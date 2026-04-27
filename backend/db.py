from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AppDB:
    def __init__(self, path: str = "backend_app.db") -> None:
        self.path = path
        self.lock = Lock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self.lock:
            cur = self.conn.cursor()
            cur.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS announcements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_by INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(created_by) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    done_courses INTEGER NOT NULL DEFAULT 0,
                    total_courses INTEGER NOT NULL DEFAULT 0,
                    done_modules INTEGER NOT NULL DEFAULT 0,
                    total_modules INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    traceback TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
                );
                """
            )
            self.conn.commit()

    def ensure_admin(self, username: str | None, password: str | None) -> None:
        if not username or not password:
            return
        user = self.find_user_by_username(username)
        if user:
            with self.lock:
                self.conn.execute(
                    "UPDATE users SET password_hash = ?, role = ? WHERE id = ?",
                    (generate_password_hash(password), "admin", int(user["id"])),
                )
                self.conn.commit()
            return
        self.create_user(username=username, password=password, role="admin")

    def create_user(self, username: str, password: str, role: str = "user") -> dict[str, Any]:
        username = username.strip()
        if len(username) < 3:
            raise ValueError("username must be at least 3 characters")
        if len(password) < 6:
            raise ValueError("password must be at least 6 characters")
        with self.lock:
            cur = self.conn.cursor()
            try:
                cur.execute(
                    "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                    (username, generate_password_hash(password), role, _iso_now()),
                )
                self.conn.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError("username already exists") from exc
        user = self.find_user_by_username(username)
        if not user:
            raise RuntimeError("create user failed")
        return user

    def find_user_by_username(self, username: str) -> dict[str, Any] | None:
        cur = self.conn.cursor()
        row = cur.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()
        return dict(row) if row else None

    def find_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        cur = self.conn.cursor()
        row = cur.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def verify_user(self, username: str, password: str) -> dict[str, Any] | None:
        user = self.find_user_by_username(username)
        if not user:
            return None
        if not check_password_hash(user["password_hash"], password):
            return None
        return user

    def create_session(self, user_id: int, hours: int = 24 * 7) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=hours)
        with self.lock:
            self.conn.execute(
                "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token, user_id, now.isoformat(), expires.isoformat()),
            )
            self.conn.commit()
        return token

    def get_user_by_token(self, token: str) -> dict[str, Any] | None:
        if not token:
            return None
        cur = self.conn.cursor()
        row = cur.execute(
            """
            SELECT u.* FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ? AND s.expires_at > ?
            """,
            (token, _iso_now()),
        ).fetchone()
        return dict(row) if row else None

    def create_announcement(self, title: str, content: str, created_by: int) -> dict[str, Any]:
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(
                "INSERT INTO announcements (title, content, created_by, created_at) VALUES (?, ?, ?, ?)",
                (title.strip(), content.strip(), created_by, _iso_now()),
            )
            announcement_id = cur.lastrowid
            self.conn.commit()
        row = self.conn.execute("SELECT * FROM announcements WHERE id = ?", (announcement_id,)).fetchone()
        return dict(row) if row else {}

    def list_announcements(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT a.*, u.username AS author
            FROM announcements a
            JOIN users u ON u.id = a.created_by
            ORDER BY a.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def create_task(self, task_id: str, user_id: int, status: str = "queued") -> None:
        now = _iso_now()
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO tasks (task_id, user_id, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (task_id, user_id, status, now, now),
            )
            self.conn.commit()

    def update_task(self, task_id: str, updates: dict[str, Any]) -> None:
        if not updates:
            return
        allowed = {
            "status",
            "done_courses",
            "total_courses",
            "done_modules",
            "total_modules",
            "error",
            "traceback",
        }
        fields: list[str] = []
        values: list[Any] = []
        for key, value in updates.items():
            if key in allowed:
                fields.append(f"{key} = ?")
                values.append(value)
        fields.append("updated_at = ?")
        values.append(_iso_now())
        values.append(task_id)
        with self.lock:
            self.conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE task_id = ?", tuple(values))
            self.conn.commit()

    def add_task_event(self, task_id: str, level: str, message: str) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT INTO task_events (task_id, level, message, created_at) VALUES (?, ?, ?, ?)",
                (task_id, level, message, _iso_now()),
            )
            self.conn.commit()

    def list_task_events(self, task_id: str, limit: int = 500) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM task_events WHERE task_id = ? ORDER BY id ASC LIMIT ?",
            (task_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT t.*, u.username
            FROM tasks t
            JOIN users u ON u.id = t.user_id
            WHERE t.task_id = ?
            """,
            (task_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_tasks(self, user_id: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if user_id is None:
            rows = self.conn.execute(
                """
                SELECT t.*, u.username
                FROM tasks t
                JOIN users u ON u.id = t.user_id
                ORDER BY t.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT t.*, u.username
                FROM tasks t
                JOIN users u ON u.id = t.user_id
                WHERE t.user_id = ?
                ORDER BY t.created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]
