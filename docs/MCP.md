# DailyKeeper MCP Server

MCP Server（stdio）把 DailyKeeper 能力暴露给 Claude Desktop / Claude Code 等 MCP 客户端：AI 助手可以查询账号状态、定时任务、执行记录与资源余额，并在确认后立即触发一次签到任务。

包名 `dailykeeper-mcp`，命令入口 `dk-mcp`，源码位于 `mcp-server/`。

## 安装

```bash
# 在仓库根目录的虚拟环境中
pip install -e mcp-server
```

## 工具列表

| 工具 | 用途 |
| --- | --- |
| `get_overview` | 系统总览：账号数、今日任务数、今日成功数、在线 Agent 数、已加载插件数、调度器心跳状态 |
| `list_accounts` | 列出所有平台账号：平台、实例、状态（ACTIVE/AUTH_EXPIRED/DISABLED）、启用、最近签到日期 |
| `list_scheduled_tasks` | 列出定时任务：账号、任务、执行时间、周期、启用、下次执行 |
| `list_executions` | 查询最近任务执行记录（含结果消息与状态），可按状态过滤（SUCCESS/FAILED/AUTH_EXPIRED/NEEDS_ACTION/RATE_LIMITED/SKIPPED/INTERRUPTED/PENDING/RUNNING），`limit` 上限 50 |
| `get_execution` | 查询单条执行详情（含完整结果 data/metrics） |
| `run_task_now` | 立即触发一次定时任务（受当日幂等去重保护；返回 created/execution_id/message） |
| `get_resources` | 查询资源最新快照总览（余额/积分/魔力/上传下载等，按账号分组） |

## 配置（环境变量）

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `DK_MCP_SERVER_URL` | 否 | DailyKeeper 后端地址，默认 `http://127.0.0.1:8000` |
| `DK_MCP_TOKEN` | 二选一 | 静态访问令牌（Bearer） |
| `DK_MCP_USERNAME` | 二选一 | 管理员用户名（与 `DK_MCP_PASSWORD` 同时提供时自动登录） |
| `DK_MCP_PASSWORD` | 二选一 | 管理员密码 |
| `DK_MCP_TIMEOUT_SECONDS` | 否 | 请求超时秒数，默认 60 |

认证二选一：提供 `DK_MCP_TOKEN`，或同时提供 `DK_MCP_USERNAME` 与 `DK_MCP_PASSWORD`（首次调用时自动登录，令牌过期后自动重登录）。

## Claude Desktop 配置

编辑 `claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "dailykeeper": {
      "command": "/path/to/.venv/bin/dk-mcp",
      "env": {
        "DK_MCP_SERVER_URL": "https://your-server.com",
        "DK_MCP_USERNAME": "admin",
        "DK_MCP_PASSWORD": "..."
      }
    }
  }
}
```

## Claude Code 配置

```bash
claude mcp add dailykeeper \
  --env DK_MCP_SERVER_URL=https://your-server.com \
  --env DK_MCP_USERNAME=admin \
  --env DK_MCP_PASSWORD='...' \
  -- /path/to/dk-mcp
```

## 安全注意

- 凭据仅保存在 MCP 客户端配置中，不要写入代码仓库或脚本。
- 生产部署必须通过 HTTPS 访问 DailyKeeper 后端（`DK_MCP_SERVER_URL` 使用 `https://`）。
- `run_task_now` 是唯一的写操作，且受当日幂等去重保护（同账号同任务同业务日期只会创建一次执行）；其余工具均为只读。
- 建议为 AI 助手使用独立的管理员账号并定期修改密码。
