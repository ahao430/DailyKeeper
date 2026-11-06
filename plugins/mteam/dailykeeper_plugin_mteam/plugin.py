"""M-Team（馒头）PT 站插件：API Key 查询用户信息与魔力；浏览器登录保活。

官方 API（x-api-key）访问不计入 40 天登录活跃，保活必须走浏览器登录：
kp.m-team.cc 为 SPA，登录成功后会请求 /api/member/profile，会话令牌
保存在 localStorage 中，由浏览器 Worker 通过 storage state 持久化复用。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time
from typing import Any, ClassVar

import httpx
from playwright.async_api import TimeoutError as PlaywrightTimeout

from dailykeeper_sdk import (
    FieldDef,
    HttpClient,
    PlatformPlugin,
    TaskContext,
    TaskDefinition,
    TaskResult,
    TaskStatus,
)

_DEFAULT_SITE_URL = "https://kp.m-team.cc"

# 登录页选择器候选（逗号分隔，SPA 结构可能变化，均可经插件配置覆盖）
_DEFAULT_USERNAME_SELECTOR = (
    "input[placeholder*='用户名'], input[name='username'], input[type='text']"
)
_DEFAULT_PASSWORD_SELECTOR = "input[type='password']"
_DEFAULT_LOGIN_BUTTON_SELECTOR = "button:has-text('登 錄'), button:has-text('登錄'), button:has-text('登录'), button:has-text('登 录')"
_DEFAULT_TOTP_SELECTOR = (
    "input[placeholder*='驗證'], input[placeholder*='验证'], input[name='totp'], input[inputmode='numeric']"
)

# 站内签到入口（登录成功后自动签到；按钮文本繁简都做候选）
_DEFAULT_CHECKIN_BUTTON_SELECTOR = (
    "a:has-text('簽到'), button:has-text('簽到'), span:has-text('簽到'), "
    "a:has-text('签到'), button:has-text('签到'), span:has-text('签到')"
)
_DEFAULT_CHECKIN_ALREADY_TEXT = "已簽到, 已签到, 已打卡"
_DEFAULT_CHECKIN_SUCCESS_TEXT = "簽到成功, 签到成功, 獲得, 获得"


def _b32_decode(secret: str) -> bytes:
    """Base32 解码，容忍空格、小写与缺失的 padding。"""
    cleaned = "".join(secret.split()).upper().replace("=", "")
    padding = (-len(cleaned)) % 8
    return base64.b32decode(cleaned + "=" * padding)


def _totp_now(secret: str, at: float = 0.0) -> str:
    """RFC 6238 TOTP（HMAC-SHA1，6 位数字，30 秒步长）；at<=0 时取当前时间。"""
    if at <= 0:
        at = time.time()
    key = _b32_decode(secret)
    counter = int(at // 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{code % 1_000_000:06d}"


class MTeamPlugin(PlatformPlugin):
    """M-Team（馒头）PT 站插件。"""

    plugin_id: ClassVar[str] = "mteam"
    plugin_name: ClassVar[str] = "M-Team"
    plugin_version: ClassVar[str] = "0.2.0"
    description: ClassVar[str] = (
        "M-Team（馒头）PT 站：API Key 查询用户信息与魔力；"
        "浏览器登录保活（官方 API 访问不计入登录活跃）"
    )
    auth_types: ClassVar[list] = ["api_key"]
    config_schema: ClassVar[list] = [
        FieldDef(
            name="profile_path",
            label="用户信息接口路径",
            type="string",
            required=False,
            default="/api/member/profile",
            help="M-Team 官方 API 路径，通常无需修改",
        ),
        FieldDef(
            name="site_url",
            label="站点地址",
            type="string",
            required=False,
            default=_DEFAULT_SITE_URL,
            help="M-Team Web 站点地址，通常无需修改",
        ),
        FieldDef(
            name="login_timeout_seconds",
            label="登录超时（秒）",
            type="number",
            required=False,
            default=60,
            help="浏览器保活登录流程的整体超时时间",
        ),
        FieldDef(
            name="username_selector",
            label="用户名输入框选择器",
            type="string",
            required=False,
            default=_DEFAULT_USERNAME_SELECTOR,
            help="逗号分隔的候选 CSS 选择器，站点改版时可在实例配置中覆盖",
        ),
        FieldDef(
            name="password_selector",
            label="密码输入框选择器",
            type="string",
            required=False,
            default=_DEFAULT_PASSWORD_SELECTOR,
            help="逗号分隔的候选 CSS 选择器，站点改版时可在实例配置中覆盖",
        ),
        FieldDef(
            name="login_button_selector",
            label="登录按钮选择器",
            type="string",
            required=False,
            default=_DEFAULT_LOGIN_BUTTON_SELECTOR,
            help="逗号分隔的候选 CSS 选择器，站点改版时可在实例配置中覆盖",
        ),
        FieldDef(
            name="totp_selector",
            label="两步验证输入框选择器",
            type="string",
            required=False,
            default=_DEFAULT_TOTP_SELECTOR,
            help="逗号分隔的候选 CSS 选择器，站点改版时可在实例配置中覆盖",
        ),
        FieldDef(
            name="checkin_url",
            label="签到页地址",
            type="string",
            required=False,
            default="",
            help="留空=登录落地页直接找签到按钮；填相对路径如 /checkin",
        ),
        FieldDef(
            name="checkin_button_selector",
            label="签到按钮选择器",
            type="string",
            required=False,
            default=_DEFAULT_CHECKIN_BUTTON_SELECTOR,
            help="逗号分隔的候选 CSS 选择器，站点改版时可在实例配置中覆盖",
        ),
        FieldDef(
            name="checkin_already_text",
            label="已签到文本",
            type="string",
            required=False,
            default=_DEFAULT_CHECKIN_ALREADY_TEXT,
            help="页面含这些文本之一即视为今日已签到（逗号分隔）",
        ),
        FieldDef(
            name="checkin_success_text",
            label="签到成功文本",
            type="string",
            required=False,
            default=_DEFAULT_CHECKIN_SUCCESS_TEXT,
            help="点击后页面出现这些文本之一即视为签到成功（逗号分隔）",
        ),
    ]
    credential_schema: ClassVar[list] = [
        FieldDef(
            name="username",
            label="用户名",
            type="string",
            required=True,
            help="保活签到必填（浏览器自动登录用）",
        ),
        FieldDef(
            name="password",
            label="密码",
            type="secret",
            required=True,
            help="保活签到必填（浏览器自动登录用）",
        ),
        FieldDef(
            name="totp_secret",
            label="两步验证密钥",
            type="secret",
            required=False,
            help="开启两步验证的账号必填；未开启可留空",
        ),
        FieldDef(
            name="api_key",
            label="API Key",
            type="secret",
            required=False,
            help="可选：控制台 → 实验室 → 存取令牌，配置后信息查询任务直接走 API",
        ),
    ]
    account_schema: ClassVar[list] = [
        FieldDef(
            name="login_hint",
            label="保活凭据说明",
            type="string",
            required=False,
            default="",
            help="凭据字典需包含 username/password/totp_secret（保活）"
            "与 api_key（信息查询），可只配其一",
        ),
    ]
    task_definitions: ClassVar[list] = [
        TaskDefinition(name="get_user_info", description="查询用户信息与魔力", default_time="09:00"),
        TaskDefinition(
            name="daily_checkin",
            description="登录保活 + 站内签到（防止 40 天未登录删号）",
            requires_browser=True,
            default_time="08:30",
            produces_resources=False,
        ),
    ]

    async def execute(self, task_name: str, context: TaskContext) -> TaskResult:
        if task_name not in {t.name for t in self.task_definitions}:
            return TaskResult.failed(f"未知任务: {task_name}")

        if task_name == "daily_checkin":
            return await self._keepalive(context)

        http = context.http
        if http is None:
            return TaskResult.failed("运行时未提供 HTTP 客户端")

        api_key = str((context.credentials or {}).get("api_key") or "")
        if not api_key:
            return TaskResult.auth_expired(
                "未配置 API Key（控制台 → 实验室 → 存取令牌）。"
                "注意：本检测走 API 查询，只验证 api_key；"
                "用户名/密码凭据会在每日签到任务（浏览器登录）中验证"
            )

        config = context.config or {}
        http.set_default_headers({"x-api-key": api_key})
        path = str(config.get("profile_path") or "/api/member/profile")

        try:
            return await self._get_user_info(http, path)
        except httpx.TimeoutException:
            return TaskResult.failed("请求超时", retryable=True)
        except httpx.HTTPError as e:
            return TaskResult.failed(f"网络错误: {type(e).__name__}", retryable=True)

    # ------------------------------------------------------------------
    # 浏览器登录保活
    # ------------------------------------------------------------------

    async def _keepalive(self, context: TaskContext) -> TaskResult:
        """登录保活 + 站内签到：先建立/复用会话，再执行站内签到。

        登录成功的判据是捕获到 SPA 发出的 /api/member/profile 200 响应；
        execute 返回后浏览器 Worker 会自动持久化 storage state 供下次复用。
        """
        browser = context.browser
        if browser is None:
            return TaskResult.needs_action("浏览器会话未注入（应由浏览器 Worker 执行）")

        creds = context.credentials or {}
        config = context.config or {}
        result = await self._login_only(browser, creds, config)
        if result.status != TaskStatus.SUCCESS:
            return result

        kind, msg = await self._do_checkin(browser.page, config)
        data = {
            "logged_in": True,
            "method": (result.data or {}).get("method"),
            "checkin": kind,
        }
        if kind == "done":
            return TaskResult.ok("签到成功（登录保活完成）", data=data)
        return TaskResult.ok(f"登录保活成功；{msg}", data=data)

    async def _login_only(self, browser: Any, creds: dict, config: dict) -> TaskResult:
        """浏览器登录保活：优先复用已持久化的会话，失效时用账号密码 + TOTP 登录。"""
        username = str(creds.get("username") or "")
        password = str(creds.get("password") or "")
        totp_secret = str(creds.get("totp_secret") or "")
        site = str(config.get("site_url") or _DEFAULT_SITE_URL).rstrip("/")
        timeout_ms = int(float(config.get("login_timeout_seconds") or 60)) * 1000
        username_selector = str(config.get("username_selector") or _DEFAULT_USERNAME_SELECTOR)
        password_selector = str(config.get("password_selector") or _DEFAULT_PASSWORD_SELECTOR)
        login_button_selector = str(
            config.get("login_button_selector") or _DEFAULT_LOGIN_BUTTON_SELECTOR
        )
        totp_selector = str(config.get("totp_selector") or _DEFAULT_TOTP_SELECTOR)

        page = browser.page
        profile_seen: dict = {}

        def _on_response(resp: Any) -> None:
            if "/api/member/profile" in resp.url:
                profile_seen["url"] = resp.url
                profile_seen["status"] = resp.status

        page.on("response", _on_response)

        try:
            # 1) 打开首页，若已登录 SPA 会自动请求 /api/member/profile
            try:
                await page.goto(site, wait_until="domcontentloaded", timeout=timeout_ms)
                await page.wait_for_timeout(4000)  # 等待 SPA 启动
            except PlaywrightTimeout:
                return TaskResult.failed(f"打开站点超时: {site}", retryable=True)

            if profile_seen.get("status") == 200:
                return TaskResult.ok(
                    "保活成功（已有有效会话，页面访问完成）",
                    data={"logged_in": True, "method": "session_reuse"},
                )

            # 2) 未登录 → 需要账号密码 + TOTP
            if not (username and password):
                return TaskResult.auth_expired(
                    "未配置 username/password 凭据，且现有会话已失效，无法自动登录"
                )

            try:
                await page.goto(
                    f"{site}/login", wait_until="domcontentloaded", timeout=timeout_ms
                )
            except PlaywrightTimeout:
                return TaskResult.failed(f"打开登录页超时: {site}/login", retryable=True)

            # 表单元素按候选选择器依次尝试
            form_timeout = min(10_000, timeout_ms)
            if not await self._try_fill(page, username_selector, username, form_timeout):
                return TaskResult.needs_action(
                    "未找到用户名输入框（站点页面结构可能已变化，"
                    "可在插件配置中调整 username_selector）"
                )
            if not await self._try_fill(page, password_selector, password, form_timeout):
                return TaskResult.needs_action(
                    "未找到密码输入框（站点页面结构可能已变化，"
                    "可在插件配置中调整 password_selector）"
                )
            if not await self._try_click(page, login_button_selector, form_timeout):
                return TaskResult.needs_action(
                    "未找到登录按钮（站点页面结构可能已变化，"
                    "可在插件配置中调整 login_button_selector）"
                )

            # 3) 若出现两步验证输入框 → 填入 TOTP 后再次提交
            await page.wait_for_timeout(2000)
            totp_input = await self._first_visible(page, totp_selector, 1500)
            if totp_input is not None:
                if not totp_secret:
                    return TaskResult.auth_expired(
                        "登录需要两步验证，但凭据未配置 totp_secret："
                        "编辑账号 → 凭据字段“两步验证密钥”，填入绑定验证器时的"
                        "Base32 密钥（如 JBSWY3DPEHPK3PXP；未保存过可在站点"
                        "两步验证设置里重新绑定获取）"
                    )
                try:
                    await totp_input.fill(_totp_now(totp_secret), timeout=5000)
                except Exception:  # noqa: BLE001 - 单个元素操作失败走兜底提示
                    return TaskResult.needs_action(
                        "两步验证码填写失败（站点页面结构可能已变化，"
                        "可在插件配置中调整 totp_selector）"
                    )
                if not await self._try_click(page, login_button_selector, 5000):
                    return TaskResult.needs_action(
                        "未找到两步验证确认按钮（可在插件配置中调整 login_button_selector）"
                    )

            # 4) 轮询等待登录完成（SPA 请求 /api/member/profile 且返回 200）
            deadline = time.monotonic() + timeout_ms / 1000
            while time.monotonic() < deadline:
                if profile_seen.get("status") == 200:
                    return TaskResult.ok(
                        "登录保活成功",
                        data={"logged_in": True, "method": "credential_login"},
                    )
                await page.wait_for_timeout(1000)

            if "/login" in page.url:
                return TaskResult.auth_expired("登录失败：凭据可能错误或需要二次验证")
            return TaskResult.failed(
                "登录后未检测到会话建立（未捕获 /api/member/profile 200 响应）",
                retryable=True,
            )
        except Exception as exc:  # noqa: BLE001 - 浏览器流程异常统一转失败
            return TaskResult.failed(f"保活执行异常: {exc}", retryable=True)

    async def _do_checkin(self, page: Any, config: dict) -> tuple[str, str]:
        """登录成功后执行站内签到。

        返回 (checkin_kind, 描述)：done / already / not_found / clicked_unconfirmed / error。
        找不到签到入口不判失败——保活目的已达成，结果在 data["checkin"] 里可观测。
        """
        site = str(config.get("site_url") or _DEFAULT_SITE_URL).rstrip("/")
        timeout_ms = int(float(config.get("login_timeout_seconds") or 60)) * 1000
        button_selector = str(
            config.get("checkin_button_selector") or _DEFAULT_CHECKIN_BUTTON_SELECTOR
        )

        def _tokens(raw: object) -> list[str]:
            return [t.strip() for t in str(raw).split(",") if t.strip()]

        already_tokens = _tokens(config.get("checkin_already_text") or _DEFAULT_CHECKIN_ALREADY_TEXT)
        success_tokens = _tokens(config.get("checkin_success_text") or _DEFAULT_CHECKIN_SUCCESS_TEXT)

        async def _body_text() -> str:
            try:
                return str(await page.evaluate("() => document.body.innerText") or "")
            except Exception:  # noqa: BLE001 - 取文本失败按空处理
                return ""

        try:
            checkin_url = str(config.get("checkin_url") or "").strip()
            if checkin_url:
                target = checkin_url if checkin_url.startswith("http") else f"{site}/{checkin_url.lstrip('/')}"
                await page.goto(target, wait_until="domcontentloaded", timeout=timeout_ms)
                await page.wait_for_timeout(3000)

            body = await _body_text()
            if any(token in body for token in already_tokens):
                return "already", "站点提示今日已签到"

            if not await self._try_click(page, button_selector, 8000):
                return (
                    "not_found",
                    "未找到签到按钮（可在实例配置中调整 checkin_button_selector 或 checkin_url）",
                )

            await page.wait_for_timeout(3000)
            body = await _body_text()
            if any(token in body for token in success_tokens):
                return "done", "签到成功"
            if any(token in body for token in already_tokens):
                return "already", "点击后站点提示今日已签到"
            return "clicked_unconfirmed", "签到按钮已点击，但未检测到结果提示（请到站点确认）"
        except Exception as exc:  # noqa: BLE001 - 签到阶段异常不推翻保活结果
            return "error", f"签到阶段异常: {exc}"

    @staticmethod
    async def _try_fill(page: Any, selector_list: str, value: str, timeout_ms: int) -> bool:
        """按逗号分隔的候选选择器依次尝试填充，任一成功即返回 True。"""
        for sel in (s.strip() for s in selector_list.split(",")):
            if not sel:
                continue
            try:
                await page.locator(sel).first.fill(value, timeout=timeout_ms)
                return True
            except Exception:  # noqa: BLE001 - 候选失败换下一个
                continue
        return False

    @staticmethod
    async def _try_click(page: Any, selector_list: str, timeout_ms: int) -> bool:
        """按逗号分隔的候选选择器依次尝试点击，任一成功即返回 True。"""
        for sel in (s.strip() for s in selector_list.split(",")):
            if not sel:
                continue
            try:
                await page.locator(sel).first.click(timeout=timeout_ms)
                return True
            except Exception:  # noqa: BLE001 - 候选失败换下一个
                continue
        return False

    @staticmethod
    async def _first_visible(page: Any, selector_list: str, timeout_ms: int) -> Any:
        """返回第一个可见的候选元素 Locator，全部不可见则返回 None。"""
        for sel in (s.strip() for s in selector_list.split(",")):
            if not sel:
                continue
            try:
                locator = page.locator(sel).first
                await locator.wait_for(state="visible", timeout=timeout_ms)
                return locator
            except Exception:  # noqa: BLE001 - 候选失败换下一个
                continue
        return None

    # ------------------------------------------------------------------
    # API Key 查询用户信息
    # ------------------------------------------------------------------

    async def _get_user_info(self, http: HttpClient, path: str) -> TaskResult:
        resp = await http.post(path, json={})
        if resp.status_code in (401, 403):
            return TaskResult.auth_expired("API Key 无效或已过期")
        if resp.status_code == 429:
            return TaskResult(
                success=False,
                status=TaskStatus.RATE_LIMITED,
                message="请求过于频繁（HTTP 429）",
            )
        content_type = resp.headers.get("content-type", "")
        if "json" not in content_type.lower():
            return TaskResult.needs_action("站点返回非 JSON 响应")

        payload = resp.json()
        data = payload.get("data") or {}

        # 防御式提取：字段缺失或类型异常时不至于崩溃
        username = str(data.get("username") or data.get("name") or "")
        bonus = self._as_number(data.get("bonus"))
        upload = self._as_number(data.get("uploaded"))
        download = self._as_number(data.get("downloaded"))
        share_rate = self._as_number(data.get("share_rate"))

        resources: list[dict] = []
        if bonus is not None:
            resources.append({"resource_type": "bonus", "value": bonus, "unit": "BOSON"})
        if upload is not None:
            resources.append({"resource_type": "upload", "value": upload, "unit": "bytes"})
        if download is not None:
            resources.append(
                {"resource_type": "download", "value": download, "unit": "bytes"}
            )
        if share_rate is not None:
            resources.append(
                {"resource_type": "share_rate", "value": share_rate, "unit": "x"}
            )

        result_data = {
            "username": username,
            "user_id": data.get("id"),
            # 原始字段名快照，便于排查站点字段差异
            "raw_keys": sorted(data.keys())[:30],
        }
        if resources:
            result_data["resources"] = resources

        return TaskResult.ok(f"用户信息获取成功: {username}", result_data)

    @staticmethod
    def _as_number(value: object) -> float | None:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        return float(value)
