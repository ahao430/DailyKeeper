"""``dk-agent`` 命令行入口：参数解析 + 启动横幅，然后交给主循环。"""

from __future__ import annotations

import argparse
import sys

from dailykeeper_agent import __version__
from dailykeeper_agent.config import load_config
from dailykeeper_agent.main import main_sync, plugin_ids
from dailykeeper_sdk.registry import plugin_registry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dk-agent", description="DailyKeeper Agent — 本地任务执行端"
    )
    parser.add_argument("--server", help="服务器地址（默认取 DK_AGENT_SERVER 环境变量）")
    parser.add_argument("--token", help="Agent 令牌（默认取 DK_AGENT_TOKEN 环境变量）")
    parser.add_argument(
        "--poll", type=float, default=None, metavar="SECONDS",
        help="空轮询间隔秒数（默认取 DK_AGENT_POLL_SECONDS，缺省 5）",
    )
    parser.add_argument("--version", action="version", version=f"dk-agent {__version__}")
    return parser


def main(argv: list[str] | None = None) -> None:
    """解析参数 → 环境变量兜底 → 覆盖配置 → 启动主循环。"""
    args = build_parser().parse_args(argv)

    try:
        config = load_config(server_url=args.server, token=args.token)
    except ValueError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    if args.poll is not None:
        if args.poll <= 0:
            print("配置错误: --poll 必须为正数", file=sys.stderr)
            raise SystemExit(2)
        config.poll_seconds = args.poll

    plugin_registry.load_entry_points()  # 幂等；横幅需要列出本机插件
    print(f"DailyKeeper Agent v{__version__}")
    print(f"服务器: {config.server_url}")
    print(f"已加载插件: {', '.join(plugin_ids()) or '无（请安装平台插件包）'}")
    print(f"轮询间隔: {config.poll_seconds:g}s | 心跳间隔: {config.heartbeat_seconds:g}s | 并发: {config.task_concurrency}")
    main_sync(config)


if __name__ == "__main__":
    main()
