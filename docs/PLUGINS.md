# 官方插件使用指南

> 四个官方插件随仓库分发，经 entry points 注册，装好即用。本文讲每个插件**怎么配、凭据从哪拿、任务做什么**。插件开发请看 [PLUGIN_SDK](PLUGIN_SDK.md)。
>
> 通用流程：`pip install -e <插件目录>` → 平台与账号 → 新增平台（选插件、填站点地址）→ 展开行「添加账号」（凭据按插件声明的字段填写，AES-GCM 加密存储）→ 任务中心「新增任务」→ 立即执行或等每日调度。
>
> 两条执行线：任务声明 `requires_browser` 时由 browser-worker 用真实 Chromium 执行（需要部署 browser-worker）；其余走普通 worker 的 HTTP 客户端。

---

## M-Team（馒头）

**做什么**：

| 任务 | 执行线 | 说明 |
| --- | --- | --- |
| `daily_checkin` | 浏览器 | 登录保活 + 站内签到两阶段：先用持久化会话访问站点（会话有效即保活完成），失效则用用户名/密码/TOTP 自动登录，登录成功后自动点击站内签到按钮并识别结果 |
| `get_user_info` | HTTP | 官方 API 查询用户信息与魔力值（`x-api-key` 头） |

**凭据准备**（三种按需组合，账号编辑里随时可补）：

| 字段 | 必填 | 从哪获取 |
| --- | --- | --- |
| `username` / `password` | 保活签到需要 | 你的 M-Team 登录账号密码 |
| `totp_secret` | 开了两步验证的账号必填 | 绑定验证器 App 时的 **Base32 密钥**（形如 `JBSWY3DPEHPK3PXP`）。没保存过 → 站点两步验证设置里重新绑定，页面上有二维码，用任意二维码解码工具读出 `otpauth://totp/...?secret=XXXX` 中的 secret；绑定后 App 扫新码 |
| `api_key` | 信息查询需要 | M-Team 控制台 → 实验室 → 存取令牌（API Key） |

**执行细节**：

- 登录成功的判据是页面 SPA 请求 `/api/member/profile` 返回 200；成功后浏览器会话（Cookie/localStorage）持久化到数据卷 `browser_states/account-{id}.json`，**后续执行直接复用会话，不再重复登录**。
- 签到结果在执行记录的 `data.checkin` 里：`done`（签到成功）/ `already`（今日已签）/ `not_found`（没找到签到入口，可在实例配置调整）/ `clicked_unconfirmed`（点了但没检测到提示）。
- 删掉 `browser_states/account-{id}.json` 即强制下次重新登录。

**常见问题**：

- 「检测」报"未配置 API Key"：检测按钮走 `get_user_info`（API 查询），只验证 api_key；**用户名/密码在每日签到任务的浏览器登录中验证**，两者用途不同。
- 「登录需要两步验证，但凭据未配置 totp_secret」：账号开了 2FA，按上表补 totp_secret 后强制重跑即可。
- 官方 API 访问**不计入登录活跃**，所以保活必须走浏览器登录（这正是浏览器执行线存在的原因）；40 天未登录会触发账号清理。
- 登录/签到选择器都可在平台实例配置中覆盖（站点改版时），无需改代码。

**配置项**（实例配置）：`profile_path`、`site_url`、`login_timeout_seconds`、`username_selector`、`password_selector`、`login_button_selector`、`totp_selector`、`checkin_url`、`checkin_button_selector`、`checkin_already_text`、`checkin_success_text`。

---

## NewAPI / OneAPI 中转站

**做什么**：

| 任务 | 执行线 | 说明 |
| --- | --- | --- |
| `daily_checkin` | HTTP | 调用站点签到接口（POST） |
| `get_user_info` | HTTP | 查询用户信息与余额（quota，按站点换算美元） |

**凭据准备**（二选一）：

| 字段 | 从哪获取 |
| --- | --- |
| `token` | 站点 → 个人设置 → 生成**系统访问令牌**（System Access Token） |
| `cookie` | 浏览器登录后 F12 → Network 复制请求头里的完整 Cookie |

**账号配置**：`api_user` —— 你的用户 ID（请求头 `new-api-user` 的值，个人设置页可见；有些站点部署需要它，有些不需要）。

**配置项**：`sign_path`（签到接口路径，默认 `/api/user/sign_in`）、`profile_path`（默认 `/api/user/self`）、`quota_per_unit`（多少 quota = 1 美元，默认 500000）等。不同站点的接口路径可能不同，报 404/路径错误时在实例配置里改。

---

## NexusPHP 站点（PT 站通用）

**做什么**：

| 任务 | 执行线 | 说明 |
| --- | --- | --- |
| `daily_checkin` | HTTP | 访问签到页点击签到（NexusPHP 标准签到流） |

**凭据准备**：

| 字段 | 从哪获取 |
| --- | --- |
| `cookie`（必填） | 浏览器登录站点后 F12 → Application/存储 → Cookies，复制完整 cookie 串（含 `c_secure_uid` 等关键项） |

**配置项**：`checkin_path`（签到页路径，默认 `/plugin.php?H_name=attendance` 等按站点）、`checkin_button_selector`、`success_text`、`user_agent`。不同 NexusPHP 站点的签到插件不同（attendance / fantasy 等），路径和按钮文本按站点在实例配置中调整。

> 注意：Cookie 有有效期，过期后任务转 `AUTH_EXPIRED` 并推送通知，重新登录站点复制新 Cookie 更新账号即可。

---

## 演示平台

**做什么**：不发起任何网络请求，用于验证引擎闭环（调度 → 执行 → 去重 → 结果 → 资源快照 → 通知）。

| 任务 | 执行线 | 说明 |
| --- | --- | --- |
| `daily_checkin` / `get_user_info` | HTTP | 按"行为模式"配置返回对应结果 |
| `browser_probe` | 浏览器 | 打开探针页读标题，验证 browser-worker 链路 |
| `agent_probe` | Agent | 在本地执行端回显配置，验证 Agent 链路 |

**账号配置**：

| 字段 | 说明 |
| --- | --- |
| `behavior` | 行为模式：成功 / 登录失效 / 失败（可重试）/ 失败（不可重试）/ 需要人工处理 / 跳过（今日已签）/ 触发限流 |
| `balance` / `points` | >0 时在结果中生成资源快照（供资源看板画趋势） |
| `balance_unit` | 余额单位，默认 CNY |

**典型用法**：新部署后先把 behavior 设为"成功"跑一遍全链路；再把 behavior 切成"登录失效"验证 `AUTH_EXPIRED` 状态与通知推送。

---

## 插件目录页说明

Dashboard「插件目录」展示的是可信白名单目录与本机已安装插件的比对结果（`installed` / `upgradable`），**不提供自动安装、不执行任何第三方代码**——新插件需要加入镜像构建并注册 entry point 后随服务启动加载。
