# DailyKeeper Dashboard

Vue 3 + TypeScript + Element Plus 管理后台（每日管家前端）。

## 技术栈

- Vue 3（`<script setup>` 组合式 API）+ TypeScript
- Vite 5 构建与开发服务器
- Element Plus 组件库 + `@element-plus/icons-vue`
- vue-router 4（history 模式，带登录守卫）
- axios（统一封装于 `src/api/client.ts`，自动携带 token、401 跳转登录页）
- dayjs（时间格式化）

## 开发

需先在 8000 端口运行后端（见根 README 的 Quick Start (Source)），Vite 已配置 `/api` 代理到 `http://127.0.0.1:8000`。

```bash
cd frontend
npm install
npm run dev
# 打开 http://localhost:5173
# 默认管理员 admin / admin123，首次登录后请在系统设置中修改密码
```

## 构建

```bash
npm run build    # 产物输出到 dist/
npm run typecheck
```

## 部署（Docker Compose）

前端镜像基于 `frontend/Dockerfile`（多阶段：node 构建 → nginx 托管），nginx 同时反代 `/api/` 到 `api:8000` 并做 SPA history 路由回退。

```bash
cp deploy/.env.example deploy/.env
docker compose -f deploy/docker-compose.yml up -d --build frontend
# 控制台: http://localhost:8080
```

## 页面说明

| 路由 | 页面 | 说明 |
| --- | --- | --- |
| `/login` | 登录 | 管理员登录，默认密码时显示修改提醒 |
| `/` | 总览 | 系统信息、今日任务统计、调度心跳 |
| `/platforms` | 平台管理 | 平台实例 CRUD、账号与凭据管理、凭据检测 |
| `/tasks` | 任务中心 | 定时任务列表、新增/编辑（执行时间、周期、参数）、立即执行、启停与删除 |
| `/executions` | 执行日志 | 按状态/账号/任务过滤，详情抽屉展示结构化结果与指标 |
| `/resources` | 资源看板 | 每账号资源最新值总览、快照记录过滤查询 |
| `/settings` | 系统设置 | 通知开关、事件开关、通知渠道（Bark / Gotify / Webhook）管理与测试、修改密码 |

## API 对接说明

- 所有请求走 `/api` 前缀：开发环境由 Vite proxy 转发到 8000；容器内由 nginx `proxy_pass` 到 `api:8000`。
- 认证 token 存于 `localStorage`（key `dk_token`），请求拦截器自动附加 `Authorization: Bearer`；401 时清除 token 并跳回 `/login`。
- 接口封装在 `src/api/index.ts`，类型定义在 `src/api/types.ts`（与 `backend/app/api/*.py` 响应一一对应）；完整 API 文档见 [docs/API.md](../docs/API.md)。
