# DailyKeeper Agent（阶段 5b）

DailyKeeper 本地执行端（Mac / Windows / Linux 守护进程）。与服务器共享
DailyKeeper SDK，通过 HTTPS 与服务器通信，把「需要本地环境执行」的任务
（`requires_agent`）拉到本机，调用本地安装的平台插件执行后回传结果。

典型场景：WorkBuddy 等只在用户本机可访问的平台签到/查询（见下方 WorkBuddy 说明）。

## 安装

需要 Python 3.12+，在仓库根目录创建虚拟环境并安装 SDK、插件与 Agent：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ../sdk -e ../plugins/demo -e ./local-agent
# 按需安装其他平台插件，例如：
# pip install -e ../plugins/workbuddy
```

> 平台插件来自 Agent **自身的 Python 环境**（entry points 组
> `dailykeeper.plugins`）。服务器不会下发插件代码——本机没装的插件任务
> 会以 FAILED（“本地未安装平台插件: xxx"）回传。

## 配置

| 环境变量 | 说明 | 默认值 |
| --- | --- | --- |
| `DK_AGENT_SERVER` | 服务器地址（如 `https://dk.example.com`） | 必填 |
| `DK_AGENT_TOKEN` | Agent 令牌 | 必填 |
| `DK_AGENT_POLL_SECONDS` | 空轮询间隔（秒） | `5` |
| `DK_AGENT_HEARTBEAT_SECONDS` | 心跳间隔（秒），服务器可动态下调 | `30` |
| `DK_AGENT_TASK_CONCURRENCY` | 并发执行任务数 | `2` |
| `DK_AGENT_VERIFY_TLS` | 是否校验 TLS 证书（`0`/`false` 关闭，仅调试用） | `1` |
| `DK_AGENT_TIMEOUT_SECONDS` | 单任务执行超时（秒） | `300` |

缺少必填项时报错：`缺少 DK_AGENT_SERVER 或 DK_AGENT_TOKEN 环境变量`。
也可用 CLI 参数覆盖：`dk-agent --server URL --token TOKEN [--poll 10]`。

**令牌获取**：由服务器管理员调用管理 API `POST /api/agents`
（body `{"name": "我的 Mac"}`）创建，响应中的 `token` **仅显示一次**，
请立即配置到 Agent 环境；泄露后可调用 `POST /api/agents/{id}/rotate` 轮换。

## 运行

```bash
dk-agent                       # 控制台脚本（打印启动横幅：服务器地址 + 已加载插件）
python -m dailykeeper_agent    # 等价入口
```

启动后常驻运行，`Ctrl+C` 优雅退出。

## 工作原理

```
┌────────────┐  ①心跳(30s)   ┌─────────────┐
│            │ ────────────► │             │
│ 本地 Agent │  ②认领任务     │  DK 服务器   │
│ (dk-agent) │ ◄──────────── │             │
│            │  ③执行上下文   │             │  Agent 令牌认证
│  本地插件   │ ◄──────────── │             │  (X-Agent-Token)
│  demo/...  │  (含解密凭据)  │             │
│            │ ────────────► │             │
└────────────┘  ④回传结果     └─────────────┘
```

1. **心跳**：上报版本与能力（当前 `["http"]`，浏览器能力后续提供），服务器
   按心跳窗口判定在线/离线；
2. **认领**：批量拉取（单次最多 5 个）到期的 Agent 通道任务，服务器原子
   置为 RUNNING 并绑定到本 Agent；
3. **取上下文**：按执行记录拉取合并后的配置与**解密后的凭据**（经 HTTPS
   下发，仅在响应中出现，服务器日志不记录）；
4. **本地执行**：`AgentRunner` 在本机插件环境中构建 `TaskContext`
   （每次执行独立 `HttpClient`，用后即关），受超时保护执行插件任务；
   插件异常时回传消息会先做**凭据脱敏**（≥8 字符的凭据值替换为 `***`）；
5. **回传结果**：`POST /api/agent/tasks/{id}/result` 终结执行，管理端
   执行历史立即可见。

服务器暂时不可达时 Agent 仅告警并每 5 秒重试，**不会退出**；单个任务的
任何失败都不会中断主循环。

## 安全注意

- **令牌保管**：令牌等同 Agent 身份，只放环境变量/密管工具，不要入库、
  不要写进 shell 历史与日志；怀疑泄露立即 rotate；
- **必须 HTTPS**：执行上下文包含解密后的账号凭据，生产部署务必全程
  TLS（反向代理终止也可），否则凭据明文过网；
- **凭据仅驻留内存**：Agent 不落盘任何凭据，任务结束即随上下文回收；
- **离线容忍**：断网期间 Agent 空转等待，服务器侧离线清扫会中断长期
  失联 Agent 的运行中任务，Agent 重连后可继续认领新任务；
- **插件可信边界**：插件代码在本机以当前用户权限运行，只安装可信来源
  的插件包。

## WorkBuddy 说明

WorkBuddy 平台（每日签到 / 账户状态）按规划在本地 Agent 环境执行。
插件适配器**待真实站点核实后开发**（站点名称 ≠ 接口标准，需先确认实际
签到入口与鉴权方式），架构与阶段划分见 `docs/ARCHITECTURE.md`。

## 测试

Agent 的测试与后端测试同套件运行（复用真实 ASGI 应用与 demo 插件）：

```bash
python -m pytest backend/tests/test_local_agent.py -q   # 仅 Agent 用例
python -m pytest backend/tests -q                        # 全量
```

覆盖：配置缺失报错、令牌认证（401 → RuntimeError 带 detail）、心跳/认领/
上下文/回传完整闭环（真实 demo 插件 `agent_probe`）、插件异常凭据脱敏、
任务超时（FAILED + 不可重试）、插件/任务缺失兜底。
