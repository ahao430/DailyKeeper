# DailyKeeper 数据库设计

> DailyKeeper 使用 SQLite 起步（`sqlite+aiosqlite`，默认路径 `./data/dailykeeper.db`），ORM 定义见 `backend/app/models/tables.py`。所有时间字段存储 **naive UTC**；`business_date` 按平台实例配置的站点时区计算（见 `app.core.timeutil`）。PostgreSQL 就绪：表结构按可移植性编写，迁移管理使用 Alembic。

## 一、表一览

| 表 | 用途 |
| --- | --- |
| `platforms` | 已注册的平台插件（plugin 目录/镜像） |
| `platform_instances` | 平台的具体部署实例（站点 URL + 配置） |
| `accounts` | 平台账号 |
| `credentials` | 加密凭据（每账号一条） |
| `scheduled_tasks` | 定时任务配置 |
| `task_executions` | 任务执行记录（队列 + 历史） |
| `task_results` | 结构化执行结果（1:1 挂在 execution 上） |
| `resource_snapshots` | 资源快照（余额/积分/额度等） |
| `notifications` | 通知发送记录 |
| `system_settings` | 系统级 KV 设置（JSON） |
| `agents` | 本地 Agent 注册表（拉取式执行通道） |
| `users` | 管理端用户（多管理员，PBKDF2 口令哈希） |

## 二、表结构说明

### platforms

已注册的平台插件，`id` 即 `plugin_id`（主键）。由服务启动时从插件注册表同步。

- `id` (String(64), PK)、`name`、`version`、`description`
- `auth_types` / `config_schema` / `account_schema` / `credential_schema` / `task_definitions` (JSON) — 插件声明的能力与表单 Schema
- `enabled`、`source`（`entry_point`）

### platform_instances

一个平台的一次具体部署：同一插件可添加多个实例（例如多个 NewAPI 中转站）。

- `id` (PK, 自增)、`platform_id` (FK → platforms.id)
- `name`、`base_url`、`config` (JSON)、`timezone`（默认 `Asia/Shanghai`，用于计算业务日期）、`description`、`enabled`

### accounts

平台账号，归属某个平台实例；一个实例可挂多个账号。

- `id` (PK)、`instance_id` (FK → platform_instances.id)
- `name`、`display_name`、`status`：`ACTIVE` / `AUTH_EXPIRED` / `DISABLED`

### credentials

登录凭据，每账号一条（`account_id` 唯一）。

- `id` (PK)、`account_id` (FK, unique)
- `kind`：凭据类型（如 `cookie`、`api_key`、`password`）
- `data_encrypted` (Text)：AES-GCM 加密密文，带 `enc1:` 版本前缀；密钥来自 `DAILYKEEPER_SECRET_KEY` 或 `DAILYKEEPER_ENCRYPTION_KEY`

### scheduled_tasks

定时任务配置，每账号每任务名一条。

- `id` (PK)、`account_id` (FK → accounts.id)、`task_name`
- `time_of_day` (String(5)，如 `08:30`)、`interval_days` (默认 1，每日)
- `params` (JSON)、`enabled`、`next_run_at`、`last_run_at`
- 约束：`uq_scheduled_tasks_account_task` (account_id, task_name)

### task_executions

一次任务执行尝试 = 一行；同时充当 Worker 的任务队列。

- `id` (PK)、`account_id` (FK)、`scheduled_task_id` (FK, 可空 — run-now 手动触发时为空)、`task_name`
- `business_date` (Date)：站点时区下的业务日期，幂等去重依据
- `status`：`PENDING` / `RUNNING` / `SUCCESS` / `FAILED` / `SKIPPED` / `INTERRUPTED` / `AUTH_EXPIRED` / `NEEDS_ACTION` / `RATE_LIMITED`
- `params` (JSON)、`retries`、`worker_id`、`due_at`、`started_at`、`finished_at`
- `needs_browser` / `needs_agent` (Boolean, 默认 false) — 执行线标记（创建执行时按插件任务声明打标，决定认领方）
- `assigned_agent_id` (FK → agents.id, 可空) — Agent 执行线认领的 Agent
- 索引：`ix_task_executions_status_due` (status, due_at) — Worker 领取任务；`ix_task_executions_dedupe` (account_id, task_name, business_date) — 幂等去重

**去重与重试语义**：

- `DEDUPE_STATUSES = PENDING / RUNNING / SUCCESS / AUTH_EXPIRED / NEEDS_ACTION` — 处于这些状态时，同一 `(account_id, task_name, business_date)` 不再创建新执行。
- `SKIPPED / FAILED / INTERRUPTED` 允许同日重跑（例如失败后手动重试）。
- 重试不覆盖原记录：创建一条新 execution 行，`retries + 1`，保留完整执行历史。

### task_results

结构化结果载荷，与 execution 一对一（`execution_id` 唯一）。

- `id` (PK)、`execution_id` (FK, unique)
- `success` (Boolean)、`status`、`message` (Text)
- `data` (JSON)：含 `resources` 资源快照协议载荷
- `metrics` (JSON)：耗时等指标

### resource_snapshots

账号在某个时间点的资源观测值，来源为任务的 `result.data["resources"]`。

- `id` (PK)、`account_id` (FK)、`execution_id` (FK, 可空)
- `resource_type`：`balance` / `points` / `quota` / `usage` / `bonus` / `upload` / `download` / `share_rate` 等
- `value` (Numeric(18,4), 可空) — 数值型；`text_value` (String(128), 可空) — 非数值型（如重置时间、等级名）
- `unit`、`observed_at`、`source`

### notifications

通知模块的发送记录，与执行逻辑解耦。

- `id` (PK)、`event`（事件名）、`title`、`body`
- `channels` (JSON)：实际使用的渠道（bark / gotify / webhook）
- `status`：`SKIPPED` / `SENT` / `FAILED`（SKIPPED 表示事件开关关闭）

### system_settings

系统级 KV 设置，`key` 为主键，`value` 为 JSON。

- `notifications` — 通知渠道与事件开关配置
- `admin_auth` — 旧版单管理员配置（已由 users 表取代，仅作为首次迁移种子来源保留）
- `password_changed` — 是否已修改默认口令（bootstrap 提示用）
- `scheduler_heartbeat` — scheduler 进程心跳（用于健康自检）

### agents

本地 Agent 注册表（拉取式执行通道，阶段 5b 已实现）。

- `id` (PK)、`name` (unique)、`token_hash`（令牌仅存 SHA-256 摘要，明文只在创建/轮换响应中出现一次）
- `status`：`ONLINE` / `OFFLINE`（超过 90 秒无心跳判定离线并中断其运行中任务）、`last_heartbeat`、`version`、`meta` (JSON：能力列表等)
- 关联：`task_executions.assigned_agent_id` → 本表；删除 Agent 会中断其运行中执行，历史引用置空

### users

管理端用户（多管理员）。登录校验与 JWT 解析均走本表；停用/删除用户后其已有 JWT 立即失效。

- `id` (PK)、`username` (unique)、`password_hash`（PBKDF2-SHA256）
- `display_name`、`role`（当前均为 `admin`）、`enabled`
- `last_login_at`、`created_at`
- 首次启动时从 `DAILYKEEPER_ADMIN_USERNAME` / `DAILYKEEPER_ADMIN_PASSWORD`（或旧 `admin_auth` 设置中的口令哈希）迁移种子管理员

## 三、关系图

```mermaid
erDiagram
    platforms ||--o{ platform_instances : "platform_id"
    platform_instances ||--o{ accounts : "instance_id"
    accounts ||--o| credentials : "account_id (unique)"
    accounts ||--o{ scheduled_tasks : "account_id"
    accounts ||--o{ task_executions : "account_id"
    scheduled_tasks ||--o{ task_executions : "scheduled_task_id (可空)"
    task_executions ||--o| task_results : "execution_id (unique)"
    task_executions ||--o{ resource_snapshots : "execution_id (可空)"
    accounts ||--o{ resource_snapshots : "account_id"
    agents ||--o{ task_executions : "assigned_agent_id (可空)"

    platforms {
        string id PK
        string name
        json task_definitions
    }
    platform_instances {
        int id PK
        string platform_id FK
        string base_url
        string timezone
    }
    accounts {
        int id PK
        int instance_id FK
        string status
    }
    credentials {
        int id PK
        int account_id FK,unique
        string kind
        text data_encrypted
    }
    scheduled_tasks {
        int id PK
        int account_id FK
        string task_name
        string time_of_day
        int interval_days
    }
    task_executions {
        int id PK
        int account_id FK
        string task_name
        date business_date
        string status
        int retries
    }
    task_results {
        int id PK
        int execution_id FK,unique
        bool success
        string status
        json data
    }
    resource_snapshots {
        int id PK
        int account_id FK
        string resource_type
        numeric value
        string text_value
    }
    agents {
        int id PK
        string name UK
        string token_hash
        string status
        datetime last_heartbeat
    }
    users {
        int id PK
        string username UK
        string password_hash
        bool enabled
    }
```

## 四、与 plan.md 的差异说明

- **task_definitions 不建独立表**：插件任务定义序列化存储在 `platforms.task_definitions` JSON 列中（随插件 manifest 同步），V1 从简未建独立表；后续如需按任务维度建立外键关系再拆表。
- **plan.md 的 task_results 与 task_executions 分表保留**：执行记录（队列语义、可重试多行）与结果载荷（1:1 结构化数据）分开存储，避免大 JSON 拖慢队列扫描。

## 五、关键索引与约束

| 名称 | 位置 | 作用 |
| --- | --- | --- |
| `uq_scheduled_tasks_account_task` | scheduled_tasks (account_id, task_name) | 同一账号同一任务只有一条定时配置 |
| `ix_task_executions_status_due` | task_executions (status, due_at) | Worker 高效扫描待领取任务 |
| `ix_task_executions_dedupe` | task_executions (account_id, task_name, business_date) | 业务日期幂等去重 |
| `credentials.account_id` UNIQUE | credentials | 每账号恰好一条凭据 |
| `task_results.execution_id` UNIQUE | task_results | 结果与执行一一对应 |
| `agents.name` UNIQUE | agents | Agent 名称唯一 |
| `task_executions.assigned_agent_id` FK | task_executions → agents | Agent 执行线归属（删除 Agent 时置空） |
| `users.username` UNIQUE | users | 用户名唯一 |
| `system_settings.key` PK | system_settings | 设置键唯一 |
