# DailyKeeper 系统架构

> 本文描述 DailyKeeper V1 的总体形态、技术选型、模块边界、任务执行流程与安全边界。

## 一、总体形态

DailyKeeper 采用**模块化单体（Modular Monolith）**架构，而不是一开始就拆分微服务：清晰的模块边界 + 单一部署单元，避免前期运维成本。

- **四进程模型**：`api`（uvicorn 提供 REST API）、`scheduler`（`python -m app.scheduler`，APScheduler 定时扫描）、`worker`（`python -m app.worker`，DB 队列消费者）、`browser-worker`（`python -m app.browser_worker`，Playwright 浏览器任务执行端）。前三个进程共用同一个镜像；`browser-worker` 使用内置 Playwright + Chromium 的专用镜像（`deploy/Dockerfile.browser`），四个进程通过 SQLite 数据库队列协作。
- **SQLite 数据库队列**：APScheduler 只负责产生定时任务，任务队列与执行状态保存在 `task_executions` 表中，Worker 通过数据库事务（乐观锁 claim）领取任务，天然保证领取不重复。
- **认领分流（needs_browser / needs_agent）**：任务声明 `requires_browser=True` / `requires_agent=True` 时，创建执行即打上对应标记；普通 worker 只认领 `needs_browser=False` 且 `needs_agent=False` 的执行，browser worker 只认领 `needs_browser=True` 的执行（`claim_pending(..., browser=True/False)`），两类 Worker 天然互不抢占。Agent 通道（`needs_agent=True`）的执行不被服务器 Worker 认领，由本地 Agent 经 `claim_agent_tasks` 拉取（同样条件更新原子认领，置 RUNNING 并写 `worker_id=agent-<id>` 与 `assigned_agent_id`）。
- **三执行环境**：API 类任务（HTTP 插件）由 worker 直接执行；浏览器任务由 browser worker 执行——进程生命周期内共享一个 Chromium 实例，每次执行使用独立 Browser Context，并在执行前后按账号持久化 storage state（Cookie / localStorage，位于 `{data_dir}/browser_states/account-{id}.json`），实现登录态跨执行复用；本地 Agent 任务由用户本机（Mac / Windows / Linux）的 `dk-agent` 拉取执行（已实现，阶段 5b）。

| 执行线 | 任务标记 | 认领方 | 执行环境 |
| --- | --- | --- | --- |
| HTTP 执行线 | `needs_browser=False` 且 `needs_agent=False` | worker 进程（`claim_pending(browser=False)`） | 服务器容器内，`context.http` |
| 浏览器执行线 | `needs_browser=True` | browser-worker 进程（`claim_pending(browser=True)`） | 服务器容器内 Playwright + Chromium，`context.browser` |
| Agent 执行线 | `needs_agent=True` | 本地 Agent 拉取（`claim_agent_tasks`，`POST /api/agent/tasks/claim`） | 用户本机插件环境（`dk-agent`，插件装在 Agent 环境） |

**本地 Agent（拉取式协议，已实现）**：Agent 与服务器之间没有长连接，全部交互由 Agent 主动发 HTTP 请求完成——心跳（默认 30s，服务器可动态下调）→ 认领 → 拉取上下文 → 本地执行 → 回传结果。认证使用 `X-Agent-Token` 请求头，服务端仅保存令牌的 SHA-256 摘要（无法反查明文），支持轮换（旧令牌立即失效）与删除（删除即中断其运行中执行）。上下文接口下发**解密后的凭据**，传输层安全必须在部署层保证（生产全程 HTTPS，反向代理终止 TLS 亦可）。服务器调度器每轮扫描做离线清扫：超过 `AGENT_OFFLINE_SECONDS`（90 秒，代码常量）未心跳的 Agent 标记 OFFLINE，其 RUNNING 执行置为 INTERRUPTED 并发送 `agent_offline` 通知；Agent 侧对服务器不可达保持离线容忍（告警退避重试，不退出进程）。Agent 与服务器共享 DailyKeeper SDK，插件运行在 Agent 自身的 Python 环境中（entry points 注册，服务器不下发插件代码）。

```mermaid
sequenceDiagram
    autonumber
    participant A as 本地 Agent（dk-agent）
    participant S as 服务器（/api/agent/*）
    participant D as SQLite 数据库
    participant P as 本地插件（Agent 环境）

    A->>S: heartbeat（X-Agent-Token，默认 30s）
    S->>D: 刷新 last_heartbeat / ONLINE
    A->>S: tasks/claim
    S->>D: 原子认领 needs_agent 执行（RUNNING + agent-<id>）
    S-->>A: 到期任务列表
    A->>S: tasks/{id}/context
    S->>D: 读取配置与凭据（解密）
    S-->>A: credentials / config（必须 HTTPS）
    A->>P: 本地执行插件 plugin.execute(task_name, context)
    P-->>A: TaskResult
    A->>S: tasks/{id}/result
    S->>D: finalize（结果 / 账号状态 / 通知 / 重试）
```

## 二、技术选型

| 层级 | 技术 | 说明 |
| --- | --- | --- |
| 后端 | Python 3.12+ | 核心开发语言 |
| API | FastAPI | REST API |
| ORM | SQLAlchemy 2.x | 数据库访问 |
| 校验 | Pydantic 2.x | 配置与数据校验 |
| 调度 | APScheduler | 定时任务 |
| HTTP | HTTPX | API 请求 |
| 浏览器 | Playwright | 网页自动化（browser worker 专用镜像） |
| 数据库 | SQLite | 初期部署 |
| 迁移 | Alembic | 数据库版本管理 |
| 前端 | Vue 3 + TypeScript + Vite | Dashboard 管理界面（已交付） |
| UI | Element Plus + ECharts | 管理组件与资源趋势图（已交付） |
| 部署 | Docker Compose | 容器化 |
| 通知 | Bark / Gotify / Webhook | 消息推送 |

暂时不需要 Redis、Celery、Kubernetes。注意：Scheduler 和 Worker 必须分离运行，不能让 APScheduler 在多个 API 实例中重复调度。

## 三、系统架构图

```mermaid
flowchart LR
    subgraph client["客户端"]
        UI["Web Dashboard（Vue 3 + Element Plus）"]
        MCP["MCP 客户端\n（Claude Desktop / Code，dk-mcp）"]
    end

    subgraph server["服务器（四个进程）"]
        API["api 进程\nFastAPI / uvicorn"]
        SCH["scheduler 进程\nAPScheduler"]
        WK["worker 进程\nDB 队列消费者"]
        BW["browser-worker 进程\nPlaywright + Chromium"]
        DB[("SQLite\ndailykeeper.db")]
        ST["browser_states/\n按账号 storage state"]
    end

    subgraph runtime["Plugin Runtime（worker / browser-worker 内）"]
        PR["插件执行上下文\n（解密凭据 / HTTP 客户端 / 浏览器会话）"]
    end

    subgraph ext["外部"]
        P1["外部平台\n（M-Team / NewAPI / NexusPHP …）"]
        LA["Local Agent（dk-agent，拉取式）"]
        N["Bark / Gotify / Webhook"]
    end

    UI -->|HTTP + JWT| API
    MCP -->|HTTP + JWT| API
    SCH -->|创建执行 / 业务日期去重| DB
    WK -->|claim needs_browser=false / finalize| DB
    BW -->|claim needs_browser=true / finalize| DB
    API --> DB
    WK --> PR
    BW --> PR
    BW <-->|执行前恢复 / 执行后持久化| ST
    PR -->|HTTPX| P1
    PR -->|Playwright| P1
    LA -->|"HTTPS：heartbeat / claim / context / result（X-Agent-Token）"| API
    LA -->|本地插件执行| P1
    WK -->|通知事件| N
```

## 四、模块边界

| 模块 | 职责 |
| --- | --- |
| `backend/app/api/` | REST 路由层：认证、平台、账号、任务、执行记录、资源、系统设置的 HTTP 接口 |
| `backend/app/services/` | 业务服务层：任务引擎、凭据加解密、执行编排，被 api/scheduler/worker 复用 |
| `backend/app/models/` | SQLAlchemy ORM 表定义（唯一的数据模型来源） |
| `backend/app/scheduler/` | APScheduler 入口：扫描 scheduled_tasks，按业务日期创建 task_executions |
| `backend/app/worker/` | Worker 入口：轮询领取 PENDING 任务，调用插件执行并 finalize |
| `backend/app/browser_worker/` | Browser Worker 入口：领取 `needs_browser` 执行，共享 Chromium + 按账号 Context / storage state，调用插件执行并 finalize |
| `backend/app/notifications/` | 通知模块：Bark / Gotify / Webhook 渠道与事件开关 |
| `backend/app/services/registry_service.py` | 可信插件目录（Registry）：目录 API + 安装状态比对；不做自动安装、不执行第三方代码 |
| `local-agent/` | 本地 Agent（dk-agent）：心跳 / 认领 / 上下文 / 回传，本地插件执行 |
| `mcp-server/` | MCP Server（dk-mcp）：经 stdio 把查询与触发能力暴露给 AI 助手 |
| `frontend/` | Web Dashboard（Vue 3 + Element Plus + ECharts）：平台 / 账号 / 任务 / 执行 / 资源 / Agent / Registry / 设置 |
| `sdk/dailykeeper_sdk/` | 插件 SDK：PlatformPlugin 基类、TaskContext、TaskResult、注册表 |
| `plugins/` | 官方插件包：demo / newapi / mteam / nexusphp，经 entry points 注册 |

## 五、任务执行流程

1. **Scheduler 扫描**：scheduler 进程按固定间隔（默认 30s）扫描 `scheduled_tasks`，对到期任务计算站点时区下的 `business_date`。
2. **create_execution（业务日期去重 + needs_browser 打标）**：为该账号 + 任务 + 业务日期创建 `task_executions` 行；若已存在去重状态（`DEDUPE_STATUSES`）内的记录则跳过，保证同一天只执行一次。任务声明 `requires_browser=True` 时，执行行同时打上 `needs_browser` 标记。
3. **Worker claim（乐观锁更新 claim，按 needs_browser 分流）**：worker 进程轮询 PENDING 且到期、`needs_browser=false` 的执行记录；browser worker 只认领 `needs_browser=true` 的记录。两者都通过条件更新（乐观锁）抢占任务并写入 `worker_id`，多 worker 不会重复领取。Agent 通道（`needs_agent=true`）的执行不被两类 Worker 认领，由本地 Agent 经 `POST /api/agent/tasks/claim` 拉取（同样乐观锁，`worker_id=agent-<id>`）。
4. **Plugin Runtime 构建上下文（解密凭据）**：引擎加载该平台插件，解密 AES-GCM 凭据，组装 `TaskContext`（凭据、实例配置、base_url、HTTP 客户端、日志）；浏览器任务额外注入 `context.browser`（BrowserSession）。
5. **plugin.execute**：调用插件的 `execute(task_name, context)`，返回统一的 `TaskResult`。`requires_browser` 的任务若被普通 worker 误领（无浏览器会话），运行时守卫直接 finalize 为 `NEEDS_ACTION`，等待 browser worker 接管重跑，不会盲目执行。
6. **finalize（结果 / 账号状态 / 资源快照 / 通知 / 重试）**：保存 `task_results`；按结果更新账号状态（如 `AUTH_EXPIRED`）；持久化 `result.data["resources"]` 为资源快照；按事件开关发送通知；可重试失败按退避策略创建新的执行记录（`retries + 1`）。

**浏览器任务流程（browser worker）**：browser worker 常驻一个共享 Chromium 实例；认领到 `needs_browser` 执行后，按账号加锁，从 `{data_dir}/browser_states/account-{id}.json` 恢复 storage state 创建独立 Browser Context（已有登录态则免登录），执行插件任务；执行结束（无论成败）先把 Context 的 storage state 持久化回该文件、再关闭 Context——首次执行完成真实登录后，后续执行即可复用登录态。

## 六、执行保护机制

| 保护机制 | 说明 | V1 状态 |
| --- | --- | --- |
| 任务去重 | 同一账号、同一任务、同一业务日期只执行一次（去重状态内） | ✅ V1 实现（`ix_task_executions_dedupe` + DEDUPE_STATUSES） |
| 执行锁 | 避免同一账号同时执行多个任务 | ✅ V1 实现（claim 乐观锁 + 状态机） |
| 超时控制 | HTTP 与浏览器任务分别设置超时 | ✅ V1 实现（`task_timeout_seconds` / `http_timeout`；浏览器超时随浏览器版本） |
| 重试策略 | 网络错误可重试；签到提交成功但响应不明确时不能重复提交 | ✅ V1 实现（幂等任务才允许重试，重试为新执行行） |
| 限流控制 | 每个平台独立设置并发数和请求间隔 | 🗺 规划（V1 按平台并发规划，先以单 worker 串行保平安） |
| 任务恢复 | 服务重启后识别中断任务，判断能否安全恢复 | ✅ V1 实现（重启后 RUNNING → INTERRUPTED，允许重跑） |
| 人工接管 | 验证码、二次验证等情况进入待处理状态 | ✅ V1 实现（`NEEDS_ACTION` 状态 + 通知） |

## 七、数据流与安全边界

- **凭据加密**：Cookie / 密码 / API Key 使用 AES-GCM 加密存储，密文带 `enc1:` 版本前缀；加密密钥来自 `DAILYKEEPER_SECRET_KEY`（或独立的 `DAILYKEEPER_ENCRYPTION_KEY`），支持密钥轮换。
- **浏览器登录态文件**：browser worker 按账号持久化的 storage state（`browser_states/account-{id}.json`）包含 Cookie / localStorage，属于敏感数据，只落在 `data_dir` 数据卷内，不进入数据库、不出现在日志与 API 响应中。
- **日志脱敏**：任务记录与日志不落明文凭据，错误信息经过滤后入库。
- **管理端认证**：API 使用 JWT 管理员认证（`/api/auth/login`），`/healthz` 等探活端点公开。管理端支持多用户（users 表，PBKDF2 口令哈希；启动时自动从环境变量/旧 admin_auth 设置迁移种子管理员；用户停用/删除后其 JWT 立即失效）。
- **插件白名单**：V1 仅加载随镜像分发的官方插件（demo / newapi / mteam / nexusphp），即「可信插件白名单」；插件之间不共享认证信息。
- **不绕过平台安全措施**：不自动处理验证码，不自动绕过二次验证，需要人工的场景统一进入 `NEEDS_ACTION`。

## 八、后续演进

- **Agent 浏览器 / 桌面自动化能力**：本地 Agent 基础链路（心跳 / 认领 / 上下文 / 回传）已于阶段 5 交付；Agent 当前上报能力为 `["http"]`（`context.http` 可用），浏览器会话（`context.browser`）与桌面自动化待后续版本提供（WorkBuddy 适配前先核实官方支持能力）。
- **插件生态扩展**：Registry V1 为可信白名单目录（只读比对、不执行第三方代码）；后续再评估第三方插件的分发与安装流程。
- **Redis / Celery**：并发量明显增加后再替换 SQLite 队列。
- **PostgreSQL**：多实例部署或数据量增长后迁移，ORM 层已按可移植性编写。
- **Alembic 迁移管理**：Alembic 已引入，后续 schema 变更统一走迁移脚本而非建表脚本。
