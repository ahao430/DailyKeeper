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

`FieldDef` 描述实例配置（`config_schema`）与账号级配置（`account_schema`），Dashboard 会据此动态渲染表单。

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
| `requires_browser` | bool | `False` | 是否需要浏览器自动化；V1 引擎对这类任务**自动返回 NEEDS_ACTION**，等待浏览器执行版本 |
| `default_time` | str | `"08:30"` | 创建定时任务时的默认执行时间（站点时区） |
| `produces_resources` | bool | `True` | 任务是否产出资源快照（余额/积分/额度等） |
| `idempotent` | bool | `True` | 是否幂等；**非幂等任务（如已提交的签到）失败后不会自动重试**，避免重复提交触发风控 |
| `allow_concurrent` | bool | `False` | 是否允许同账号并发执行 |

## 六、资源快照协议

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

## 七、注册方式

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

## 八、本地调试方法

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

## 九、M-Team 特殊说明

M-Team 提供 API Key 方式接入（站点控制台 → 实验室 → 存取令牌），但 **API 访问不计入登录活跃**。因此：

- `mteam` 插件的 `daily_checkin`（签到）任务被声明为 `requires_browser=True`，在浏览器自动化版本落地前，引擎会持续返回 `NEEDS_ACTION` 并通知人工处理——这是预期行为，不是故障。
- `get_user_info` 等信息查询类任务走 API Key 正常执行，可采集用户信息与资源快照。
- 详细部署注意事项见 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 十、发布规范

- **可信插件白名单**：V1 只加载随镜像分发的官方插件；要接入新平台，将插件放入 `plugins/` 并加入镜像构建（`deploy/Dockerfile.*` 的 `pip install` 列表）。
- **第三方插件本质是可执行代码**：普通 Python 插件不是安全沙箱，安装第三方插件等于在该机器上运行任意代码。请按 plan.md §11.3 安全设计审慎评估来源与行为，V1 不提供插件市场，后续再研究独立容器隔离。
- 插件不得访问其他插件的认证信息；不得绕过平台安全措施（验证码、二次验证）；只执行用户授权且平台规则允许的任务。
