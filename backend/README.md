# SupportOps Agent Backend

FastAPI 后端，包含 JWT 登录注册、SupportOps 工单上传、FAQ 文档索引、LangGraph 状态化 Agent、PostgreSQL Checkpoint、人工审核恢复、SSE 执行轨迹、离线评测、指标看板和 API Key 管理。

```bash
cp .env.example .env
docker compose up -d --build
```

API 文档地址：http://localhost:8000/docs

- 数据库表在应用启动时自动创建（`utils/database.py: init_db`），无需手动迁移。
- 检索层位于 `app/service/retrieval/`：jieba 分词、pdfplumber / python-docx 文档解析、DashScope Embedding、Elasticsearch BM25 + kNN 混合检索；无有效 API Key 时自动降级为关键词检索。
- 启动后可请求 `GET /supportops/workflow/status`，确认 checkpoint 返回 `"durable": true`；`GET /health` 用于存活检查。

本地跑测试与离线评测：

```bash
cd app
python -m unittest discover -s tests -v
python scripts/evaluate_supportops.py --mode both --user-id 1
python scripts/evaluate_retrieval.py --with-embeddings --user-id 1 --limit 100
```

`--user-id` 会从数据库读取该用户的 active API Key（与生产一致的解析链路）；不带时使用环境变量。评测方法与实测结果见根目录 README 的「评测结果」章节。
