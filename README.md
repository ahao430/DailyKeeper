# DailyKeeper

**One Platform. All Your Daily Tasks.**

DailyKeeper is a self-hosted, extensible automation platform for managing multiple accounts and automating routine tasks across websites, online services, and desktop applications.

It brings account management, daily check-in service, scheduled tasks, task execution records, resource monitoring, and cross-platform automation together in one unified dashboard.

## Features

- **Multi-platform Management** — Manage accounts and services from different platforms in one place.
- **Automated Daily Tasks** — Schedule daily check-ins, reward collection, and routine operations.
- **Account Management** — Manage auth credentials, sessions, and login status.
- **Resource Monitoring** — Track balances, credits, quotas, usage, and expiration times.
- **Extensible Plugin System** — Add new platforms and capabilities through a unified plugin SDK.
- **Browser Automation** — Automate supported web workflows with Playwright (browser worker, later phase).
- **Local Agent** — Extend automation to local desktop applications and browsers (later phase).
- **Notifications** — Bark / Gotify / Webhook with per-event toggles.
- **Self-hosted** — Deploy and manage your own automation service.

## Technology Stack

- Backend: Python 3.12+, FastAPI
- Monorepo: backend / sdk / plugins / local-agent / frontend / deploy / docs
- Database: SQLite (PostgreSQL-ready)
- Browser Automation: Playwright (later phase)
- Task Scheduling: APScheduler
- Deployment: Docker Compose
- License: MIT

## Quick Start (Docker Compose)

```bash
git clone git@github.com:ahao430/DailyKeeper.git
cd DailyKeeper
cp deploy/.env.example deploy/.env
docker compose -f deploy/docker-compose.yml up -d --build
# Swagger UI: http://localhost:8000/docs
```

## Quick Start (Source)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e sdk -e plugins/demo -e plugins/newapi -e plugins/mteam -e plugins/nexusphp -e backend
uvicorn app.main:app --reload
# Swagger UI: http://localhost:8000/docs
# 默认管理员 admin / admin123，首次登录后请修改密码
```

## Project Structure

```
dailykeeper/
├── backend/        # DailyKeeper Server
├── sdk/            # DailyKeeper SDK
├── plugins/        # DailyKeeper Plugins
├── local-agent/    # DailyKeeper Agent (phase 5, placeholder)
├── frontend/       # DailyKeeper Dashboard (phase 4, placeholder)
├── deploy/         # Docker Compose deployment
└── docs/           # PRD, ARCHITECTURE, PLUGIN_SDK, DATABASE, API, DEPLOYMENT
```

## Documentation

- [PRD](docs/PRD.md) — product requirements and scope
- [ARCHITECTURE](docs/ARCHITECTURE.md) — system architecture and module boundaries
- [PLUGIN_SDK](docs/PLUGIN_SDK.md) — plugin interface, registration, dev guide
- [DATABASE](docs/DATABASE.md) — data model and relationships
- [API](docs/API.md) — auth, platforms, accounts, tasks, executions, resources, system
- [DEPLOYMENT](docs/DEPLOYMENT.md) — Docker Compose deployment guide
- [plan.md](plan.md) — 原始项目规划（V1.0）
