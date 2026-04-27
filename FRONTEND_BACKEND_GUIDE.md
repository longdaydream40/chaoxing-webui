# Frontend/Backend Split Guide

## Overview

This repository now includes a separated web architecture:

- `frontend/`: user main UI (`/`), login UI (`/login/`), and register UI (`/register/`)
- `backend/`: processing service (auth, invite, announcement, task execution, status tracking)
- `module_records/`: per-module completion files
- `backend_app.db`: lightweight SQLite database for users/sessions/tasks/events/announcements

## Run Backend

```bash
python -m backend.server
```

Backend default URL:

- `http://127.0.0.1:8000`

Backend environment variables:

- `PORT` (default: `8000`)
- `CORS_ALLOW_ORIGIN` (comma-separated allowed origins; empty means same-origin only)
- `MODULE_RECORD_DIR` (default: `module_records`)
- `INVITE_CODE_FILE` (default: `invite_codes.json`)
- `ADMIN_USERNAME` / `ADMIN_PASSWORD` (admin is created or reset on startup)
- `AI_CONFIG_FILE` (default runtime AI answering configuration file)

## Run Frontend

Use any static server:

```bash
python -m http.server 5500 -d frontend
```

Frontend URL:

- `http://127.0.0.1:5500`

If backend URL is different, edit:

- `frontend/config.js`

## API Endpoints

- `GET /api/health`
- `POST /api/auth/register` (no invite code required)
- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/announcements`
- `POST /api/courses` (requires user auth token)
- `POST /api/tasks` (requires user auth token + `invite_code`, consumes 1 usage)
- `GET /api/tasks/<task_id>` (query task status)
- `GET /api/tasks` (list tasks)

Admin endpoints (requires admin user token):

- `GET /api/admin/ai-config`
- `POST /api/admin/ai-config`
- `POST /api/admin/ai-config/test`
- `GET /api/admin/invites`
- `POST /api/admin/invites/generate`
- `POST /api/admin/invites/enable`
- `POST /api/admin/invites/disable`
- `POST /api/admin/announcements`
- `GET /api/admin/tasks`
- `GET /api/admin/tasks/<task_id>`

Generate invite example:

```bash
curl -X POST http://127.0.0.1:8000/api/admin/invites/generate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <admin_token>" \
  -d "{\"note\":\"vip user\",\"max_uses\":10,\"expires_hours\":72}"
```

Invite updates take effect in real time without backend restart.

## User Flow

- Login page: `/login/`
- Register page: `/register/`
- Main panel: `/`

The main panel shows the admin control area only after an admin account logs in.

## First Admin Setup

Set environment variables before start:

- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`

`/api/admin/bootstrap` is disabled; do not create administrators through public HTTP endpoints.

## Per-Module Record Files

For each processed module, backend writes one file:

- `module_records/<task_id>/<timestamp>_<course>_<module>_<status>.json`

Each JSON includes:

- course info
- module info
- module status
- job progress counts
- timestamp

## Deploy Suggestion

- Deploy backend to server (systemd + reverse proxy, or Docker).
- Keep frontend as static files on Nginx/CDN.
- Configure frontend `API_BASE_URL` to backend public URL.

## Windows One-Click Scripts

Start both services:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\start.ps1
```

Check service status:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\status.ps1
```

Stop both services:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\stop.ps1
```
