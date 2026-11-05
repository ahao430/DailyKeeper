# DailyKeeper REST API 说明

> 管理端 API 全部要求 JWT 管理员认证（`Authorization: Bearer <token>`），仅 `/healthz`、`/api/auth/login`、`/api/auth/bootstrap` 公开。交互式文档：部署后访问 `http://<host>:8000/docs`（Swagger UI），以运行实例的 OpenAPI 为准。

## 一、端点一览

### 系统

| 方法 | 路径 | 认证 | 说明 |
| --- | --- | --- | --- |
| GET | `/healthz` | 公开 | 健康检查（容器 healthcheck 使用） |
| GET | `/api/system/info` | 需要 | 系统信息：版本、环境、插件数量、调度器心跳、在线 Agent 数（`agents_online`）等 |
| GET | `/api/system/settings` | 需要 | 读取系统设置 |
| PUT | `/api/system/settings` | 需要 | 更新系统设置（JSON 合并写入） |
| GET | `/api/system/notifications` | 需要 | 读取通知渠道与事件开关配置 |
| PUT | `/api/system/notifications` | 需要 | 更新 Bark / Gotify / Webhook 配置与事件开关 |
| POST | `/api/system/notifications/test` | 需要 | 发送测试通知，验证渠道配置 |

### 认证

| 方法 | 路径 | 认证 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/auth/login` | 公开 | 管理员登录，返回 JWT access token |
| POST | `/api/auth/bootstrap` | 公开 | 首次初始化管理员（仅在尚未设置管理员时可用） |
| GET | `/api/auth/me` | 需要 | 当前登录管理员信息 |
| PUT | `/api/auth/password` | 需要 | 修改管理员密码 |

### 插件与平台

| 方法 | 路径 | 认证 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/plugins` | 需要 | 已加载插件清单（manifest：config_schema / account_schema / task_definitions） |
| GET | `/api/platforms` | 需要 | 平台列表（插件注册的 platform 定义） |
| GET | `/api/platforms/instances` | 需要 | 平台实例列表（含账号数） |
| POST | `/api/platforms/instances` | 需要 | 创建平台实例（platform_id + name + base_url + config） |
| PATCH | `/api/platforms/instances/{instance_id}` | 需要 | 更新平台实例 |
| DELETE | `/api/platforms/instances/{instance_id}` | 需要 | 删除平台实例（须先删除其下账号） |

### 账号与凭据

| 方法 | 路径 | 认证 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/accounts` | 需要 | 账号列表（支持按实例过滤） |
| POST | `/api/accounts` | 需要 | 创建账号（同一请求内提交凭据，服务端 AES-GCM 加密存储） |
| PATCH | `/api/accounts/{account_id}` | 需要 | 更新账号（含替换凭据） |
| DELETE | `/api/accounts/{account_id}` | 需要 | 删除账号及其凭据、任务配置 |
| POST | `/api/accounts/{account_id}/check` | 需要 | 认证检查：调用插件 auth 任务，按结果更新账号状态（AUTH_EXPIRED 等） |

### 定时任务

| 方法 | 路径 | 认证 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/scheduled-tasks` | 需要 | 定时任务列表（支持按账号过滤） |
| POST | `/api/scheduled-tasks` | 需要 | 创建定时任务（task_name 须在该平台插件的 task_definitions 中） |
| PUT | `/api/scheduled-tasks/{task_id}` | 需要 | 更新定时任务（时间/间隔/参数/启用，next_run_at 重置重算） |
| DELETE | `/api/scheduled-tasks/{task_id}` | 需要 | 删除定时任务（执行历史保留，关联引用置空） |
| POST | `/api/scheduled-tasks/{task_id}/run-now` | 需要 | 立即执行一次（创建 execution，遵循业务日期去重） |

### 执行记录

| 方法 | 路径 | 认证 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/executions` | 需要 | 执行记录列表（分页，支持按账号/任务/状态过滤） |
| GET | `/api/executions/{execution_id}` | 需要 | 执行详情（含 task_results 结构化结果与 metrics） |

> 端点无变化：执行列表/详情的条目新增 `needs_browser` 布尔字段，标记该执行是否需要浏览器自动化（由 browser-worker 认领执行）。 |

### 资源

| 方法 | 路径 | 认证 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/resources` | 需要 | 资源快照列表（支持按账号/类型/时间过滤） |
| GET | `/api/resources/summary` | 需要 | 资源汇总：每账号每资源类型的最新值 |

### Agent 管理（本地 Agent 注册/令牌）

| 方法 | 路径 | 认证 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/agents` | 需要 | Agent 列表：status / version / last_heartbeat / `online`（心跳新鲜度，90 秒窗口）/ running_tasks 等 |
| POST | `/api/agents` | 需要 | 注册 Agent 并生成令牌；**令牌仅在本次响应中明文返回一次**（服务端只存 SHA-256 摘要） |
| DELETE | `/api/agents/{agent_id}` | 需要 | 删除 Agent：其运行中执行标记 INTERRUPTED（附失败结果），历史执行保留、Agent 引用置空 |
| POST | `/api/agents/{agent_id}/rotate` | 需要 | 轮换令牌：旧令牌立即失效，新令牌仅返回一次 |

### Agent 专用接口（`X-Agent-Token`）

这组端点**不使用管理员 JWT**，凭 `X-Agent-Token` 请求头认证（令牌缺失/无效统一返回 401）。请求/响应示例见第四节。

| 方法 | 路径 | 认证 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/agent/heartbeat` | Agent 令牌 | 心跳上线：上报版本与能力列表，返回心跳间隔（30s）与服务器时间 |
| POST | `/api/agent/tasks/claim` | Agent 令牌 | 认领到期的 Agent 通道执行（`limit` 1–5，默认 2；PENDING → RUNNING，绑定该 Agent） |
| GET | `/api/agent/tasks/{execution_id}/context` | Agent 令牌 | 执行上下文：合并配置、base_url 与**解密后的凭据**（生产必须 HTTPS） |
| POST | `/api/agent/tasks/{execution_id}/result` | Agent 令牌 | 回传结果并终结执行；迟到结果（如已被离线清扫置 INTERRUPTED）仍可上报并覆盖状态 |

> 归属规则：context / result 仅允许认领该执行的 Agent 访问——其他 Agent（即使令牌有效）返回 **403**；执行记录不存在返回 404。

## 二、curl 完整流程示例

以下示例演示完整链路：登录 → 创建平台实例 → 创建账号（含凭据）→ 创建定时任务 → run-now → 轮询执行记录 → 资源汇总。

```bash
BASE=http://127.0.0.1:8000

# 1. 登录，获取 token（默认管理员 admin / admin123，首次登录后请修改密码）
TOKEN=$(curl -s -X POST "$BASE/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

echo "$TOKEN"

# 2. 查看已加载插件，确认目标平台存在（例如 newapi）
curl -s "$BASE/api/plugins" -H "Authorization: Bearer $TOKEN"

# 3. 创建平台实例（platform_id 来自插件 manifest）
curl -s -X POST "$BASE/api/platforms/instances" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "platform_id": "newapi",
    "name": "我的中转站",
    "base_url": "https://api.example.com",
    "config": {}
  }'

# 4. 创建账号并提交凭据（凭据字段以插件 account_schema 为准，服务端加密存储）
curl -s -X POST "$BASE/api/accounts" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "instance_id": 1,
    "name": "main",
    "display_name": "主账号",
    "credential": {"kind": "cookie", "data": {"cookie": "session=xxxx"}}
  }'

# 5. 创建定时任务（task_name 须在插件 task_definitions 中；default_time 见插件声明）
curl -s -X POST "$BASE/api/scheduled-tasks" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "account_id": 1,
    "task_name": "daily_checkin",
    "time_of_day": "08:30",
    "interval_days": 1
  }'

# 6. 立即执行一次（受业务日期去重约束：同日已 SUCCESS 会被跳过）
curl -s -X POST "$BASE/api/scheduled-tasks/1/run-now" \
  -H "Authorization: Bearer $TOKEN"

# 7. 轮询执行记录，观察状态流转（PENDING → RUNNING → SUCCESS / FAILED / …）
curl -s "$BASE/api/executions?account_id=1&page=1&page_size=20" \
  -H "Authorization: Bearer $TOKEN"

# 8. 查看执行详情（含 task_results）
curl -s "$BASE/api/executions/1" -H "Authorization: Bearer $TOKEN"

# 9. 资源汇总（每账号每资源类型的最新快照值）
curl -s "$BASE/api/resources/summary" -H "Authorization: Bearer $TOKEN"
```

## 三、注意事项

- 所有时间在响应中为 naive UTC；`business_date` 按平台实例时区计算，请勿自行换算后比对。
- 凭据仅在接受创建/更新请求时提交一次，任何接口都不会返回明文凭据。
- `run-now` 与定时调度共用幂等去重：同一 `(account_id, task_name, business_date)` 在去重状态内不会重复执行。
- 认证失败返回 401 时，请重新登录获取 token；token 有效期默认 1440 分钟。
