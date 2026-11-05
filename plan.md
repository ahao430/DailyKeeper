# DailyKeeper — 通用平台自动化管理服务完整方案

我建议把这个项目正式定位为一个多平台账号、每日任务与权益管理平台。

它不只是自动签到工具，而是一个可以持续扩展的平台：今天接入 M-Team、WorkBuddy、NewAPI 中转站，未来还可以接入其他 AI 服务、Coding Plan、开发者平台和积分网站。

这次方案按照可以直接进入开发阶段的标准来设计，包含产品规划、技术架构、插件 SDK、数据库、任务调度、服务器与本地 Agent、前端、部署和开发里程碑。

# DailyKeeper

项目规划 V1.0

One Platform · Multiple Services · Automated Tasks

统一管理平台账号，自动执行日常任务，监控资源权益，集中处理异常。

多平台

论坛、PT、AI、NewAPI

自动任务

签到、查询、领取权益

跨端执行

服务器、Mac、Windows

资源看板

余额、积分、额度、用量

## 一、产品目标与范围

### 1.1 核心目标

DailyKeeper 主要解决四类问题：

1. 账号维护：不同平台的登录状态、Cookie、认证凭据统一管理。
2. 日常任务：自动签到、每日领取、积分任务、状态检查。
3. 资源管理：余额、积分、模型额度、用量、重置时间等。
4. 自动化执行：根据平台能力，自动选择 API、浏览器或本地 Agent 执行。

### 1.2 首批接入平台

建议按照实际价值排序，而不是按照平台类型平均分配开发资源。

| 平台             | 首批任务           | 执行环境          |
| -------------- | -------------- | ------------- |
| M-Team         | 登录检查、每日签到、用户信息 | Ubuntu        |
| 其他 PT 站        | 登录、签到、积分查询     | Ubuntu        |
| NewAPI 中转站     | 签到、余额、用量       | Ubuntu        |
| WorkBuddy      | 每日签到、账户状态      | Mac / Windows |
| 智谱 Coding Plan | 额度、重置时间        | API / 浏览器     |
| 其他 AI 平台       | 签到、额度、权益       | 按平台决定         |

这里有个重要原则：平台名称不等于接口标准。

例如 NewAPI 各个中转站可能有不同的二次开发，WorkBuddy 也需要先核实实际签到入口。不能假设所有平台都有公开 API。

### 1.3 V1 功能边界

V1 必须实现

- 多平台管理。
- 每个平台支持多个账号。
- 登录状态管理。
- Cookie 和认证信息持久化。
- 每日任务调度。
- 任务执行记录。
- 余额、积分、额度等数据采集。
- Bark、Gotify、Webhook 通知。
- 插件注册和扩展。
- Docker 部署。

后续版本

- Mac / Windows 本地 Agent。
- MCP 服务。
- 插件市场。
- 多用户权限。
- 复杂任务工作流。
- 数据趋势分析。
- 更多桌面软件自动化。

## 二、总体技术架构

我建议采用模块化单体架构（Modular Monolith），而不是一开始拆分微服务。

这样既有清晰的模块边界，又不会增加部署和维护成本。

## DailyKeeper 系统架构

Web 管理后台

Vue 3 · TypeScript · Element Plus

FastAPI 服务层

REST API · WebSocket · 用户认证

平台管理

站点、账号、插件

任务管理

任务、调度、工作流

认证管理

Cookie、Token、OAuth

资源管理

余额、积分、额度

Scheduler

APScheduler

Worker

任务执行引擎

Plugin Runtime

HTTP · Browser · Local Agent · MCP

SQLite / PostgreSQL

Redis（后续可选）

### 2.1 技术选型

| 层级   | 技术                      | 说明       |
| ---- | ----------------------- | -------- |
| 后端   | Python 3.12+            | 核心开发语言   |
| API  | FastAPI                 | REST API |
| ORM  | SQLAlchemy 2.x          | 数据库访问    |
| 校验   | Pydantic 2.x            | 配置与数据校验  |
| 调度   | APScheduler             | 定时任务     |
| HTTP | HTTPX                   | API 请求   |
| 浏览器  | Playwright              | 网页自动化    |
| 数据库  | SQLite                  | 初期部署     |
| 迁移   | Alembic                 | 数据库版本管理  |
| 前端   | Vue 3                   | 管理界面     |
| UI   | Element Plus            | 管理组件     |
| 部署   | Docker Compose          | 容器化      |
| 通知   | Bark / Gotify / Webhook | 消息推送     |

暂时不需要 Redis、Celery、Kubernetes。

不过要注意：Scheduler 和 Worker 必须分离运行，不能让 APScheduler 在多个 API 实例中重复调度。初期采用独立 Scheduler 进程、独立 Worker 进程和数据库任务队列即可。

## 三、最核心的设计：平台插件系统

这是整个项目最重要的部分。

如果插件设计不好，后面每增加一个网站都要修改核心代码，最终会变成大量 if/else。

我建议将插件分为三层。

### 3.1 第一层：平台插件

负责描述一个平台的能力。

例如：

- M-Team 插件。
- NewAPI 插件。
- WorkBuddy 插件。
- NexusPHP 插件。
- Discuz 插件。

每个插件可以声明：

```
class PlatformPlugin:    plugin_id: str    plugin_name: str    plugin_version: str    async def initialize(self):        ...    async def get_capabilities(self):        ...    async def validate_config(self, config):        ...    async def create_account(self, config):        ...    async def get_task_definitions(self):        ...
```

### 3.2 第二层：认证适配器

不同平台使用不同的认证方式。

建议统一支持：

| 认证类型                | 用途           |
| ------------------- | ------------ |
| Cookie              | 论坛、Web 平台    |
| Username / Password | 普通账号登录       |
| API Key             | NewAPI、AI 平台 |
| OAuth               | 第三方授权        |
| Browser Session     | 桌面端及浏览器登录    |
| Custom              | 特殊认证方式       |

认证模块独立于平台插件，避免每个插件重复实现 Cookie 存储、认证检查和凭据刷新。

### 3.3 第三层：任务定义

不要把签到写死在平台接口里。

例如一个 NewAPI 站点可能支持：

- daily_checkin
- get_balance
- get_usage
- get_user_info

而 M-Team 可能支持：

- daily_checkin
- get_user_info
- get_bonus

WorkBuddy 可能支持：

- daily_checkin
- get_account_info

每个插件自行声明能力，管理后台根据能力动态生成任务配置。

### 3.4 统一任务执行接口

建议采用如下结构：

```
class TaskContext:    account_id: str    platform_id: str    task_id: str    execution_id: strclass TaskResult:    success: bool    status: str    message: str    data: dict    metrics: dictclass PlatformPlugin:    async def execute(        self,        task_name: str,        context: TaskContext,        params: dict    ) -> TaskResult:        ...
```

任务状态统一定义：

| 状态           | 含义     |
| ------------ | ------ |
| SUCCESS      | 成功     |
| FAILED       | 执行失败   |
| SKIPPED      | 跳过     |
| AUTH_EXPIRED | 认证失效   |
| NEEDS_ACTION | 需要人工处理 |
| RATE_LIMITED | 触发限流   |
| RUNNING      | 执行中    |

特别建议区分 `FAILED` 和 `AUTH_EXPIRED`。这样系统知道是普通任务错误，还是需要重新登录。

## 四、任务调度与执行引擎

这是第二个关键模块。

### 4.1 任务模型

建议每个账号可以有多个任务，每个任务单独配置调度规则。

例如：

| 账号             | 任务   | 执行时间  | 周期 |
| -------------- | ---- | ----- | -- |
| M-Team 账号 A    | 每日签到 | 08:10 | 每天 |
| NewAPI 站点 A    | 每日签到 | 08:20 | 每天 |
| NewAPI 站点 A    | 余额查询 | 09:00 | 每天 |
| WorkBuddy 账号 A | 每日签到 | 09:30 | 每天 |
| 智谱账号 A         | 额度查询 | 10:00 | 每天 |

所有时间统一使用平台配置的时区，默认 `Asia/Shanghai`，并允许单独设置站点时区。

### 4.2 执行流程

\#chatgpt-mermaid-\_r_me\_{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:16px;fill:rgb(13, 13, 13);}@keyframes edge-animation-frame{from{stroke-dashoffset:0;}}@keyframes dash{to{stroke-dashoffset:0;}}#chatgpt-mermaid-\_r_me\_ .edge-animation-slow{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 50s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-\_r_me\_ .edge-animation-fast{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 20s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-\_r_me\_ .error-icon{fill:rgb(243, 243, 243);}#chatgpt-mermaid-\_r_me\_ .error-text{fill:rgb(13, 13, 13);stroke:rgb(13, 13, 13);}#chatgpt-mermaid-\_r_me\_ .edge-thickness-normal{stroke-width:1px;}#chatgpt-mermaid-\_r_me\_ .edge-thickness-thick{stroke-width:3.5px;}#chatgpt-mermaid-\_r_me\_ .edge-pattern-solid{stroke-dasharray:0;}#chatgpt-mermaid-\_r_me\_ .edge-thickness-invisible{stroke-width:0;fill:none;}#chatgpt-mermaid-\_r_me\_ .edge-pattern-dashed{stroke-dasharray:3;}#chatgpt-mermaid-\_r_me\_ .edge-pattern-dotted{stroke-dasharray:2;}#chatgpt-mermaid-\_r_me\_ .marker{fill:rgb(143, 143, 143);stroke:rgb(143, 143, 143);}#chatgpt-mermaid-\_r_me\_ .marker.cross{stroke:rgb(143, 143, 143);}#chatgpt-mermaid-\_r_me\_ svg{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:16px;}#chatgpt-mermaid-\_r_me\_ p{margin:0;}#chatgpt-mermaid-\_r_me\_ .label{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";color:rgb(13, 13, 13);}#chatgpt-mermaid-\_r_me\_ .cluster-label text{fill:rgb(13, 13, 13);}#chatgpt-mermaid-\_r_me\_ .cluster-label span{color:rgb(13, 13, 13);}#chatgpt-mermaid-\_r_me\_ .cluster-label span p{background-color:transparent;}#chatgpt-mermaid-\_r_me\_ .label text,#chatgpt-mermaid-\_r_me\_ span{fill:rgb(13, 13, 13);color:rgb(13, 13, 13);}#chatgpt-mermaid-\_r_me\_ .node rect,#chatgpt-mermaid-\_r_me\_ .node circle,#chatgpt-mermaid-\_r_me\_ .node ellipse,#chatgpt-mermaid-\_r_me\_ .node polygon,#chatgpt-mermaid-\_r_me\_ .node path{fill:rgb(222, 234, 251);stroke:rgb(83, 154, 248);stroke-width:1px;}#chatgpt-mermaid-\_r_me\_ .rough-node .label text,#chatgpt-mermaid-\_r_me\_ .node .label text,#chatgpt-mermaid-\_r_me\_ .image-shape .label,#chatgpt-mermaid-\_r_me\_ .icon-shape .label{text-anchor:middle;}#chatgpt-mermaid-\_r_me\_ .node .katex path{fill:#000;stroke:#000;stroke-width:1px;}#chatgpt-mermaid-\_r_me\_ .rough-node .label,#chatgpt-mermaid-\_r_me\_ .node .label,#chatgpt-mermaid-\_r_me\_ .image-shape .label,#chatgpt-mermaid-\_r_me\_ .icon-shape .label{text-align:center;}#chatgpt-mermaid-\_r_me\_ .node.clickable{cursor:pointer;}#chatgpt-mermaid-\_r_me\_ .root .anchor path{fill:rgb(143, 143, 143)!important;stroke-width:0;stroke:rgb(143, 143, 143);}#chatgpt-mermaid-\_r_me\_ .arrowheadPath{fill:rgb(143, 143, 143);}#chatgpt-mermaid-\_r_me\_ .edgePath .path{stroke:rgb(143, 143, 143);stroke-width:1px;}#chatgpt-mermaid-\_r_me\_ .flowchart-link{stroke:rgb(143, 143, 143);fill:none;}#chatgpt-mermaid-\_r_me\_ .edgeLabel{background-color:rgb(252, 252, 252);text-align:center;}#chatgpt-mermaid-\_r_me\_ .edgeLabel p{background-color:rgb(252, 252, 252);}#chatgpt-mermaid-\_r_me\_ .edgeLabel rect{opacity:0.5;background-color:rgb(252, 252, 252);fill:rgb(252, 252, 252);}#chatgpt-mermaid-\_r_me\_ .labelBkg{background-color:rgba(252, 252, 252, 0.5);}#chatgpt-mermaid-\_r_me\_ .cluster rect{fill:rgb(243, 243, 243);stroke:rgba(0, 0, 0, 0.1);stroke-width:1px;}#chatgpt-mermaid-\_r_me\_ .cluster text{fill:rgb(13, 13, 13);}#chatgpt-mermaid-\_r_me\_ .cluster span{color:rgb(13, 13, 13);}#chatgpt-mermaid-\_r_me\_ div.mermaidTooltip{position:absolute;text-align:center;max-width:200px;padding:2px;font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:12px;background:rgb(243, 243, 243);border:1px solid rgba(0, 0, 0, 0.1);border-radius:2px;pointer-events:none;z-index:100;}#chatgpt-mermaid-\_r_me\_ .flowchartTitleText{text-anchor:middle;font-size:18px;fill:rgb(13, 13, 13);}#chatgpt-mermaid-\_r_me\_ rect.text{fill:none;stroke-width:0;}#chatgpt-mermaid-\_r_me\_ .icon-shape,#chatgpt-mermaid-\_r_me\_ .image-shape{background-color:rgb(252, 252, 252);text-align:center;}#chatgpt-mermaid-\_r_me\_ .icon-shape p,#chatgpt-mermaid-\_r_me\_ .image-shape p{background-color:rgb(252, 252, 252);padding:2px;}#chatgpt-mermaid-\_r_me\_ .icon-shape .label rect,#chatgpt-mermaid-\_r_me\_ .image-shape .label rect{opacity:0.5;background-color:rgb(252, 252, 252);fill:rgb(252, 252, 252);}#chatgpt-mermaid-\_r_me\_ .label-icon{display:inline-block;height:1em;overflow:visible;vertical-align:-0.125em;}#chatgpt-mermaid-\_r_me\_ .node .label-icon path{fill:currentColor;stroke:revert;stroke-width:revert;}#chatgpt-mermaid-\_r_me\_ .node .neo-node{stroke:rgb(83, 154, 248);}#chatgpt-mermaid-\_r_me\_ [data-look="neo"].node rect,#chatgpt-mermaid-\_r_me\_ [data-look="neo"].cluster rect,#chatgpt-mermaid-\_r_me\_ [data-look="neo"].node polygon{stroke:url(#chatgpt-mermaid-\_r_me\_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-\_r_me\_ [data-look="neo"].swimlane.cluster rect{filter:none;}#chatgpt-mermaid-\_r_me\_ [data-look="neo"].node path{stroke:url(#chatgpt-mermaid-\_r_me\_-gradient);stroke-width:1px;}#chatgpt-mermaid-\_r_me\_ [data-look="neo"].node .outer-path{filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-\_r_me\_ [data-look="neo"].node .neo-line path{stroke:rgb(83, 154, 248);filter:none;}#chatgpt-mermaid-\_r_me\_ [data-look="neo"].node circle{stroke:url(#chatgpt-mermaid-\_r_me\_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-\_r_me\_ [data-look="neo"].node circle .state-start{fill:#000000;}#chatgpt-mermaid-\_r_me\_ [data-look="neo"].icon-shape .icon{fill:url(#chatgpt-mermaid-\_r_me\_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-\_r_me\_ [data-look="neo"].icon-shape .icon-neo path{stroke:url(#chatgpt-mermaid-\_r_me\_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-\_r_me\_ .node text{font-size:14px;font-weight:600;letter-spacing:normal;fill:rgb(0, 79, 153);}#chatgpt-mermaid-\_r_me\_ .edgeLabels text{font-size:13px;font-weight:600;letter-spacing:-0.08px;fill:rgb(0, 79, 153);}#chatgpt-mermaid-\_r_me\_ .node tspan[font-weight="normal"],#chatgpt-mermaid-\_r_me\_ .edgeLabels tspan[font-weight="normal"]{font-weight:600;}#chatgpt-mermaid-\_r_me\_ .edgeLabel .label rect{opacity:1;rx:13px;ry:13px;fill:rgb(245, 250, 255);stroke:rgb(206, 219, 229);stroke-width:1px;}#chatgpt-mermaid-\_r_me\_ .node rect,#chatgpt-mermaid-\_r_me\_ .node circle,#chatgpt-mermaid-\_r_me\_ .node ellipse,#chatgpt-mermaid-\_r_me\_ .node polygon,#chatgpt-mermaid-\_r_me\_ .node path{fill:rgb(229, 243, 255);stroke:rgba(0, 0, 0, 0.1);stroke-width:1px;}#chatgpt-mermaid-\_r_me\_ .node rect{rx:16px;ry:16px;}#chatgpt-mermaid-\_r_me\_ .mermaid-decision .label-container{fill:rgb(245, 250, 255);stroke:rgb(206, 219, 229);stroke-dasharray:2,2;}#chatgpt-mermaid-\_r_me\_ .edgePaths .flowchart-link{stroke:rgb(143, 143, 143);stroke-width:1px;stroke-linecap:round;stroke-linejoin:round;}#chatgpt-mermaid-\_r_me\_ .marker{fill:rgb(143, 143, 143);stroke:rgb(143, 143, 143);}#chatgpt-mermaid-\_r_me\_ :root{--mermaid-font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";}Scheduler 定时触发创建任务实例任务是否重复跳过进入任务队列Worker 获取任务检查账号认证标记认证异常加载平台插件执行任务执行结果保存结果错误分类暂停并通知是否允许重试结束任务更新统计并通知是否失效有效成功失败需要人工验证允许不允许

### 4.3 必须实现的执行保护

这几个设计不要省略：

1. 任务去重：同一个账号、同一个任务、同一个业务日期只执行一次。
2. 执行锁：避免同一个账号同时执行多个任务。
3. 超时控制：HTTP 和浏览器任务分别设置超时。
4. 重试策略：网络错误可以重试，签到提交成功但响应不明确时不能直接重复提交。
5. 限流控制：每个平台独立设置并发数和请求间隔。
6. 任务恢复：服务重启后识别中断任务，判断能否安全恢复。
7. 人工接管：验证码、二次验证等情况进入待处理状态。

尤其是签到：要有幂等性保护。不能因为请求超时就再次提交，否则可能重复领取或触发风控。

### 4.4 任务队列怎么实现？

V1 建议：

- APScheduler：负责产生定时任务。
- SQLite：保存任务队列和执行状态。
- Worker：从数据库领取任务。
- 数据库事务：保证任务领取不会重复。
- 独立进程锁：避免多个 Scheduler 同时运行。

未来并发量明显增加，再考虑 Redis + Celery 或其他消息队列。

## 五、服务器与本地 Agent 双执行架构

这个设计是 DailyKeeper 区别于普通签到脚本的重要能力。

M-Team、NewAPI 大多数在线任务可以由 Ubuntu 服务器执行，但 WorkBuddy 这样的桌面应用可能依赖本机客户端、浏览器登录态或桌面环境。

因此不能把所有自动化都放到服务器。

### 5.1 双执行环境

DailyKeeper Server

Ubuntu · FastAPI · Scheduler · Database

Server Worker

M-Team、NewAPI、论坛、HTTP API

服务器执行

Local Agent

WorkBuddy、本地浏览器、桌面应用

本地执行

安全通信通道

HTTPS · Agent 身份认证 · 心跳 · 任务分发 · 结果回传

### 5.2 Local Agent 功能

建议 Local Agent 使用 Python 开发，和服务器端共享插件 SDK。

负责：

- Agent 注册。
- 心跳上报。
- 接收执行任务。
- 管理本地浏览器会话。
- 调用本地桌面程序。
- 保存本地认证状态。
- 返回执行日志和任务结果。

### 5.3 Agent 通信方式

我更推荐 Agent 主动连接服务器，而不是让服务器主动连接用户电脑。

例如：

```
Local Agent
    |
    | HTTPS / WebSocket
    |
DailyKeeper Server
    |
    | 分配任务
    |
Local Agent
    |
    | 执行 WorkBuddy 任务
    |
    | 返回结果
    |
DailyKeeper Server
```

好处：

- 不需要给 Mac 开放公网端口。
- 可以适应家庭网络和 NAT。
- Agent 离线不影响服务器任务。
- Agent 恢复连接后可以接收新任务。

需要注意：Agent 离线期间的任务是否执行，应根据任务有效期决定，过期签到不能无限补执行。

## 六、数据库设计

建议从第一版就把数据模型设计完整，避免以后迁移困难。

核心表如下：

| 表名                 | 作用         |
| ------------------ | ---------- |
| platforms          | 平台定义       |
| platform_instances | 站点实例       |
| plugins            | 插件注册信息     |
| accounts           | 平台账号       |
| credentials        | 加密认证信息     |
| task_definitions   | 插件提供的任务定义  |
| scheduled_tasks    | 用户配置的定时任务  |
| task_executions    | 任务执行历史     |
| task_results       | 任务执行结果     |
| resource_snapshots | 余额、积分、额度历史 |
| agents             | 本地 Agent   |
| notifications      | 通知记录       |
| system_settings    | 系统配置       |

### 6.1 关键关系

\#chatgpt-mermaid-\_r_mv\_{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:16px;fill:rgb(13, 13, 13);}@keyframes edge-animation-frame{from{stroke-dashoffset:0;}}@keyframes dash{to{stroke-dashoffset:0;}}#chatgpt-mermaid-\_r_mv\_ .edge-animation-slow{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 50s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-\_r_mv\_ .edge-animation-fast{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 20s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-\_r_mv\_ .error-icon{fill:rgb(243, 243, 243);}#chatgpt-mermaid-\_r_mv\_ .error-text{fill:rgb(13, 13, 13);stroke:rgb(13, 13, 13);}#chatgpt-mermaid-\_r_mv\_ .edge-thickness-normal{stroke-width:1px;}#chatgpt-mermaid-\_r_mv\_ .edge-thickness-thick{stroke-width:3.5px;}#chatgpt-mermaid-\_r_mv\_ .edge-pattern-solid{stroke-dasharray:0;}#chatgpt-mermaid-\_r_mv\_ .edge-thickness-invisible{stroke-width:0;fill:none;}#chatgpt-mermaid-\_r_mv\_ .edge-pattern-dashed{stroke-dasharray:3;}#chatgpt-mermaid-\_r_mv\_ .edge-pattern-dotted{stroke-dasharray:2;}#chatgpt-mermaid-\_r_mv\_ .marker{fill:rgb(143, 143, 143);stroke:rgb(143, 143, 143);}#chatgpt-mermaid-\_r_mv\_ .marker.cross{stroke:rgb(143, 143, 143);}#chatgpt-mermaid-\_r_mv\_ svg{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:16px;}#chatgpt-mermaid-\_r_mv\_ p{margin:0;}#chatgpt-mermaid-\_r_mv\_ .entityBox{fill:rgb(222, 234, 251);stroke:rgb(83, 154, 248);}#chatgpt-mermaid-\_r_mv\_ .relationshipLabelBox{fill:rgb(243, 243, 243);opacity:0.7;background-color:rgb(243, 243, 243);}#chatgpt-mermaid-\_r_mv\_ .relationshipLabelBox rect{opacity:0.5;}#chatgpt-mermaid-\_r_mv\_ .labelBkg{background-color:rgba(243, 243, 243, 0.5);}#chatgpt-mermaid-\_r_mv\_ .edgeLabel{background-color:rgb(252, 252, 252);}#chatgpt-mermaid-\_r_mv\_ .edgeLabel .label rect{fill:rgb(252, 252, 252);}#chatgpt-mermaid-\_r_mv\_ .edgeLabel .label text{fill:rgb(13, 13, 13);}#chatgpt-mermaid-\_r_mv\_ .edgeLabel .label{fill:rgb(83, 154, 248);font-size:14px;}#chatgpt-mermaid-\_r_mv\_ .label{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";color:rgb(13, 13, 13);}#chatgpt-mermaid-\_r_mv\_ .edge-pattern-dashed{stroke-dasharray:8,8;}#chatgpt-mermaid-\_r_mv\_ .node rect,#chatgpt-mermaid-\_r_mv\_ .node circle,#chatgpt-mermaid-\_r_mv\_ .node ellipse,#chatgpt-mermaid-\_r_mv\_ .node polygon{fill:rgb(222, 234, 251);stroke:rgb(83, 154, 248);stroke-width:1px;}#chatgpt-mermaid-\_r_mv\_ .relationshipLine{stroke:rgb(143, 143, 143);stroke-width:1px;fill:none;}#chatgpt-mermaid-\_r_mv\_ .marker{fill:none!important;stroke:rgb(143, 143, 143)!important;stroke-width:1;}#chatgpt-mermaid-\_r_mv\_ [data-look=neo].labelBkg{background-color:rgba(243, 243, 243, 0.5);}#chatgpt-mermaid-\_r_mv\_ .node .neo-node{stroke:rgb(83, 154, 248);}#chatgpt-mermaid-\_r_mv\_ [data-look="neo"].node rect,#chatgpt-mermaid-\_r_mv\_ [data-look="neo"].cluster rect,#chatgpt-mermaid-\_r_mv\_ [data-look="neo"].node polygon{stroke:url(#chatgpt-mermaid-\_r_mv\_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-\_r_mv\_ [data-look="neo"].swimlane.cluster rect{filter:none;}#chatgpt-mermaid-\_r_mv\_ [data-look="neo"].node path{stroke:url(#chatgpt-mermaid-\_r_mv\_-gradient);stroke-width:1px;}#chatgpt-mermaid-\_r_mv\_ [data-look="neo"].node .outer-path{filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-\_r_mv\_ [data-look="neo"].node .neo-line path{stroke:rgb(83, 154, 248);filter:none;}#chatgpt-mermaid-\_r_mv\_ [data-look="neo"].node circle{stroke:url(#chatgpt-mermaid-\_r_mv\_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-\_r_mv\_ [data-look="neo"].node circle .state-start{fill:#000000;}#chatgpt-mermaid-\_r_mv\_ [data-look="neo"].icon-shape .icon{fill:url(#chatgpt-mermaid-\_r_mv\_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-\_r_mv\_ [data-look="neo"].icon-shape .icon-neo path{stroke:url(#chatgpt-mermaid-\_r_mv\_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-\_r_mv\_ :root{--mermaid-font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";}PLATFORMSPLATFORM_INSTANCESPLUGINSACCOUNTSCREDENTIALSTASK_DEFINITIONSSCHEDULED_TASKSTASK_EXECUTIONSTASK_RESULTSRESOURCE_SNAPSHOTSAGENTShasimplementsownshasdeclaresconfiguresdefinesproducesreturnstracksexecutes

### 6.2 几个重要的数据设计

平台实例与平台分离

例如：

- NewAPI 是平台类型。
- 中转站 A 是一个平台实例。
- 中转站 B 是另一个平台实例。
- 每个实例可以有多个账号。

这样不需要为每个 NewAPI 中转站创建不同插件。

资源数据使用统一结构

建议资源采集统一为：

```
{
  "resource_type": "balance",
  "value": 128.50,
  "unit": "CNY",
  "observed_at": "2026-11-05T09:00:00+08:00",
  "source": "newapi"
}
```

可以支持：

- balance：余额。
- points：积分。
- quota：可用额度。
- usage：使用量。
- bonus：奖励。
- reset_at：重置时间。

这里建议使用 `Decimal` 存储金额，不要使用浮点数。

认证信息独立保存

Cookie、Token、密码不要直接存放在 accounts 表中。

采用：

- 认证凭据独立表。
- AES-GCM 加密敏感字段。
- 主加密密钥放环境变量或 Docker Secret。
- 不在日志中输出 Cookie、Token、密码。
- 支持认证信息更新和失效标记。

## 七、前端管理后台

建议采用 Vue 3 + TypeScript + Element Plus。

第一版规划六个主要页面。

1\. 总览 Dashboard

P0

# 12

平台账号

# 18

今日任务

# 15

任务成功

# 2

待处理异常

界面示意，非实际数据。

2\. 平台管理

平台列表、站点实例、插件状态

多账号、认证状态、账号备注

3\. 任务中心

任务日历、定时任务、执行状态

手动执行、暂停、重试

4\. 资源看板

余额、积分、额度、用量趋势

5\. 执行日志

执行详情、异常原因、耗时

6\. 系统设置

通知、Agent、插件、权限、安全

### 7.1 平台添加流程

用户点击添加平台：

1. 选择平台类型。
2. 输入站点 URL。
3. 选择认证方式。
4. 完成登录或授权。
5. 插件检测平台能力。
6. 展示可用任务。
7. 用户启用需要的任务。
8. 配置执行时间。

这里建议做成动态配置表单。插件返回字段定义，前端根据字段定义渲染，不要为每个插件单独开发一套添加页面。

## 八、通知系统

建议通知系统独立出来，不要和任务执行逻辑耦合。

支持：

- Bark。
- Gotify。
- Webhook。
- 后续可以扩展邮件、企业微信等。

通知事件：

| 事件       | 默认通知 |
| -------- | ---- |
| 每日签到成功   | 可选   |
| 签到失败     | 是    |
| 登录失效     | 是    |
| 需要人工验证   | 是    |
| 余额低于阈值   | 是    |
| Agent 离线 | 是    |
| 任务执行异常   | 是    |

通知也应该支持按平台配置，避免每天大量成功消息造成干扰。

## 九、项目目录结构

这是建议的正式目录：

```
dailykeeper/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── platforms.py
│   │   │   ├── accounts.py
│   │   │   ├── tasks.py
│   │   │   ├── resources.py
│   │   │   ├── agents.py
│   │   │   └── plugins.py
│   │   │
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── database.py
│   │   │   ├── security.py
│   │   │   └── logging.py
│   │   │
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── scheduler/
│   │   ├── worker/
│   │   ├── queue/
│   │   ├── notifications/
│   │   └── main.py
│   │
│   └── tests/
│
├── sdk/
│   └── dailykeeper_sdk/
│       ├── base.py
│       ├── context.py
│       ├── result.py
│       ├── capabilities.py
│       └── registry.py
│
├── plugins/
│   ├── mteam/
│   ├── nexusphp/
│   ├── discuz/
│   ├── newapi/
│   └── workbuddy/
│
├── local-agent/
│   ├── agent/
│   ├── executors/
│   ├── communication/
│   └── tests/
│
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── views/
│   │   ├── components/
│   │   ├── stores/
│   │   └── router/
│   └── package.json
│
├── deploy/
│   ├── docker-compose.yml
│   ├── Dockerfile.backend
│   ├── Dockerfile.worker
│   └── nginx/
│
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── PLUGIN_SDK.md
│   ├── DATABASE.md
│   ├── API.md
│   └── DEPLOYMENT.md
│
└── README.md
```

插件建议使用 Python 包入口点（Entry Points）注册，而不是扫描任意目录并直接执行未知代码。第三方插件需要版本约束、权限声明和可信来源管理。

## 十、开发阶段与里程碑

我建议分成六个阶段，不要一开始就把所有平台全部接入。

## 开发路线图

1. 阶段 1：项目基础设施

   P0
   - 初始化 Python 后端、Vue 前端。
   - 数据库与迁移机制。
   - FastAPI 基础 API。
   - Docker Compose 部署。
   - 用户登录和系统配置。
   交付：可运行的空平台。
2. 阶段 2：插件 SDK 和任务引擎

   P0
   - 插件注册和能力声明。
   - 账号、认证管理。
   - Scheduler 与 Worker。
   - 任务状态机、执行锁。
   - 任务日志和重试策略。
   交付：可以运行一个模拟平台插件。
3. 阶段 3：首批平台接入

   P0
   - M-Team。
   - NewAPI 通用适配器。
   - NexusPHP 通用适配器。
   - 站点差异配置。
   - 余额、积分和用量采集。
   交付：服务器端自动化服务可用。
4. 阶段 4：管理后台

   P0
   - Dashboard。
   - 平台管理。
   - 账号管理。
   - 任务管理。
   - 执行日志。
   - 资源看板。
   交付：完整 Web 管理体验。
5. 阶段 5：本地 Agent

   P1
   - Agent 注册与认证。
   - 心跳机制。
   - 任务接收和结果回传。
   - 本地浏览器管理。
   - WorkBuddy 适配。
   交付：支持本地桌面任务。
6. 阶段 6：扩展能力

   P2
   - MCP Server。
   - 插件安装和升级。
   - 更多平台。
   - 资源趋势分析。
   - 多用户和权限管理。
   交付：可持续扩展的平台。

### 开发优先级

| 模块          | 优先级 | 依赖          |
| ----------- | --- | ----------- |
| 项目基础设施      | P0  | 无           |
| 插件 SDK      | P0  | 基础设施        |
| 任务引擎        | P0  | SDK         |
| 认证管理        | P0  | 基础设施        |
| M-Team      | P0  | SDK、认证      |
| NewAPI      | P0  | SDK、认证      |
| NexusPHP    | P1  | SDK         |
| 管理后台        | P0  | API         |
| 通知系统        | P1  | 任务引擎        |
| Local Agent | P1  | SDK、任务引擎    |
| WorkBuddy   | P1  | Local Agent |
| MCP         | P2  | API         |

建议按阶段交付，但可以让前端在后端基础设施完成后并行开发。

## 十一、测试与质量保障

自动化项目特别容易出现一种问题：开发环境测试成功，实际运行几天后出现重复签到、Cookie 失效或者任务卡死。

所以测试不能只关注接口返回是否正常。

### 11.1 测试层次

| 测试类型  | 主要内容                 |
| ----- | -------------------- |
| 单元测试  | 插件接口、任务状态机           |
| 集成测试  | 数据库、Scheduler、Worker |
| 模拟测试  | 假平台、假签到接口            |
| 浏览器测试 | 登录、Cookie 复用         |
| 故障测试  | 网络中断、超时、重启           |
| 并发测试  | 多账号同时执行              |
| 安全测试  | 凭据泄漏、插件权限            |

### 11.2 必须验证的场景

- 同一天重复触发签到。
- 两个 Worker 同时领取同一任务。
- 登录状态过期。
- 签到成功但响应超时。
- 服务器重启时任务正在执行。
- Local Agent 离线。
- 站点返回限流。
- 插件执行异常。
- 认证信息更新。
- 站点时区与服务器时区不一致。

建议使用 pytest，浏览器测试使用 Playwright Test 或 pytest-playwright。

### 11.3 安全设计

这个项目会保存大量网站账号凭据，需要从第一版就重视安全：

1. 后台必须设置独立管理员认证。
2. Cookie、密码、API Key 加密保存。
3. Docker 数据目录设置最小权限。
4. Agent 使用独立身份凭据，可撤销、可轮换。
5. 插件默认不能访问其他插件的认证信息。
6. 插件执行设置网络访问白名单和资源限制。
7. 所有任务记录脱敏。
8. 不自动处理验证码或绕过平台安全措施。
9. 只执行用户授权且平台规则允许的任务。
10. 提供账号凭据删除和数据导出功能。

另外，第三方插件本质上是可以执行代码的，不能把普通 Python 插件当成安全沙箱。V1 先采用可信插件白名单，后续再研究独立容器隔离。

## 十二、Ubuntu / Debian 部署方案

建议最终采用 Docker Compose：

```
services:
  api:
    build:
      context: ..
      dockerfile: deploy/Dockerfile.backend
    restart: unless-stopped

  scheduler:
    build:
      context: ..
      dockerfile: deploy/Dockerfile.worker
    command: python -m app.scheduler
    restart: unless-stopped

  worker:
    build:
      context: ..
      dockerfile: deploy/Dockerfile.worker
    command: python -m app.worker
    restart: unless-stopped

  frontend:
    image: nginx:alpine
    restart: unless-stopped
```

这是部署结构示意，实际配置还需要补充数据库卷、配置文件、密钥、健康检查、网络和资源限制。

### 初期服务器资源建议

| 资源  | 建议                   |
| --- | -------------------- |
| CPU | 2 核起步                |
| 内存  | 2GB 起步，浏览器任务多时建议 4GB |
| 磁盘  | 20GB 起步              |
| 数据库 | SQLite               |
| 浏览器 | 独立 Playwright Worker |
| 备份  | 每日数据库备份              |

初期规模并不大，完全没必要为了未来可能出现的几百个账号提前上复杂架构。

## 十三、V1 验收标准

我建议把以下条件作为第一版完成标准。

| 验收项目 | 标准                  |
| ---- | ------------------- |
| 平台管理 | 能添加多个不同类型平台         |
| 多账号  | 每个平台能管理多个账号         |
| 插件机制 | 新增插件不修改核心任务引擎       |
| 认证管理 | 能保存和检测认证状态          |
| 自动任务 | 支持每日定时任务            |
| 任务安全 | 重复执行有幂等保护           |
| 执行记录 | 每次任务都有完整记录          |
| 资源统计 | 支持余额、积分、额度等         |
| 通知   | 失败和人工验证能通知          |
| 部署   | Docker Compose 一键部署 |
| 恢复   | 服务重启后任务状态正确恢复       |

对于首批平台，建议分别完成真实站点验证，而不是只用模拟接口验收。

## 十四、几个我建议提前定下来的架构决策

这部分很重要，避免后面返工。

| 决策       | 我的建议               |
| -------- | ------------------ |
| 项目形态     | 模块化单体              |
| 后端语言     | Python             |
| 插件方式     | SDK + Entry Points |
| 任务执行     | 统一任务引擎             |
| 调度       | 独立 Scheduler       |
| Worker   | 独立进程               |
| 数据库      | SQLite 起步          |
| 插件配置     | Pydantic Schema    |
| 浏览器      | Playwright         |
| 本地执行     | 独立 Local Agent     |
| Agent 通信 | 主动连接服务器            |
| 认证存储     | 加密凭据仓库             |
| 第三方插件    | 可信白名单              |
| MCP      | 后续增加               |

### 特别值得注意的两个问题

1\. NewAPI 插件要支持站点差异。

建议采用：

```
NewAPI Plugin
    ├── 通用用户信息接口
    ├── 通用余额查询接口
    ├── 通用用量查询接口
    ├── 签到能力探测
    └── 站点自定义适配配置
```

不要假设不同中转站的签到接口一致。站点接口可以配置映射，但不要允许任意执行未经审核的动态代码。

2\. WorkBuddy 不要强行塞进服务器端。

它应该作为 Local Agent 的一个任务适配器。先核实官方支持能力，再选择 API、浏览器或受支持的桌面交互方式。

这样服务器和本地 Agent 的边界会非常清楚。

## 十五、最终开发建议：先做一个真正可用的 MVP

我不建议第一版就实现全部功能。最合理的顺序是：

## MVP 第一阶段目标

建议首先完成

一个服务器端运行的多平台自动任务系统

- Python + FastAPI 后端。
- Vue 3 管理后台。
- 插件 SDK。
- 统一任务执行引擎。
- 多站点、多账号管理。
- M-Team 签到插件。
- NewAPI 签到及余额查询插件。
- NexusPHP 适配器。
- Bark / Gotify 通知。
- Docker Compose 部署。\

  第二阶段
- Local Agent。
- WorkBuddy。
- MCP。
- 更多 AI 平台。
- 资源趋势和统计。

### 我建议的实际开发顺序

不要先写 M-Team 脚本，再考虑怎么改造成插件。

应该先：

1. 定义插件 SDK。
2. 实现一个模拟平台插件。
3. 验证账号、认证、任务调度、结果记录完整闭环。
4. 再开发 M-Team 和 NewAPI 插件。
5. 最后接入管理后台和 Local Agent。

这样以后增加一个平台，基本就是开发一个插件，而不是重新开发一套业务逻辑。

### 下一步可以进入项目初始化

我建议接下来产出四份开发基础文档：

- `PRD.md`：完整产品需求。
- `ARCHITECTURE.md`：系统架构与模块边界。
- `PLUGIN_SDK.md`：插件接口、注册机制、开发规范。
- `DATABASE.md`：完整数据库表结构和关系。

然后生成第一版项目目录和可运行代码骨架。

另外，可以在开发过程中每周自动整理一次进度、已完成模块和下一周开发任务：

🛠️每周整理 DailyKeeper 开发进度轻点设置

我的总体判断是：DailyKeeper 值得按照一个长期维护的小型开源项目来设计，而不是一次性的签到脚本。最重要的投资是插件 SDK 和任务引擎，这两个核心做好了，后续平台接入成本会越来越低。