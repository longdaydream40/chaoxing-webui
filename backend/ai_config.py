from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import urlparse

import httpx
from openai import OpenAI


AI_CONFIG_LOCK = RLock()
KEEP_SECRET_SENTINEL = "__KEEP__"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


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


def _config_path() -> Path:
    default_path = Path(os.getenv("RUNTIME_DIR", "runtime")) / "ai_config.json"
    return Path(os.getenv("AI_CONFIG_FILE", str(default_path)))


def _default_config() -> dict[str, Any]:
    api_key = os.getenv("AI_API_KEY", "").strip()
    return {
        "enabled": _env_bool("AI_ENABLED", bool(api_key)),
        "provider": "AI",
        "endpoint": os.getenv("AI_API_ENDPOINT", "https://api.openai.com/v1").strip(),
        "api_key": api_key,
        "model": os.getenv("AI_API_MODEL", "gpt-4o-mini").strip(),
        "http_proxy": os.getenv("AI_HTTP_PROXY", "").strip(),
        "min_interval_seconds": _env_int("AI_MIN_INTERVAL_SECONDS", 1, minimum=0, maximum=3600),
        "delay": _env_float("AI_QUERY_DELAY", 1.0, minimum=0.0, maximum=60.0),
        "submit": _env_bool("AI_SUBMIT_ANSWERS", True),
        "cover_rate": _env_float("AI_COVER_RATE", 0.75, minimum=0.0, maximum=1.0),
        "true_list": os.getenv("AI_TRUE_LIST", "正确,对,√,是").strip(),
        "false_list": os.getenv("AI_FALSE_LIST", "错误,错,×,否,不对,不正确").strip(),
    }


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _as_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _normalize_config(raw: dict[str, Any], *, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    defaults = _default_config()
    merged = {**defaults, **(existing or {}), **raw}

    incoming_key = raw.get("api_key", None)
    api_key = str(merged.get("api_key") or "").strip()
    if incoming_key is not None and not str(incoming_key).strip() and existing is not None:
        api_key = str(existing.get("api_key") or "").strip()
    if api_key == KEEP_SECRET_SENTINEL:
        api_key = str((existing or defaults).get("api_key") or "").strip()
    if _as_bool(merged.get("clear_api_key"), False):
        api_key = ""

    normalized = {
        "enabled": _as_bool(merged.get("enabled"), defaults["enabled"]),
        "provider": "AI",
        "endpoint": str(merged.get("endpoint") or "").strip().rstrip("/"),
        "api_key": api_key,
        "model": str(merged.get("model") or "").strip(),
        "http_proxy": str(merged.get("http_proxy") or "").strip(),
        "min_interval_seconds": _as_int(merged.get("min_interval_seconds"), 1, 0, 3600),
        "delay": _as_float(merged.get("delay"), 1.0, 0.0, 60.0),
        "submit": _as_bool(merged.get("submit"), True),
        "cover_rate": _as_float(merged.get("cover_rate"), 0.75, 0.0, 1.0),
        "true_list": str(merged.get("true_list") or defaults["true_list"]).strip(),
        "false_list": str(merged.get("false_list") or defaults["false_list"]).strip(),
    }
    return normalized


def _validate_config(config: dict[str, Any]) -> None:
    if not config.get("enabled"):
        return
    endpoint = str(config.get("endpoint") or "").strip()
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("endpoint must be a valid http(s) OpenAI-compatible base URL")
    if not str(config.get("model") or "").strip():
        raise ValueError("model is required when AI answering is enabled")
    if not str(config.get("api_key") or "").strip():
        raise ValueError("api_key is required when AI answering is enabled")


def load_ai_config() -> dict[str, Any]:
    with AI_CONFIG_LOCK:
        path = _config_path()
        if not path.is_file():
            return _normalize_config({})
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _normalize_config({})
        if not isinstance(raw, dict):
            return _normalize_config({})
        return _normalize_config(raw)


def save_ai_config(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("config payload must be an object")
    with AI_CONFIG_LOCK:
        existing = load_ai_config()
        config = _normalize_config(payload, existing=existing)
        _validate_config(config)
        path = _config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        tmp_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, path)
        return config


def public_ai_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    data = dict(config or load_ai_config())
    api_key = str(data.pop("api_key", "") or "")
    data["has_api_key"] = bool(api_key)
    data["api_key_preview"] = f"...{api_key[-4:]}" if api_key else ""
    data["api_key"] = ""
    return data


def get_fixed_tiku_config() -> dict[str, Any]:
    config = load_ai_config()
    has_ai_config = all(
        [
            config.get("enabled"),
            str(config.get("endpoint") or "").strip(),
            str(config.get("api_key") or "").strip(),
            str(config.get("model") or "").strip(),
        ]
    )
    return {
        "provider": "AI" if has_ai_config else "",
        "check_llm_connection": "false",
        "submit": "true" if config.get("submit") else "false",
        "cover_rate": str(config.get("cover_rate", 0.75)),
        "delay": str(config.get("delay", 1.0)),
        "tokens": "",
        "url": "",
        "endpoint": str(config.get("endpoint") or "").strip(),
        "key": str(config.get("api_key") or "").strip(),
        "model": str(config.get("model") or "").strip(),
        "min_interval_seconds": str(config.get("min_interval_seconds", 1)),
        "http_proxy": str(config.get("http_proxy") or "").strip(),
        "true_list": str(config.get("true_list") or "正确,对,√,是"),
        "false_list": str(config.get("false_list") or "错误,错,×,否,不对,不正确"),
    }


def test_ai_config(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    base = load_ai_config()
    candidate = _normalize_config(payload or {}, existing=base)
    _validate_config(candidate)
    client_kwargs: dict[str, Any] = {
        "base_url": candidate["endpoint"],
        "api_key": candidate["api_key"],
    }
    if candidate.get("http_proxy"):
        client_kwargs["http_client"] = httpx.Client(proxy=candidate["http_proxy"], timeout=20)
    client = OpenAI(**client_kwargs)
    completion = client.chat.completions.create(
        model=candidate["model"],
        messages=[{"role": "user", "content": "Reply with OK."}],
        max_tokens=8,
    )
    content = ""
    if completion.choices:
        content = completion.choices[0].message.content or ""
    return {"ok": bool(content.strip()), "response": content.strip()}
