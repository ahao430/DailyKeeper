# DailyKeeper 部署指南（Docker Compose）

> 本文描述生产环境的 Docker Compose 部署、数据持久化、升级、首个账号配置流程、通知配置与常见问题。接口细节见 [API.md](API.md)，架构说明见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 一、Docker Compose 部署

```bash
# 1. 克隆仓库
git clone git@github.com:ahao430/DailyKeeper.git
cd DailyKeeper

# 2. 准备环境变量
cp deploy/.env.example deploy/.env

# 3. 修改 SECRET_KEY（生产必须！）
#    openssl rand -hex 32
vim deploy/.env

# 4. 构建并启动（api / scheduler / worker / browser-worker 四进程）
docker compose -f deploy/docker-compose.yml up -d --build

# 5. 验证
curl http://127.0.0.1:8000/healthz
# 浏览器打开 Swagger UI：http://<host>:8000/docs
```

部署内容：

- **api**：uvicorn，对外暴露 `8000` 端口，带 healthcheck（`/healthz`，30s 间隔）。
- **scheduler**：`python -m app.scheduler`，APScheduler 定时扫描并创建任务执行。
- **worker**：`python -m app.worker`，从数据库队列领取并执行 API 类任务（`needs_browser=false`）。
- **browser-worker**：`python -m app.browser_worker`，执行浏览器自动化任务（`needs_browser=true`），见第三节「browser-worker 服务」。
- api / scheduler / worker 共用同一镜像（`deploy/Dockerfile.backend`，scheduler/worker 通过 `command` 覆盖启动命令）；browser-worker 使用内置 Playwright + Chromium 的专用镜像（`deploy/Dockerfile.browser`）。四个服务挂载同一个数据卷 `dk-data:/app/data`。

**默认管理员**：`admin / admin123`（来自环境变量，首次启动自动写入 users 表）。**首次登录后请立即通过 `PUT /api/auth/password` 修改密码**；更多管理员可在 Dashboard「设置 → 用户管理」添加（`POST /api/users`），停用/删除后其会话立即失效。

## 二、环境变量

配置前缀统一为 `DAILYKEEPER_`，也可在 `.env` 文件中设置（见 `deploy/.env.example`）。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DAILYKEEPER_ENV` | `dev` | 运行环境标识（`dev` / `prod`） |
| `DAILYKEEPER_LOG_LEVEL` | `INFO` | 日志级别 |
| `DAILYKEEPER_DATABASE_URL` | `sqlite+aiosqlite:///./data/dailykeeper.db` | 数据库连接串 |
| `DAILYKEEPER_DATA_DIR` | `./data` | 数据目录 |
| `DAILYKEEPER_SECRET_KEY` | 内置开发默认值 | **生产必须修改**：JWT 签名与凭据加密（AES-GCM）密钥，`openssl rand -hex 32` |
| `DAILYKEEPER_ENCRYPTION_KEY` | 空（回退用 SECRET_KEY） | 独立凭据加密密钥，可与 SECRET_KEY 分开轮换 |
| `DAILYKEEPER_ADMIN_USERNAME` | `admin` | 初始管理员用户名 |
| `DAILYKEEPER_ADMIN_PASSWORD` | `admin123` | 初始管理员密码，**首次登录后修改** |
| `DAILYKEEPER_ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | JWT 有效期（分钟） |
| `DAILYKEEPER_TIMEZONE` | `Asia/Shanghai` | 调度默认时区 |
| `DAILYKEEPER_SCHEDULER_INTERVAL_SECONDS` | `30` | scheduler 扫描间隔 |
| `DAILYKEEPER_WORKER_POLL_SECONDS` | `3` | worker 轮询间隔 |
| `DAILYKEEPER_WORKER_CONCURRENCY` | `4` | worker 并发数 |
| `DAILYKEEPER_TASK_TIMEOUT_SECONDS` | `300` | 单任务超时 |
| `DAILYKEEPER_HTTP_TIMEOUT` | `30` | 插件 HTTP 请求超时 |
| `DAILYKEEPER_MAX_RETRIES` | `3` | 可重试失败的最大重试次数 |
| `DAILYKEEPER_RETRY_BACKOFF_SECONDS` | `60` | 重试退避间隔 |
| `DAILYKEEPER_BROWSER_HEADLESS` | `true` | browser worker 是否无头运行（容器内保持 `true`） |
| `DAILYKEEPER_BROWSER_WORKER_CONCURRENCY` | `2` | browser worker 并发执行的浏览器任务数 |
| `DAILYKEEPER_BROWSER_STATE_DIR` | 空（`{data_dir}/browser_states`） | 浏览器登录态（storage state）文件目录 |
| `DAILYKEEPER_BROWSER_SLOW_MO_MS` | `0` | Playwright slow_mo（调试时放慢操作，如 `250`） |
| `DAILYKEEPER_CORS_ORIGINS` | `*` | CORS 允许来源（接入 Dashboard 后收紧） |

## 三、browser-worker 服务（浏览器自动化）

`browser-worker` 执行所有 `requires_browser` 的任务（认领分流见 [ARCHITECTURE.md](ARCHITECTURE.md)），使用专用镜像 `deploy/Dockerfile.browser`（基于 `mcr.microsoft.com/playwright/python:v1.49.0-noble`，内置 Playwright 与 Chromium 及全部系统依赖，**不要在该镜像内重新安装 playwright**）。

- **内存**：Chromium 常驻 + 每任务一个 Browser Context，内存开销明显高于普通 worker。compose 中已设 `mem_limit: 1g`；账号多或页面重时可调到 `1.5g`–`2g`，并相应调整 `DAILYKEEPER_BROWSER_WORKER_CONCURRENCY`（默认 2，每个并发任务一个 Context）。
- **环境变量**：`DAILYKEEPER_BROWSER_HEADLESS`（容器内保持 `true`）、`DAILYKEEPER_BROWSER_WORKER_CONCURRENCY`、`DAILYKEEPER_BROWSER_STATE_DIR`（默认 `{data_dir}/browser_states`）、`DAILYKEEPER_BROWSER_SLOW_MO_MS`（排障时放慢操作），详见第二节环境变量表。
- **登录态文件**：每个账号的 storage state（Cookie / localStorage）持久化在数据卷 `dk-data` 内，容器路径 `/app/data/browser_states/account-{id}.json`，随数据卷一起备份/迁移；删除对应文件即强制该账号下次重新登录。这些文件包含登录凭据，注意数据卷的访问控制。
- **单独排障**：临时起一个有头实例排查页面问题时，可 `docker compose -f deploy/docker-compose.yml run -e DAILYKEEPER_BROWSER_HEADLESS=false -e DAILYKEEPER_BROWSER_SLOW_MO_MS=250 browser-worker`（需要桌面环境转发）。
- 不部署 browser-worker 时，浏览器任务会被普通 worker 的守卫置为 `NEEDS_ACTION`（不会误执行），部署后新任务自动走浏览器执行。

## 四、本地 Agent（dk-agent）部署

本地 Agent 把任务执行延伸到你的 Mac / Windows / Linux 桌面环境（桌面应用、本地浏览器登录态等），与服务器共享 DailyKeeper SDK。协议为**拉取式**：Agent 主动向服务器发心跳 / 认领 / 拉取上下文 / 回传结果，服务器不需要访问你的电脑，家庭网络 NAT 后面即可运行（详见 [ARCHITECTURE.md](ARCHITECTURE.md)）。

**服务器侧（创建 Agent 令牌）**

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<你的管理员密码>"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s -X POST http://127.0.0.1:8000/api/agents -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"name":"我的 Mac"}'
# 返回 {"id":1,"name":"我的 Mac","token":"...","note":"令牌仅显示一次..."} —— 立即保存 token
```

**Agent 侧（安装并运行）**

```bash
# 与服务器相同版本：git clone 同一仓库
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e sdk -e plugins/demo -e local-agent      # 插件按需安装（装了什么就能跑什么平台）
export DK_AGENT_SERVER="https://your-server.com"       # 生产必须 HTTPS：凭据经上下文接口下发
export DK_AGENT_TOKEN="<上一步的一次性令牌>"
dk-agent                                               # 或 python -m dailykeeper_agent
```

- **心跳**：默认 30 秒；超过 90 秒（`AGENT_OFFLINE_SECONDS`，代码常量）未心跳，调度器将该 Agent 置为 OFFLINE，中断其运行中任务并发送 `agent_offline` 通知。
- **令牌**：支持轮换（`POST /api/agents/{id}/rotate`，旧令牌立即失效）与撤销（删除 Agent 即中断其运行中任务）。
- **凭据**：仅经上下文接口下发、只驻留 Agent 进程内存，不落盘；离线时 Agent 容忍服务器不可达（退避重试不退出）。
- **浏览器任务**：Agent 上报能力为 `["http"]`（`context.http` 可用）；`context.browser` 目前仅服务器 browser worker 提供。

## 五、数据持久化与备份

- 所有持久化数据在 Docker 卷 `dk-data` 中，容器内路径 `/app/data`，数据库文件为 `/app/data/dailykeeper.db`。
- 更换宿主机或迁移时，先备份数据卷再操作。

容器内备份（SQLite 在线备份，安全）：

```bash
docker compose -f deploy/docker-compose.yml exec api \
  sqlite3 /app/data/dailykeeper.db ".backup '/app/data/backup.db'"
```

若镜像内没有 `sqlite3` CLI，可用 Python 执行同样的事：

```bash
docker compose -f deploy/docker-compose.yml exec api python -c \
  "import sqlite3; sqlite3.connect('/app/data/dailykeeper.db').backup(sqlite3.connect('/app/data/backup.db')); print('ok')"
```

将备份复制到宿主机：

```bash
docker compose -f deploy/docker-compose.yml cp api:/app/data/backup.db ./dailykeeper-backup.db
```

恢复：停服务后把备份文件放回卷内 `dailykeeper.db`（或用 SQLite `restore`），再启动。

## 六、升级

```bash
cd DailyKeeper
git pull
docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d
```

升级前建议先执行第四节的数据备份。数据库 schema 变更随应用自动/迁移脚本处理（Alembic），不会删除已有数据。

## 七、首个账号配置流程

通过 Swagger UI（`/docs`）或 curl（示例见 [API.md](API.md)）完成：

1. **添加平台实例**：`GET /api/plugins` 确认插件已加载 → `POST /api/platforms/instances` 创建实例（填 `platform_id`、`base_url` 与实例配置）。
2. **添加账号 + 凭据**：`POST /api/accounts`，按插件 `account_schema` 提交凭据（Cookie / API Key 等），服务端 AES-GCM 加密存储。
3. **认证检查**（可选但推荐）：`POST /api/accounts/{id}/check` 验证凭据有效，失败会标记 `AUTH_EXPIRED`。
4. **创建定时任务**：`POST /api/scheduled-tasks`（`task_name` 取自插件 `task_definitions`，设置 `time_of_day` 与 `interval_days`）。
5. **验证**：`POST /api/scheduled-tasks/{id}/run-now` 立即执行一次 → `GET /api/executions` 轮询状态 → `GET /api/resources/summary` 查看资源快照。
6. 配置通知（见下一节）后，失败 / 登录失效等事件会自动推送。

## 八、通知配置

通知支持 Bark / ntfy / Gotify / 邮件（SMTP）/ Webhook 五种渠道，按事件独立开关（每日签到成功默认可选，其余异常事件默认开启）。

- 通过系统设置 API 配置：`GET /api/system/settings`（返回的 `notifications` 字段）读取，`PUT /api/system/settings/notifications` 更新渠道与事件开关（Dashboard「设置」页可视化编辑）。
- 配置后调用 `POST /api/system/notifications/test` 发送测试通知，确认渠道可达。
- 通知发送记录可在 `notifications` 数据中查看（`SENT` / `FAILED` / `SKIPPED`）。
- Dashboard「设置」页提供图形化配置界面（渠道地址 + 事件开关 + 测试发送）。

**ntfy 渠道**（手机推送最简方案）：手机安装 ntfy App（iOS / Android），订阅一个自选 topic（建议带随机后缀，如 `dk-notify-9f2k`），在 DailyKeeper 中配置同名 topic 即可；默认官方服务器 `https://ntfy.sh`，也可指向自建 ntfy；topic 开启访问控制时填访问令牌。

**邮件渠道**（SMTP）：填 SMTP 服务器/端口/账号/密码/收件人；465 端口用 SSL（默认），587 端口关闭 SSL（自动 STARTTLS）；QQ 邮箱 / Gmail 需使用授权码或应用专用密码。

## 九、M-Team 注意事项

- **API Key 获取**：M-Team 站点控制台 → 实验室 → 存取令牌（API Key），在创建账号凭据中以 `api_key` 字段提交。
- **API 访问不计入登录活跃**：因此 M-Team 的每日保活签到任务（`daily_checkin`）需要浏览器登录态，插件将其声明为 `requires_browser=True`，由 browser-worker 执行。
- **保活凭据**：创建账号时凭据字典需包含 `username` / `password` / `totp_secret`（两步验证密钥）；`api_key` 为可选，配上后 `get_user_info` 等信息查询任务可直接走 API。**首次执行会进行一次真实登录（自动填写账号密码与 TOTP）**，登录态（Cookie / localStorage）由 browser-worker 自动持久化到数据卷，后续执行直接复用会话，无需每次登录。
- 未部署 browser-worker 时，该任务会被守卫置为 `NEEDS_ACTION` 并推送「需要人工验证」通知——部署 browser-worker 后自动恢复浏览器执行。
- 用户信息、资源查询类任务（`get_user_info` 等）走 API Key 可正常执行与采集。

## 十、常见问题

| 现象 | 处理 |
| --- | --- |
| 接口返回 401 | 未登录或 token 过期：重新 `POST /api/auth/login` 获取 token；确认请求头 `Authorization: Bearer <token>` |
| 插件未加载 | `GET /api/plugins` 为空或缺少平台时，查看启动日志：`docker compose -f deploy/docker-compose.yml logs api \| grep -i plugin`；确认插件已加入镜像构建并注册 entry point |
| SQLite `database is locked` | 高并发写入时会偶发；可增大超时（连接串加 `?timeout=30`，对应 busy_timeout），或降低 `DAILYKEEPER_WORKER_CONCURRENCY`；数据量与并发上去后迁移 PostgreSQL |
| 任务时区不对 | 定时时间按平台实例的 `timezone` 字段计算业务日期；检查实例配置与 `DAILYKEEPER_TIMEZONE` |
| scheduler 未产生任务 | `GET /api/system/info` 查看 scheduler 心跳；确认 scheduled_tasks 已启用且 `time_of_day` 已过 |
| run-now 提示跳过 | 业务日期去重：同日该任务已处于 `SUCCESS` 等去重状态；`SKIPPED/FAILED/INTERRUPTED` 允许同日重跑 |
| 浏览器任务一直 `NEEDS_ACTION` | `docker compose -f deploy/docker-compose.yml ps browser-worker` 确认 browser-worker 已启动；结果消息含「未提供浏览器会话」即守卫拦截（未部署 browser-worker 所致），部署后新任务自动走浏览器执行，当日该执行可删除后 run-now 重跑 |
