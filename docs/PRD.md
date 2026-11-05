# DailyKeeper PRD（产品需求文档）

> DailyKeeper 是一个自托管的多平台自动化平台：统一管理多平台账号凭据，自动执行每日签到等例行任务，采集余额/积分/额度等资源数据，并通过 Bark / Gotify / Webhook 推送通知。
>
> 本文描述 V1 的产品定位、功能边界与验收标准。系统架构见 [ARCHITECTURE.md](ARCHITECTURE.md)，数据库设计见 [DATABASE.md](DATABASE.md)，接口清单见 [API.md](API.md)。

## 一、项目定位与目标

DailyKeeper 解决四类问题：

| 类别 | 说明 |
| --- | --- |
| 账号维护 | 不同平台的登录状态、Cookie、认证凭据统一管理 |
| 日常任务 | 自动签到、每日领取、积分任务、状态检查 |
| 资源管理 | 余额、积分、模型额度、用量、重置时间等数据采集与统计 |
| 自动化执行 | 根据平台能力自动选择 API、浏览器或本地 Agent 执行 |

产品形态：模块化单体后端 + 插件体系 + Docker 一键部署。平台名称不等于接口标准——每个平台由独立插件适配，核心任务引擎不因新增平台而修改。

## 二、首批接入平台

| 平台 | 首批任务 | 执行环境 |
| --- | --- | --- |
| M-Team | 登录检查、每日签到、用户信息 | Ubuntu（服务器） |
| NewAPI 中转站 | 签到、余额、用量 | Ubuntu（服务器） |
| NexusPHP 站点 | 登录、签到、积分查询 | Ubuntu（服务器） |
| WorkBuddy | 每日签到、账户状态 | Mac / Windows（Local Agent，后续版本） |
| 其他 AI 平台 | 签到、额度、权益 | 按平台决定 |

> 完整平台清单与优先级排序原则见 plan.md §1.2（其他 PT 站、智谱 Coding Plan 等按同样插件模式接入）。

**首批平台实施状态**：demo 插件已验证「插件 → 引擎 → 执行记录 → 资源快照 → 通知」的完整闭环；M-Team、NewAPI、NexusPHP 插件已随仓库提供。真实站点的执行验证需要用户在部署后配置真实凭据进行，操作指引见 [README](../README.md) 与 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 三、V1 功能边界

### 3.1 V1 必须实现

- 多平台管理。
- 每个平台支持多个账号。
- 登录状态管理。
- Cookie 和认证信息持久化（AES-GCM 加密存储）。
- 每日任务调度（独立 Scheduler 进程 + 数据库队列 + Worker 进程）。
- 任务执行记录（含按业务日期的幂等去重）。
- 余额、积分、额度等数据采集（资源快照）。
- Bark、Gotify、Webhook 通知。
- 插件注册和扩展（SDK + Entry Points）。
- Docker 部署（docker compose 一键部署）。

### 3.2 已交付（阶段 4–5）

- Web Dashboard 前端（阶段 4）：六页管理界面 + 插件动态表单。
- 浏览器自动化执行线（阶段 5a）：Playwright browser worker + 会话持久化（M-Team 保活）。
- 本地 Agent（阶段 5b）：拉取式协议（心跳 / 认领 / 上下文 / 回传），令牌轮换与离线清扫。
- MCP Server（dk-mcp）：AI 助手接入（查询状态 / 触发任务 / 资源查询）。
- 插件目录 Registry V1（可信白名单目录 + 安装状态比对，不自动执行第三方代码）。
- 多用户管理 V1：多管理员账号（创建/停用/删除/重置密码，令牌随停用即时失效）。

### 3.3 后续版本

- Agent 浏览器 / 桌面自动化能力（WorkBuddy 适配）。
- 复杂任务工作流。
- 数据趋势分析。
- 更多桌面软件自动化。

## 四、通知事件

| 事件 | 默认通知 |
| --- | --- |
| 每日签到成功 | 可选 |
| 签到失败 | 是 |
| 登录失效 | 是 |
| 需要人工验证 | 是 |
| 余额低于阈值 | 是 |
| Agent 离线 | 是 |
| 任务执行异常 | 是 |

通知按事件独立开关，避免每天大量成功消息造成干扰；后续支持按平台配置。

## 五、V1 验收标准

| 验收项目 | 标准 | 状态 |
| --- | --- | --- |
| 平台管理 | 能添加多个不同类型平台 | ✅ 已实现：`/api/platforms` 展示插件注册的平台定义，平台实例支持增删改查 |
| 多账号 | 每个平台能管理多个账号 | ✅ 已实现：每个平台实例可挂载多个账号，账号与凭据独立管理 |
| 插件机制 | 新增插件不修改核心任务引擎 | ✅ 已实现：插件通过 entry point group `dailykeeper.plugins` 注册，引擎按 TaskDefinition 通用调度 |
| 认证管理 | 能保存和检测认证状态 | ✅ 已实现：凭据 AES-GCM（`enc1:`）加密存储，账号 check 接口检测登录状态并更新 AUTH_EXPIRED |
| 自动任务 | 支持每日定时任务 | ✅ 已实现：scheduled_tasks（time_of_day + interval_days）+ APScheduler + 独立 Worker 进程 |
| 任务安全 | 重复执行有幂等保护 | ✅ 已实现：account_id + task_name + business_date 去重索引，DEDUPE 状态内禁止同日重跑 |
| 执行记录 | 每次任务都有完整记录 | ✅ 已实现：task_executions / task_results 记录状态、消息、data、metrics |
| 资源统计 | 支持余额、积分、额度等 | ✅ 已实现：resource_snapshots（value + text_value，balance/points/quota/usage 等）与汇总接口 |
| 通知 | 失败和人工验证能通知 | ✅ 已实现：Bark / Gotify / Webhook 渠道，notifications 表记录发送结果，提供 test 接口 |
| 部署 | Docker Compose 一键部署 | ✅ 已实现：`deploy/docker-compose.yml`（api / scheduler / worker 三进程 + 数据卷 + 健康检查） |
| 恢复 | 服务重启后任务状态正确恢复 | ✅ 已实现：重启后 RUNNING 中断任务标记 INTERRUPTED，允许安全重跑；scheduler 心跳写入 system_settings |

## 六、参考资料

- [plan.md](../plan.md) — 原始项目规划（V1.0）
- [ARCHITECTURE.md](ARCHITECTURE.md) — 系统架构与模块边界
- [PLUGIN_SDK.md](PLUGIN_SDK.md) — 插件开发指南
- [DATABASE.md](DATABASE.md) — 数据库设计
- [API.md](API.md) — REST API 说明
- [DEPLOYMENT.md](DEPLOYMENT.md) — 部署指南
