<p align="center">
  <img src="frontend/assets/readme-cover.png" alt="Chaoxing WebUI cover" width="260">
</p>

# Chaoxing WebUI

一个带 Web 面板的超星刷课小工具，前后端分离，支持多用户、邀请码和 AI 答题。

## 项目由来

本项目的后端刷课、课程处理、答题和超星接口逻辑基于 [Samueli924/chaoxing](https://github.com/Samueli924/chaoxing) 继续开发，并在上游的基础上加了 Web GUI、用户/管理员后台、任务管理、邀请码系统、运行时配置和 OpenAI 兼容答题模型等功能。

沿用上游的 [GNU General Public License v3.0](LICENSE)。

## 快速上手（Windows 一键启动）

最快的方式——双击项目根目录的 `start-windows.bat`。脚本会自动读取 `.env`、装好缺失的依赖、启动后端和前端，然后打开浏览器到 `http://127.0.0.1:5501/`，直接就能用了。

> 如果没设 `ADMIN_PASSWORD`，本地启动会临时用 `local-admin-change-me` 顶一下。**公网部署前记得改掉！**

想手动控制后端和前端的话，往下看"本地调试"部分。

## 它能干嘛

- 普通用户登录后可以拉取课程、创建刷课任务、盯着进度条发呆。
- 管理员登录后会多出一个控制区，可以发公告、管邀请码、偷看所有任务、关掉不听话的任务。
- 支持多章节、多视频、答题任务并行跑，进度实时更新。
- 任务可以暂停、继续、取消。就算你关掉浏览器，后端进程也还在勤勤恳恳干活。
- 邀请码可以设最大使用次数和过期时间。查剩余次数不会偷偷扣掉你的次数哦。

## 安全相关

- `/api/admin/bootstrap` 已关闭，不能通过接口偷偷创建管理员。
- 默认管理员用户名是 `admin`，密码必须通过 `ADMIN_PASSWORD` 环境变量或 `.env` 手动设置，发布包里没有内置真实密码。
- 管理员接口全部要求 `role=admin`。
- 普通用户只能看和控制自己的任务，不能碰别人的。
- 普通用户看任务时会藏起后端的 traceback 和内部 error，只有管理员能看到完整报错。
- 获取课程列表也必须提供有效邀请码（但不消耗次数），防止公网用户把服务当免费代理用。
- 创建任务时才真正消耗一次邀请码。扣减用线程锁保护，并发创建也不会超额。
- API 默认有限流、安全响应头和 CORS 白名单。
- 打包和 Docker 构建会排除数据库、cookie、邀请码文件、日志、运行时目录和虚拟环境。

## 项目结构

```text
api/                  超星核心登录、课程、视频、答题逻辑
backend/              Flask API、权限、任务管理、邀请码、数据库
frontend/             静态 WebUI，生产环境只发布这个目录为站点根目录
deploy/               Windows 本地启动脚本和 Nginx 示例
resource/             原项目资源文件
runtime/              运行时数据目录，部署时挂载，不要公开
docker-compose.yml    后端容器部署示例
Dockerfile            生产后端镜像，使用 gunicorn
local_backend_launcher.py  本地调试启动器
```

## 本地调试

### 1. 装依赖

```powershell
python -m pip install -r requirements.txt
```

### 2. 启动后端和前端

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\start.ps1
```

### 3. 打开浏览器

```
http://127.0.0.1:5501/
```

后端跑在：

```
http://127.0.0.1:8000
```

### 4. 停下来

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\stop.ps1
```

## 公网部署

推荐结构：Nginx 对外暴露 80/443，前端静态文件直接给，`/api/` 反向代理到本机后端容器。

### 1. 准备环境变量

```bash
cp .env.example .env
```

按你的实际情况改：

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=请换成你自己的强密码
CORS_ALLOW_ORIGIN=https://你的域名
ALLOW_PUBLIC_REGISTER=true
MAX_ACTIVE_TASKS_PER_USER=2
AI_CONFIG_FILE=runtime/ai_config.json
AI_API_ENDPOINT=https://api.openai.com/v1
AI_API_KEY=
AI_API_MODEL=gpt-4o-mini
```

### 2. 启动后端

```bash
docker compose up -d --build
```

后端监听 `8000`，宿主机只绑 `127.0.0.1:18000`。

### 3. 配 Nginx

参考 `deploy/nginx/chaoxing.example.conf`，关键点：

- `root` 指到项目的 `frontend/`
- `/api/` 代理到 `http://127.0.0.1:18000/api/`
- `/config.js` 返回 `API_BASE_URL: ""`，让公网前端走同源 API
- 禁止访问 `.env`、数据库、日志、cookie、`runtime/`、`backend/` 等路径

### 4. 验证

```bash
curl https://你的域名/api/health
```

返回 `{"ok": true, ...}` 说明后端活着。

## 邀请码消耗规则

三个会碰到邀请码的动作：

- `POST /api/invites/check`：查有效性和剩余次数，**不消耗**
- `POST /api/courses`：拉课程前校验邀请码，**不消耗**
- `POST /api/tasks`：创建任务时**消耗一次**

消耗判断顺序：code 非空 → 存在 → 已启用 → 未过期 → 还有剩余次数 → 通过后 `used_count + 1`

如果任务创建了但登录超星失败，目前不会自动退回邀请码次数。需要退款的话找管理员重新生成或调整。

## 管理员面板

管理员登录后会看到：

- 发布公告
- 配置 OpenAI 兼容答题模型（端点、模型名、API Key、请求间隔、判断题词表）
- 生成、启用、停用邀请码
- 查看所有任务
- 关闭用户任务
- 查询单个任务的事件日志

普通用户看不到这些，直接调 API 也会被 403。

## 这些文件不要提交不要公开

```text
runtime/
run/
logs/
module_records/
backend_app.db*
invite_codes.json
cookies.txt
.env
```

## 常用排查

检查后端：

```bash
curl http://127.0.0.1:18000/api/health
```

看容器日志：

```bash
docker logs chaoxing-webui --tail 200
```

本地检查语法：

```powershell
python -m py_compile backend\server.py backend\runner.py backend\invite_service.py api\base.py
node --check frontend\app.js
```

## 免责声明

本工具仅供学习和技术研究使用，请勿将其用于任何违反学校规定、平台服务条款或相关法律法规的用途。

- 使用者应自行承担使用本工具所带来的一切后果和责任。
- 开发者不对因使用本工具而导致的任何直接或间接损失负责，包括但不限于学业处分、账号封禁、成绩作废等。
- 本项目不提供任何形式的题库数据、课程答案或付费内容。AI 答题功能需要用户自行提供 OpenAI 兼容的 API 端点。
- 如果你所在的学校或平台明确禁止自动化操作，请不要使用本工具。
- 下载即表示你已阅读并同意上述声明。

Stay ethical, learn lots, and don't get yourself banned. ♡
