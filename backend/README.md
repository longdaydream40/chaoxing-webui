# Backend

本目录是 Flask API 服务，生产环境通过 `gunicorn backend.server:app` 运行。

关键环境变量：

- `PORT`：本地 Flask 启动端口，默认 `8000`。
- `ADMIN_USERNAME` / `ADMIN_PASSWORD`：启动时创建或重置管理员。
- `APP_DB_FILE`：SQLite 数据库路径。
- `INVITE_CODE_FILE`：邀请码数据文件路径。
- `MODULE_RECORD_DIR`：任务模块记录目录。
- `RUNTIME_DIR`：cookie 等临时运行数据目录。
- `CORS_ALLOW_ORIGIN`：逗号分隔的前端域名白名单。
- `TRUST_PROXY`：反代部署时设为 `true`。
- `ALLOW_PUBLIC_REGISTER`：是否允许公网注册。
- `RATE_LIMIT_ENABLED`：是否启用 API 限流。
- `MAX_ACTIVE_TASKS_PER_USER`：普通用户最大活跃任务数。
- `MAX_CONTENT_LENGTH`：请求体大小上限，默认 64KB。
- `AI_CONFIG_FILE`：管理员保存的 OpenAI 兼容答题模型配置文件，默认位于运行时目录。
- `AI_API_ENDPOINT` / `AI_API_KEY` / `AI_API_MODEL`：首次启动时的模型配置默认值；管理员后台保存后以 `AI_CONFIG_FILE` 为准。

已关闭 `/api/admin/bootstrap`。管理员只能通过启动环境变量初始化或重置。
