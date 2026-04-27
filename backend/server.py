from __future__ import annotations

import os
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from functools import wraps
from typing import Any

from flask import Flask, jsonify, request
from werkzeug.middleware.proxy_fix import ProxyFix

from .db import AppDB
from .ai_config import public_ai_config, save_ai_config, test_ai_config
from .invite_service import InviteCodeService
from .module_recorder import ModuleRecorder
from .runner import ChaoxingTaskRunner, TaskOptions, TaskStateStore


DEFAULT_ADMIN_USERNAME = "admin"
ACTIVE_TASK_STATUSES = {"queued", "running", "paused", "cancelling"}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _split_csv(value: str) -> set[str]:
    return {part.strip() for part in value.split(",") if part.strip()}


def _safe_failure_message(message: str) -> str:
    if message.startswith("task failed:"):
        return "task failed; contact administrator for details"
    return message


def _public_task(task: dict[str, Any] | None, *, is_admin: bool = False) -> dict[str, Any] | None:
    if not task:
        return None
    blocked = {"traceback"} if is_admin else {"traceback", "error"}
    return {key: value for key, value in task.items() if key not in blocked}


def _public_tasks(tasks: list[dict[str, Any]], *, is_admin: bool = False) -> list[dict[str, Any]]:
    return [clean for task in tasks if (clean := _public_task(task, is_admin=is_admin)) is not None]


def _public_events(events: list[dict[str, Any]], *, is_admin: bool = False) -> list[dict[str, Any]]:
    if is_admin:
        return events
    cleaned: list[dict[str, Any]] = []
    for event in events:
        item = dict(event)
        item["message"] = _safe_failure_message(str(item.get("message", "")))
        cleaned.append(item)
    return cleaned


def _public_runtime(runtime: dict[str, Any] | None, *, is_admin: bool = False) -> dict[str, Any] | None:
    if runtime is None or is_admin:
        return runtime
    cleaned = dict(runtime)
    if isinstance(cleaned.get("logs"), list):
        cleaned["logs"] = [_safe_failure_message(str(line)) for line in cleaned["logs"]]
    return cleaned


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False
    app.config["MAX_CONTENT_LENGTH"] = _env_int("MAX_CONTENT_LENGTH", 64 * 1024, minimum=1024)
    if _env_bool("TRUST_PROXY", False):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # type: ignore[method-assign]

    db = AppDB(path=os.getenv("APP_DB_FILE", "backend_app.db"))
    admin_username = os.getenv("ADMIN_USERNAME", DEFAULT_ADMIN_USERNAME).strip()
    admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
    if not admin_password:
        raise RuntimeError("ADMIN_PASSWORD must be set")
    db.ensure_admin(admin_username, admin_password)

    store = TaskStateStore()
    recorder = ModuleRecorder(base_dir=os.getenv("MODULE_RECORD_DIR", "module_records"))
    invite_service = InviteCodeService(file_path=os.getenv("INVITE_CODE_FILE", "invite_codes.json"))

    def on_state_update(task_id: str, updates: dict[str, Any]) -> None:
        db.update_task(task_id, updates)

    def on_log(task_id: str, message: str) -> None:
        db.add_task_event(task_id, "info", message)

    runner = ChaoxingTaskRunner(
        store=store,
        recorder=recorder,
        on_state_update=on_state_update,
        on_log=on_log,
    )
    rate_buckets: dict[str, deque[float]] = defaultdict(deque)
    allowed_origins = _split_csv(os.getenv("CORS_ALLOW_ORIGIN", ""))

    def client_id() -> str:
        return request.remote_addr or "unknown"

    def check_rate_limit(scope: str, limit: int, window_seconds: int):
        if not _env_bool("RATE_LIMIT_ENABLED", True):
            return None
        now = time.monotonic()
        key = f"{scope}:{client_id()}"
        bucket = rate_buckets[key]
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            return _json_error("too many requests", 429)
        bucket.append(now)
        return None

    def limited(scope: str, limit: int, window_seconds: int):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
                err = check_rate_limit(scope, limit, window_seconds)
                if err:
                    return err
                return func(*args, **kwargs)

            return wrapper

        return decorator

    @app.after_request
    def add_cors_headers(response):  # type: ignore[no-untyped-def]
        origin = request.headers.get("Origin", "")
        if "*" in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = "*"
        elif origin and origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def current_user() -> dict[str, Any] | None:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        token = auth.split(" ", 1)[1].strip()
        return db.get_user_by_token(token)

    def require_user():
        user = current_user()
        if not user:
            return None, _json_error("authentication required", 401)
        return user, None

    def require_admin():
        user, err = require_user()
        if err:
            return None, err
        if user["role"] != "admin":
            return None, _json_error("admin role required", 403)
        return user, None

    def require_task_access(task_id: str):
        user, err = require_user()
        if err:
            return None, None, err
        task = db.get_task(task_id)
        if not task:
            return None, None, _json_error("task not found", 404)
        if user["role"] != "admin" and int(task["user_id"]) != int(user["id"]):
            return None, None, _json_error("forbidden", 403)
        return user, task, None

    @app.route("/api/health", methods=["GET"])
    def health() -> Any:
        return jsonify({"ok": True, "time": _iso_now()})

    @app.route("/api/auth/register", methods=["POST", "OPTIONS"])
    @limited("auth_register", 10, 300)
    def register() -> Any:
        if request.method == "OPTIONS":
            return ("", 204)
        if not _env_bool("ALLOW_PUBLIC_REGISTER", True):
            return _json_error("public registration is disabled", 403)
        data = request.get_json(silent=True) or {}
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", "")).strip()
        if not username or not password:
            return _json_error("username and password are required")
        try:
            user = db.create_user(username=username, password=password, role="user")
        except Exception as exc:
            return _json_error(str(exc))
        token = db.create_session(int(user["id"]))
        return jsonify(
            {
                "token": token,
                "user": {"id": user["id"], "username": user["username"], "role": user["role"]},
            }
        )

    @app.route("/api/auth/login", methods=["POST", "OPTIONS"])
    @limited("auth_login", 30, 300)
    def login() -> Any:
        if request.method == "OPTIONS":
            return ("", 204)
        data = request.get_json(silent=True) or {}
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", "")).strip()
        user = db.verify_user(username, password)
        if not user:
            return _json_error("invalid username or password", 401)
        token = db.create_session(int(user["id"]))
        return jsonify(
            {
                "token": token,
                "user": {"id": user["id"], "username": user["username"], "role": user["role"]},
            }
        )

    @app.route("/api/auth/me", methods=["GET"])
    def auth_me() -> Any:
        user, err = require_user()
        if err:
            return err
        return jsonify({"user": {"id": user["id"], "username": user["username"], "role": user["role"]}})

    @app.route("/api/admin/bootstrap", methods=["POST", "OPTIONS"])
    def admin_bootstrap() -> Any:
        return _json_error("admin bootstrap is disabled", 404)

    @app.route("/api/announcements", methods=["GET"])
    def list_announcements() -> Any:
        return jsonify({"announcements": db.list_announcements(limit=30)})

    @app.route("/api/courses", methods=["POST", "OPTIONS"])
    @limited("courses", 30, 300)
    def courses() -> Any:
        if request.method == "OPTIONS":
            return ("", 204)
        user, err = require_user()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", "")).strip()
        if not username:
            return _json_error("username is required")
        if not password:
            return _json_error("password is required")
        invite_code = str(data.get("invite_code", "")).strip()
        invite_validation = invite_service.validate(invite_code)
        if not invite_validation.ok:
            return _json_error(invite_validation.message, 403)
        try:
            course_list = runner.fetch_courses(username=username, password=password)
            return jsonify({"courses": course_list, "requested_by": user["username"]})
        except Exception as exc:
            return _json_error(f"{type(exc).__name__}: {exc}", 400)

    @app.route("/api/tasks", methods=["POST", "OPTIONS"])
    @limited("task_create", 10, 600)
    def create_task() -> Any:
        if request.method == "OPTIONS":
            return ("", 204)
        user, err = require_user()
        if err:
            return err

        data = request.get_json(silent=True) or {}
        course_ids = [str(cid).strip() for cid in (data.get("course_ids") or []) if str(cid).strip()]
        if not course_ids:
            return _json_error("course_ids is required")
        task_id = uuid.uuid4().hex[:12]
        try:
            speed = max(0.1, min(float(data.get("speed", 1.0)), 10.0))
            jobs = max(1, min(int(data.get("jobs", 4)), 8))
        except (TypeError, ValueError):
            return _json_error("speed and jobs must be numeric")
        notopen_action = str(data.get("notopen_action", "continue"))
        if notopen_action not in {"continue", "retry", "ask"}:
            return _json_error("notopen_action is invalid")

        opts = TaskOptions(
            username=str(data.get("username", "")).strip(),
            password=str(data.get("password", "")).strip(),
            course_ids=course_ids,
            speed=speed,
            notopen_action=notopen_action,
            jobs=jobs,
        )
        if not opts.username or not opts.password:
            return _json_error("username and password are required")
        if user["role"] != "admin":
            max_active = _env_int("MAX_ACTIVE_TASKS_PER_USER", 2, minimum=1, maximum=20)
            active_count = sum(1 for task in db.list_tasks(user_id=int(user["id"]), limit=100) if task["status"] in ACTIVE_TASK_STATUSES)
            if active_count >= max_active:
                return _json_error("active task limit reached", 429)

        invite_code = str(data.get("invite_code", "")).strip()
        invite_validation = invite_service.consume(invite_code)
        if not invite_validation.ok:
            return _json_error(invite_validation.message, 403)

        payload = {
            "task_id": task_id,
            "user_id": int(user["id"]),
            "username": user["username"],
            "status": "queued",
            "created_at": _iso_now(),
            "done_courses": 0,
            "total_courses": 0,
            "done_modules": 0,
            "total_modules": 0,
            "logs": [],
        }
        store.create(task_id, payload)
        db.create_task(task_id=task_id, user_id=int(user["id"]), status="queued")
        db.add_task_event(task_id, "info", f"task created by {user['username']}")

        thread = threading.Thread(target=runner.run_task, args=(task_id, opts), daemon=True)
        thread.start()
        return jsonify({"task_id": task_id, "status": "queued"})

    @app.route("/api/invites/check", methods=["POST", "OPTIONS"])
    @limited("invite_check", 60, 300)
    def check_invite() -> Any:
        if request.method == "OPTIONS":
            return ("", 204)
        _, err = require_user()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        code = str(data.get("code", "")).strip()
        return jsonify({"invite": invite_service.inspect(code)})

    @app.route("/api/tasks/<task_id>", methods=["GET"])
    @limited("task_get", 120, 60)
    def get_task(task_id: str) -> Any:
        user, task, err = require_task_access(task_id)
        if err:
            return err
        is_admin = user["role"] == "admin"
        events = db.list_task_events(task_id, limit=500)
        runtime = store.get(task_id)
        return jsonify(
            {
                "task": _public_task(task, is_admin=is_admin),
                "events": _public_events(events, is_admin=is_admin),
                "runtime": _public_runtime(runtime, is_admin=is_admin),
            }
        )

    @app.route("/api/tasks/<task_id>/<action>", methods=["POST", "OPTIONS"])
    @limited("task_control", 60, 300)
    def control_task(task_id: str, action: str) -> Any:
        if request.method == "OPTIONS":
            return ("", 204)
        user, task, err = require_task_access(task_id)
        if err:
            return err
        if action not in {"pause", "resume", "cancel"}:
            return _json_error("unsupported task action", 404)

        active_worker = True
        if action == "pause":
            active_worker = runner.pause_task(task_id)
            if not active_worker:
                db.update_task(task_id, {"status": "paused"})
                db.add_task_event(task_id, "warning", "task marked paused; no active worker in this server process")
        elif action == "resume":
            active_worker = runner.resume_task(task_id)
            if not active_worker:
                return _json_error("task cannot resume because no active worker exists in this server process", 409)
        elif action == "cancel":
            active_worker = runner.cancel_task(task_id)
            if not active_worker:
                db.update_task(task_id, {"status": "cancelled"})
                db.add_task_event(task_id, "warning", "task cancelled without active worker")

        updated = db.get_task(task_id) or task
        return jsonify({"ok": True, "active_worker": active_worker, "task": _public_task(updated, is_admin=user["role"] == "admin")})

    @app.route("/api/tasks", methods=["GET"])
    def list_tasks() -> Any:
        user, err = require_user()
        if err:
            return err
        if user["role"] == "admin":
            tasks = db.list_tasks(user_id=None, limit=200)
        else:
            tasks = db.list_tasks(user_id=int(user["id"]), limit=200)
        return jsonify({"tasks": _public_tasks(tasks, is_admin=user["role"] == "admin")})

    @app.route("/api/admin/tasks", methods=["GET"])
    def admin_list_tasks() -> Any:
        user, err = require_admin()
        if err:
            return err
        tasks = db.list_tasks(user_id=None, limit=500)
        return jsonify({"tasks": _public_tasks(tasks, is_admin=True), "operator": user["username"]})

    @app.route("/api/admin/tasks/<task_id>", methods=["GET"])
    def admin_get_task(task_id: str) -> Any:
        _, err = require_admin()
        if err:
            return err
        task = db.get_task(task_id)
        if not task:
            return _json_error("task not found", 404)
        events = db.list_task_events(task_id, limit=1000)
        runtime = store.get(task_id)
        return jsonify({"task": _public_task(task, is_admin=True), "events": events, "runtime": runtime})

    @app.route("/api/admin/ai-config", methods=["GET"])
    def admin_get_ai_config() -> Any:
        _, err = require_admin()
        if err:
            return err
        return jsonify({"config": public_ai_config()})

    @app.route("/api/admin/ai-config", methods=["POST", "PUT", "OPTIONS"])
    def admin_save_ai_config() -> Any:
        if request.method == "OPTIONS":
            return ("", 204)
        _, err = require_admin()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        try:
            config = save_ai_config(data)
        except ValueError as exc:
            return _json_error(str(exc))
        return jsonify({"config": public_ai_config(config)})

    @app.route("/api/admin/ai-config/test", methods=["POST", "OPTIONS"])
    @limited("admin_ai_config_test", 10, 300)
    def admin_test_ai_config() -> Any:
        if request.method == "OPTIONS":
            return ("", 204)
        _, err = require_admin()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        try:
            result = test_ai_config(data)
        except Exception as exc:
            return _json_error(f"{type(exc).__name__}: {exc}", 400)
        return jsonify(result)

    @app.route("/api/admin/invites", methods=["GET"])
    def list_invites() -> Any:
        _, err = require_admin()
        if err:
            return err
        return jsonify({"invites": invite_service.list_codes()})

    @app.route("/api/admin/invites/generate", methods=["POST", "OPTIONS"])
    @limited("admin_invite_generate", 30, 300)
    def generate_invite() -> Any:
        if request.method == "OPTIONS":
            return ("", 204)
        _, err = require_admin()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        note = str(data.get("note", "")).strip()
        max_uses = data.get("max_uses")
        expires_hours = data.get("expires_hours")
        try:
            if max_uses is not None:
                max_uses = int(max_uses)
            if expires_hours is not None:
                expires_hours = int(expires_hours)
        except (TypeError, ValueError):
            return _json_error("max_uses and expires_hours must be integers")
        invite = invite_service.generate(note=note, max_uses=max_uses, expires_hours=expires_hours)
        return jsonify({"invite": invite})

    @app.route("/api/admin/invites/enable", methods=["POST", "OPTIONS"])
    def enable_invite() -> Any:
        if request.method == "OPTIONS":
            return ("", 204)
        _, err = require_admin()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        code = str(data.get("code", "")).strip()
        if not code:
            return _json_error("code is required")
        updated = invite_service.set_enabled(code, True)
        if not updated:
            return _json_error("invite code not found", 404)
        return jsonify({"ok": True})

    @app.route("/api/admin/invites/disable", methods=["POST", "OPTIONS"])
    def disable_invite() -> Any:
        if request.method == "OPTIONS":
            return ("", 204)
        _, err = require_admin()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        code = str(data.get("code", "")).strip()
        if not code:
            return _json_error("code is required")
        updated = invite_service.set_enabled(code, False)
        if not updated:
            return _json_error("invite code not found", 404)
        return jsonify({"ok": True})

    @app.route("/api/admin/announcements", methods=["POST", "OPTIONS"])
    def create_announcement() -> Any:
        if request.method == "OPTIONS":
            return ("", 204)
        user, err = require_admin()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        title = str(data.get("title", "")).strip()
        content = str(data.get("content", "")).strip()
        if not title or not content:
            return _json_error("title and content are required")
        notice = db.create_announcement(title=title, content=content, created_by=int(user["id"]))
        return jsonify({"announcement": notice})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")), debug=False)
