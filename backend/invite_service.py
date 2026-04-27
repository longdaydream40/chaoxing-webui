from __future__ import annotations

import json
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except Exception:
        return None


@dataclass
class InviteValidation:
    ok: bool
    message: str


class InviteCodeService:
    def __init__(self, file_path: str = "invite_codes.json") -> None:
        self.file = Path(file_path)
        self.lock = RLock()
        self._cache: dict[str, Any] = {"codes": {}}
        self._mtime_ns: int | None = None
        self._ensure_file()
        self._load()

    def _ensure_file(self) -> None:
        if self.file.exists():
            return
        self.file.write_text(json.dumps({"codes": {}}, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load(self) -> None:
        with self.lock:
            try:
                payload = json.loads(self.file.read_text(encoding="utf-8"))
            except Exception:
                payload = {"codes": {}}
            if "codes" not in payload or not isinstance(payload["codes"], dict):
                payload = {"codes": {}}
            self._cache = payload
            self._mtime_ns = self.file.stat().st_mtime_ns

    def _reload_if_changed(self) -> None:
        try:
            current = self.file.stat().st_mtime_ns
        except FileNotFoundError:
            self._ensure_file()
            current = self.file.stat().st_mtime_ns
        if self._mtime_ns is None or current != self._mtime_ns:
            self._load()

    def _save(self) -> None:
        with self.lock:
            self.file.write_text(json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8")
            self._mtime_ns = self.file.stat().st_mtime_ns

    def _new_code(self, length: int = 10) -> str:
        chars = string.ascii_uppercase + string.digits
        return "".join(secrets.choice(chars) for _ in range(length))

    def generate(self, note: str = "", max_uses: int | None = None, expires_hours: int | None = None) -> dict[str, Any]:
        self._reload_if_changed()
        code = self._new_code()
        while code in self._cache["codes"]:
            code = self._new_code()

        expires_at = None
        if expires_hours and expires_hours > 0:
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=expires_hours)).isoformat()

        self._cache["codes"][code] = {
            "enabled": True,
            "note": note,
            "created_at": _iso_now(),
            "expires_at": expires_at,
            "max_uses": max_uses if max_uses and max_uses > 0 else None,
            "used_count": 0,
            "last_used_at": None,
        }
        self._save()
        return {"code": code, **self._cache["codes"][code]}

    def list_codes(self) -> list[dict[str, Any]]:
        self._reload_if_changed()
        result: list[dict[str, Any]] = []
        for code, meta in self._cache["codes"].items():
            result.append({"code": code, **meta})
        result.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return result

    def set_enabled(self, code: str, enabled: bool) -> bool:
        self._reload_if_changed()
        code = code.strip().upper()
        if code not in self._cache["codes"]:
            return False
        self._cache["codes"][code]["enabled"] = enabled
        self._save()
        return True

    def _validate_normalized(self, normalized: str) -> InviteValidation:
        if not normalized:
            return InviteValidation(False, "invite_code is required")

        meta = self._cache["codes"].get(normalized)
        if not meta:
            return InviteValidation(False, "invalid invite_code")
        if not meta.get("enabled", False):
            return InviteValidation(False, "invite_code is disabled")

        expires_at = _to_datetime(meta.get("expires_at"))
        if expires_at and datetime.now(timezone.utc) > expires_at:
            return InviteValidation(False, "invite_code is expired")

        max_uses = meta.get("max_uses")
        used_count = int(meta.get("used_count", 0))
        if max_uses is not None and used_count >= int(max_uses):
            return InviteValidation(False, "invite_code usage limit reached")

        return InviteValidation(True, "ok")

    def validate(self, code: str) -> InviteValidation:
        self._reload_if_changed()
        normalized = (code or "").strip().upper()
        return self._validate_normalized(normalized)

    def inspect(self, code: str) -> dict[str, Any]:
        self._reload_if_changed()
        normalized = (code or "").strip().upper()
        validation = self._validate_normalized(normalized)
        meta = self._cache["codes"].get(normalized) or {}

        try:
            used_count = int(meta.get("used_count", 0))
        except (TypeError, ValueError):
            used_count = 0
        max_uses_raw = meta.get("max_uses")
        try:
            max_uses = int(max_uses_raw) if max_uses_raw is not None else None
        except (TypeError, ValueError):
            max_uses = None
        remaining_uses = None if max_uses is None else max(0, max_uses - used_count)

        return {
            "code": normalized,
            "valid": validation.ok,
            "message": validation.message,
            "max_uses": max_uses,
            "used_count": used_count,
            "remaining_uses": remaining_uses,
            "expires_at": meta.get("expires_at"),
        }

    def consume(self, code: str) -> InviteValidation:
        self._reload_if_changed()
        normalized = code.strip().upper()
        with self.lock:
            validation = self._validate_normalized(normalized)
            if not validation.ok:
                return validation
            meta = self._cache["codes"][normalized]
            meta["used_count"] = int(meta.get("used_count", 0)) + 1
            meta["last_used_at"] = _iso_now()
            self._save()
        return InviteValidation(True, "ok")
