# DailyKeeper 插件开发指南（Plugin SDK）

> DailyKeeper 通过插件接入新平台：插件声明配置项、账号字段与任务定义，核心任务引擎按统一接口调度，**新增插件不需要修改引擎代码**。
>
> SDK 源码位于 `sdk/dailykeeper_sdk/`，官方插件示例见 `plugins/demo`、`plugins/newapi`、`plugins/mteam`、`plugins/nexusphp`。

## 一、安装方式

```bash
pip install -e ./sdk
```

SDK 仅依赖 `httpx`，提供插件基类、任务上下文、统一结果模型与插件注册表。

## 二、插件包结构

一个插件就是一个普通 Python 包，推荐结构：

```
plugins/hello/
├── pyproject.toml
└── dailykeeper_hello/
    ├── __init__.py
    └── plugin.py
```

`pyproject.toml` 中通过 entry point 向引擎注册插件（见第六节）。

## 三、最小示例

下面是一个完整可运行的 "hello" 插件：声明一个 `daily_checkin` 任务，执行时调用签到接口并返回余额快照。

```python
# dailykeeper_hello/plugin.py
from dailykeeper_sdk import (
    FieldDef, HttpClient, PlatformPlugin, TaskContext, TaskDefinition, TaskResult,
)


class HelloPlugin(PlatformPlugin):
    plugin_id = "hello"
    plugin_name = "Hello 示例平台"
    plugin_version = "0.1.0"
    description = "演示插件：展示 SDK 的最小接入方式"
    auth_types = ["cookie"]

    config_schema = [
        FieldDef(name="base_url", label="站点地址", type="string", required=True,
                 placeholder="https://example.com"),
    ]
    account_schema = [
        FieldDef(name="cookie", label="Cookie", type="secret", required=True),
    ]
    credential_schema = [
        FieldDef(name="cookie", label="Cookie", type="secret", required=True,
                 help="浏览器登录后的完整 Cookie"),
    ]
    task_definitions = [
        TaskDefinition(name="daily_checkin", description="每日签到",
                       default_time="08:30", produces_resources=True),
        TaskDefinition(name="get_balance", description="查询余额",
                       default_time="09:00", produces_resources=True),
    ]

    async def execute(self, task_name: str, context: TaskContext) -> TaskResult:
        base_url = (context.config.get("base_url") or context.base_url).rstrip("/")
        http: HttpClient = context.http

        if task_name == "daily_checkin":
            resp = await http.post(f"{base_url}/api/checkin",
                                   headers={"Cookie": context.credentials.get("cookie", "")})
            if resp.status_code == 401:
                return TaskResult.auth_expired()
            if not resp.is_success:
                return TaskResult.failed(f"签到接口返回 {resp.status_code}", retryable=True)
            data = resp.json()
            return TaskResult.ok(
                message=f"签到成功：{data.get('message', 'OK')}",
                data={
                    "resources": [{
                        "resource_type": "balance",
                        "value": data.get("balance"),
                        "unit": "CNY",
                    }],
                },
            )

        if task_name == "get_balance":
            resp = await http.get(f"{base_url}/api/user",
                                  headers={"Cookie": context.credentials.get("cookie", "")})
            if resp.status_code == 401:
                return TaskResult.auth_expired()
            data = resp.json()
            return TaskResult.ok(
                message="查询成功",
                data={
                    "resources": [{
                        "resource_type": "balance",
                        "value": data.get("balance"),
                        "unit": "CNY",
                    }],
                },
            )

        return TaskResult.failed(f"未知任务: {task_name}")
```

要点：

- `execute()` **不要对预期内的失败抛异常**，统一返回 `TaskResult`（`ok` / `failed` / `auth_expired` / `needs_action`）。
- 认证失效返回 `TaskResult.auth_expired()`，引擎会把账号标记为 `AUTH_EXPIRED` 并发送登录失效通知。
- 需要人工处理（验证码、二次验证）返回 `TaskResult.needs_action()`，进入 `NEEDS_ACTION` 状态并通知。

## 四、FieldDef 字段定义

`FieldDef` 描述实例配置（`config_schema`）、账号级配置（`account_schema`）与登录凭据字段（`credential_schema`），Dashboard 会据此动态渲染表单：添加账号时凭据区按 `credential_schema` 渲染命名字段（用户名/密码等），同时保留自定义键值对用于额外字段；`options` 项支持字符串或 `{"value": ..., "label": ...}`（值与展示文案不同时用后者，如英文枚举配中文标签）。

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| `name` | str | 字段名（提交到 config / account_config 中的键） |
| `label` | str | 表单显示名 |
| `type` | str | `string` 普通文本 / `secret` 敏感值（界面隐藏、日志脱敏）/ `number` 数字 / `boolean` 布尔开关 / `select` 下拉（配合 `options`） |
| `required` | bool | 是否必填（引擎按此做缺失校验） |
| `default` | object | 默认值 |
| `options` | list | `type="select"` 时的可选项 |
| `help` | str | 帮助文案 |
| `placeholder` | str | 输入框占位符 |

## 五、TaskDefinition 任务定义

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | str | （必填） | 任务名，对应 `execute(task_name)` 与 scheduled_tasks.task_name |
| `description` | str | `""` | 任务中文描述 |
| `description_en` | str | `""` | 任务英文描述 |
| `requires_browser` | bool | `False` | 是否需要浏览器自动化；此类任务由 **browser worker**（Playwright）执行，见第六节「浏览器任务」 |
| `requires_agent` | bool | `False` | 是否需要本地 Agent 执行；此类任务由用户本机的 **dk-agent** 拉取执行，见第七节「Agent 任务」 |
| `default_time` | str | `"08:30"` | 创建定时任务时的默认执行时间（站点时区） |
| `produces_resources` | bool | `True` | 任务是否产出资源快照（余额/积分/额度等） |
| `idempotent` | bool | `True` | 是否幂等；**非幂等任务（如已提交的签到）失败后不会自动重试**，避免重复提交触发风控 |
| `allow_concurrent` | bool | `False` | 是否允许同账号并发执行 |

## 六、浏览器任务（requires_browser）

任务声明 `requires_browser=True` 后，由 **browser worker**（`python -m app.browser_worker`，Playwright + Chromium 专用镜像）执行，普通 worker 不会认领。

### 执行机制

- **认领分流**：`create_execution` 按任务声明给执行行打 `needs_browser` 标记；普通 worker 只认领 `needs_browser=false` 的执行，browser worker 只认领 `needs_browser=true` 的执行。
- **context.browser（BrowserSession）**：浏览器任务执行时，运行时把 Playwright 的 page/context 包装为 `BrowserSession`（`from dailykeeper_sdk import BrowserSession`，仅类型标注用；SDK 本身不依赖 playwright）注入 `context.browser`：

| 成员 | 说明 |
| --- | --- |
| `session.page` / `session.context` | 原生 Playwright Page / BrowserContext（完整 API 可用） |
| `session.url` | 当前页面 URL |
| `await session.goto(url)` | 导航（默认 `domcontentloaded`） |
| `await session.click(selector)` / `await session.fill(selector, value)` | 点击 / 填表（默认 15s 超时，可传 `timeout_ms`） |
| `await session.text(selector=None)` | 页面全文或某选择器的文本 |
| `await session.wait_for_selector(selector)` | 等待元素出现 |
| `await session.screenshot(path)` | 整页截图 |

- **登录态自动持久化**：browser worker 在**每次执行前**从 `{data_dir}/browser_states/account-{id}.json` 恢复 storage state（Cookie / localStorage），**执行后**（无论成败）再写回该文件。插件无需关心会话保存——首次执行完成真实登录后，后续执行自动复用登录态。同一账号的浏览器任务按账号加锁串行。
- **误领守卫**：若 `requires_browser` 任务在无浏览器会话的环境下被执行（如被普通 worker 误领），运行时守卫直接 finalize 为 `NEEDS_ACTION`（消息含「未提供浏览器会话」），插件代码不会运行，等待 browser worker 接管重跑。插件内也应以 `context.browser is None` 兜底。
- **插件不应关闭浏览器会话**：Context 的生命周期归 browser worker 所有（持久化状态后统一关闭），插件里不要调用 `session.close()` / `context.close()`。

### 示例参考

demo 插件的 `browser_probe` 任务（`plugins/demo/dailykeeper_plugin_demo/plugin.py`）是最小示例：打开 data: URL 探针页读取标题验证链路；M-Team 插件则是真实场景（登录保活 + TOTP）。

### Playwright 可用性

SDK 本身**不依赖** playwright——只有 browser worker 运行环境需要（`deploy/Dockerfile.browser` 镜像内置）。声明了 `requires_browser` 任务的插件，在本地调试时需自行安装：`pip install playwright && playwright install chromium`。

## 七、Agent 任务（requires_agent）

任务声明 `requires_agent=True` 后，服务器 Worker 不认领这类执行，由用户本机运行的 **Local Agent**（`dk-agent`）经 `POST /api/agent/tasks/claim` 拉取执行。适用于依赖本机环境的目标（桌面应用、本地浏览器登录态等，如 WorkBuddy）。

### 执行机制

- 插件必须安装在 **Agent 所在环境**（`pip install -e your-plugin` 即可，entry points 自动发现）；服务器与 Agent 共享同一套 SDK。
- Agent 拉取任务后调用 `GET /api/agent/tasks/{id}/context` 获取**解密后的凭据与配置**（传输安全由部署层 HTTPS 保证），在本地构建 `TaskContext` 执行插件，再把 `TaskResult` 回传服务器 finalize。
- `context.http`（`HttpClient`）在 Agent 环境同样可用；`context.browser` 目前仅服务器 browser worker 提供（Agent 上报能力 `["http"]`）。
- 超时、异常脱敏、离线容忍与服务器侧一致；离线清扫（90 秒无心跳 → 任务置 INTERRUPTED）由服务器调度器负责。

### 示例参考

`plugins/demo` 的 `agent_probe` 任务：在 Agent 环境回显配置并返回本机 hostname，用于验证 Agent 执行线（服务器侧用例见 `backend/tests/test_agent.py`，Agent 侧见 `backend/tests/test_local_agent.py`）。

---

## 八、资源快照协议

任务产出的资源数据通过 `result.data["resources"]` 返回，引擎会持久化到 `resource_snapshots` 表：

```python
result.data["resources"] = [
    {
        "resource_type": "balance",   # balance / points / quota / usage / bonus / upload / download / share_rate 等
        "value": 12.34,               # 数值型
        # "text_value": "2026-11-06 00:00",  # 非数值型（如重置时间）改用 text_value
        "unit": "CNY",                # 可选：单位
        # "observed_at": "2026-11-05T12:00:00Z",  # 可选：默认为执行完成时间
    },
]
```

- 数值填 `value`（Numeric(18,4)），非数值（如重置时间、等级名）填 `text_value`。
- 一个任务可以返回多条资源快照。
- 资源汇总通过 `GET /api/resources/summary` 查询。

## 九、注册方式

在插件 `pyproject.toml` 中声明 entry point，group 固定为 `dailykeeper.plugins`：

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "dailykeeper-hello"
version = "0.1.0"
description = "DailyKeeper hello plugin"
requires-python = ">=3.12"
dependencies = [
    "dailykeeper-sdk",
]

[project.entry-points."dailykeeper.plugins"]
hello = "dailykeeper_hello.plugin:HelloPlugin"

[tool.setuptools.packages.find]
include = ["dailykeeper_hello*"]
```

服务启动时引擎调用 `plugin_registry.load_entry_points()` 加载全部插件；损坏的 entry point 会被跳过并记录警告，不会拖垮启动。V1 采用**可信插件白名单**：只有随镜像安装的官方插件会被加载。

## 十、本地调试方法

```bash
# 1. 安装 SDK、你的插件与后端
pip install -e ./sdk -e ./plugins/hello -e ./backend

# 2. 启动服务
uvicorn app.main:app --reload

# 3. 打开 Swagger 调试
#    http://127.0.0.1:8000/docs
#    - 先 /api/auth/login 登录（默认 admin / admin123，点 Authorize 填 token）
#    - /api/plugins 确认插件已加载
#    - 创建平台实例 / 账号（填入凭据）/ 定时任务
#    - 对任务执行 run-now，观察 /api/executions 的执行记录与 /api/resources 的资源快照
```

调试建议：先在插件 `execute()` 里用 `context.logger.debug()` 打印请求响应（注意不要打印凭据），再逐步接入真实站点。

## 十一、M-Team 特殊说明

M-Team 提供 API Key 方式接入（站点控制台 → 实验室 → 存取令牌），但 **API 访问不计入登录活跃**。因此：

- `mteam` 插件的 `daily_checkin`（保活签到）任务被声明为 `requires_browser=True`，由 browser worker 通过浏览器执行：凭据字典需包含 `username` / `password` / `totp_secret`（可另配 `api_key` 用于信息查询，可只配其一）。首次执行完成真实登录（含 TOTP），登录态由 browser worker 自动持久化，后续执行复用会话。
- 部署 browser worker 前，该任务会因误领守卫进入 `NEEDS_ACTION`；部署后自动恢复为浏览器执行。
- `get_user_info` 等信息查询类任务走 API Key 正常执行，可采集用户信息与资源快照。
- 详细部署注意事项见 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 十二、发布规范

- **可信插件白名单**：V1 只加载随镜像分发的官方插件；要接入新平台，将插件放入 `plugins/` 并加入镜像构建（`deploy/Dockerfile.*` 的 `pip install` 列表）。
- **第三方插件本质是可执行代码**：普通 Python 插件不是安全沙箱，安装第三方插件等于在该机器上运行任意代码。请按 plan.md §11.3 安全设计审慎评估来源与行为，V1 不提供插件市场，后续再研究独立容器隔离。
- 插件不得访问其他插件的认证信息；不得绕过平台安全措施（验证码、二次验证）；只执行用户授权且平台规则允许的任务。

## 十三、插件目录（Registry）

Dashboard 的「插件目录」页与 `GET /api/registry` 接口读取一份**可信白名单目录**，展示官方插件清单及本地安装状态。目录数据是静态 JSON，不含任何可执行逻辑。

### 目录文件位置与 schema

文件位置：`backend/app/resources/registry.json`，由 `backend/app/services/registry_service.py` 读取（文件缺失或格式异常时记录 warning 并返回空目录）。

顶层结构：

```json
{
  "schema_version": 1,
  "updated_at": "2026-11-06",
  "plugins": [ ... ]
}
```

每个插件条目的字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `plugin_id` | string | 插件标识，与 `PlatformPlugin.plugin_id` 及 `platforms` 表主键一致 |
| `package` | string | PyPI 风格包名（如 `dailykeeper-plugin-mteam`） |
| `name` | string | 展示名称 |
| `version` | string | 目录收录的版本号，应与插件 `pyproject.toml` 的 `version` 一致 |
| `description` | string | 插件描述（复制自插件声明） |
| `author` | string | 维护方，官方插件为 `DailyKeeper Official` |
| `trusted` | bool | 是否为官方信任插件；V1 目录中全部为 `true` |
| `homepage` | string | 插件源码目录的 GitHub 链接 |
| `capabilities` | string[] | 插件 `task_definitions` 的任务名清单 |
| `requires_browser` | bool | 任一任务声明 `requires_browser=True` 时为 `true` |
| `install` | string | 人工安装命令（如 `pip install -e plugins/mteam（本仓库内）`） |

### 如何把插件加入目录

通过 PR 修改 `backend/app/resources/registry.json`：在 `plugins` 数组中新增条目，填齐上表字段（`version` / `description` / `capabilities` / `requires_browser` 必须与插件源码一致，不得臆造）。新增插件同时需满足「发布规范」一节：插件包放入 `plugins/` 并加入镜像构建的 `pip install` 列表。

### 安装状态比对规则

`registry_catalog` 将目录条目与 `platforms` 表（已加载插件）按 `plugin_id` 合并，附 `installed` / `installed_version` / `upgradable` 三个字段。版本比较按**逐段数字比较**：`"0.10.0"` 解析为 `(0, 10, 0)`，因此 `"0.10.0" > "0.9.0"`；非数字段容错按 `0` 处理。`upgradable = 目录版本 > 已安装版本`。

### 安全模型重申

插件目录是**白名单目录**，不是插件市场：V1 不下载、不自动安装、不执行目录之外的任何代码，安装/升级需管理员在服务器环境手动执行 `install` 命令后重启服务。
