FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_DB_FILE=/app/runtime/backend_app.db \
    INVITE_CODE_FILE=/app/runtime/invite_codes.json \
    MODULE_RECORD_DIR=/app/runtime/module_records \
    RUNTIME_DIR=/app/runtime \
    AI_CONFIG_FILE=/app/runtime/ai_config.json \
    COOKIES_PATH=/app/runtime/cookies.txt \
    CHAOXING_LOG_FILE=/app/runtime/chaoxing.log \
    CHAOXING_LOG_LEVEL=INFO \
    PORT=8000

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/runtime /app/tmp

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY api /app/api
COPY backend /app/backend
COPY resource /app/resource
COPY main.py app.py pyproject.toml README.md LICENSE /app/

RUN find /app -type d -name "__pycache__" -prune -exec rm -rf {} + \
    && find /app -type f \( -name "*.pyc" -o -name "*.pyo" -o -name "*.bak" -o -name "*.bak.*" \) -delete \
    && chown -R appuser:appuser /app

USER appuser
EXPOSE 8000
CMD ["gunicorn", "-w", "1", "--threads", "8", "-b", "0.0.0.0:8000", "--timeout", "600", "backend.server:app"]
