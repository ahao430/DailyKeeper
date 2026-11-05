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

# 4. 构建并启动（api / scheduler / worker 三进程）
docker compose -f deploy/docker-compose.yml up -d --build

# 5. 验证
curl http://127.0.0.1:8000/healthz
# 浏览器打开 Swagger UI：http://<host>:8000/docs
```

部署内容：

- **api**：uvicorn，对外暴露 `8000` 端口，带 healthcheck（`/healthz`，30s 间隔）。
- **scheduler**：`python -m app.scheduler`，APScheduler 定时扫描并创建任务执行。
- **worker**：`python -m app.worker`，从数据库队列领取并执行任务。
- 三个服务共用同一镜像（`deploy/Dockerfile.backend`，scheduler/worker 通过 `command` 覆盖启动命令），并挂载同一个数据卷 `dk-data:/app/data`。

**默认管理员**：`admin / admin123`（来自环境变量）。**首次登录后请立即通过 `PUT /api/auth/password` 修改密码。**

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
| `DAILYKEEPER_CORS_ORIGINS` | `*` | CORS 允许来源（接入 Dashboard 后收紧） |

## 三、数据持久化与备份

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

## 四、升级

```bash
cd DailyKeeper
git pull
docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d
```

升级前建议先执行第三节的数据备份。数据库 schema 变更随应用自动/迁移脚本处理（Alembic），不会删除已有数据。

## 五、首个账号配置流程

通过 Swagger UI（`/docs`）或 curl（示例见 [API.md](API.md)）完成：

1. **添加平台实例**：`GET /api/plugins` 确认插件已加载 → `POST /api/platforms/instances` 创建实例（填 `platform_id`、`base_url` 与实例配置）。
2. **添加账号 + 凭据**：`POST /api/accounts`，按插件 `account_schema` 提交凭据（Cookie / API Key 等），服务端 AES-GCM 加密存储。
3. **认证检查**（可选但推荐）：`POST /api/accounts/{id}/check` 验证凭据有效，失败会标记 `AUTH_EXPIRED`。
4. **创建定时任务**：`POST /api/scheduled-tasks`（`task_name` 取自插件 `task_definitions`，设置 `time_of_day` 与 `interval_days`）。
5. **验证**：`POST /api/scheduled-tasks/{id}/run-now` 立即执行一次 → `GET /api/executions` 轮询状态 → `GET /api/resources/summary` 查看资源快照。
6. 配置通知（见下一节）后，失败 / 登录失效等事件会自动推送。

## 六、通知配置

通知支持 Bark / Gotify / Webhook 三种渠道，按事件独立开关（每日签到成功默认可选，其余异常事件默认开启）。

- 通过系统设置 API 配置：`GET /api/system/notifications` 读取，`PUT /api/system/notifications` 更新渠道地址与事件开关。
- 配置后调用 `POST /api/system/notifications/test` 发送测试通知，确认渠道可达。
- 通知发送记录可在 `notifications` 数据中查看（`SENT` / `FAILED` / `SKIPPED`）。
- 后续 Dashboard（阶段 4）将提供图形化配置界面。

## 七、M-Team 注意事项

- **API Key 获取**：M-Team 站点控制台 → 实验室 → 存取令牌（API Key），在创建账号时以 `api_key` 凭据类型提交。
- **API 访问不计入登录活跃**：因此 M-Team 的每日签到任务（`daily_checkin`）需要浏览器登录态，插件将其声明为 `requires_browser=True`。在浏览器自动化版本发布前，该任务会持续返回 `NEEDS_ACTION` 并推送「需要人工验证」通知——这是预期行为。
- 用户信息、资源查询类任务（`get_user_info` 等）走 API Key 可正常执行与采集。

## 八、常见问题

| 现象 | 处理 |
| --- | --- |
| 接口返回 401 | 未登录或 token 过期：重新 `POST /api/auth/login` 获取 token；确认请求头 `Authorization: Bearer <token>` |
| 插件未加载 | `GET /api/plugins` 为空或缺少平台时，查看启动日志：`docker compose -f deploy/docker-compose.yml logs api \| grep -i plugin`；确认插件已加入镜像构建并注册 entry point |
| SQLite `database is locked` | 高并发写入时会偶发；可增大超时（连接串加 `?timeout=30`，对应 busy_timeout），或降低 `DAILYKEEPER_WORKER_CONCURRENCY`；数据量与并发上去后迁移 PostgreSQL |
| 任务时区不对 | 定时时间按平台实例的 `timezone` 字段计算业务日期；检查实例配置与 `DAILYKEEPER_TIMEZONE` |
| scheduler 未产生任务 | `GET /api/system/info` 查看 scheduler 心跳；确认 scheduled_tasks 已启用且 `time_of_day` 已过 |
| run-now 提示跳过 | 业务日期去重：同日该任务已处于 `SUCCESS` 等去重状态；`SKIPPED/FAILED/INTERRUPTED` 允许同日重跑 |
