"""DailyKeeper Agent — 本地执行端（阶段 5b）。

通过 HTTPS 与 DailyKeeper 服务器通信：心跳注册 → 认领任务 → 拉取执行上下文
（含凭据）→ 调用本地安装的平台插件执行 → 回传结果。平台插件来自 Agent 自身
的 Python 环境（entry points 组 ``dailykeeper.plugins``）。
"""

__version__ = "0.1.0"
