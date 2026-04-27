from __future__ import annotations

import os
import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parent

os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("HOST", "127.0.0.1")
os.environ.setdefault("PORT", "8000")
os.environ.setdefault("CORS_ALLOW_ORIGIN", "http://127.0.0.1:5501,http://localhost:5501")
os.environ.setdefault("CHAOXING_LOG_FILE", str(ROOT / "logs" / "chaoxing.log"))
os.environ.setdefault("RUNTIME_DIR", str(ROOT / "runtime"))
os.environ.setdefault("APP_DB_FILE", str(ROOT / "runtime" / "backend_app.db"))
os.environ.setdefault("INVITE_CODE_FILE", str(ROOT / "runtime" / "invite_codes.json"))
os.environ.setdefault("MODULE_RECORD_DIR", str(ROOT / "runtime" / "module_records"))
os.environ.setdefault("AI_CONFIG_FILE", str(ROOT / "runtime" / "ai_config.json"))

Path(os.environ["CHAOXING_LOG_FILE"]).parent.mkdir(parents=True, exist_ok=True)
Path(os.environ["RUNTIME_DIR"]).mkdir(parents=True, exist_ok=True)
Path(os.environ["MODULE_RECORD_DIR"]).mkdir(parents=True, exist_ok=True)
Path(os.environ["APP_DB_FILE"]).parent.mkdir(parents=True, exist_ok=True)
Path(os.environ["INVITE_CODE_FILE"]).parent.mkdir(parents=True, exist_ok=True)
Path(os.environ["AI_CONFIG_FILE"]).parent.mkdir(parents=True, exist_ok=True)

if not os.environ.get("ADMIN_PASSWORD", "").strip():
    raise RuntimeError("ADMIN_PASSWORD must be set before starting the backend")

runpy.run_module("backend.server", run_name="__main__")
