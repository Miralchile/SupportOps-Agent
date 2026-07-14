# SupportOps Agent Backend

FastAPI 后端，包含 JWT 登录注册、SupportOps 工单上传、FAQ 文档索引、LangGraph 状态化 Agent、PostgreSQL Checkpoint、人工审核恢复、SSE 执行轨迹、离线评测、指标看板和 API Key 管理。

```bash
cp .env.example .env
docker compose up -d --build
```

API 文档地址：http://localhost:8000/docs

启动后可请求 `GET /supportops/workflow/status`，确认 checkpoint 返回 `"durable": true`。
