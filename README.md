# SupportOps Agent

SupportOps Agent 是一个本地可部署的智能客服工单分类、检索与自动处理系统。当前仓库是独立项目，复用了原工程中必要的认证、文档解析、Elasticsearch 检索和 SSE 能力，并删除了旧聊天、旧知识库页面、旧语音接口和上一个项目的业务入口。

## 技术栈

- Backend: FastAPI, SQLAlchemy, Alembic, JWT, SSE
- Frontend: React, Vite, TypeScript, Ant Design
- Storage: PostgreSQL, Elasticsearch, Redis
- Agent Runtime: LangGraph 1.x, PostgreSQL Checkpoint, Human-in-the-loop
- AI: DashScope / 阿里云百炼 OpenAI-compatible API
- Retrieval: Elasticsearch hybrid/vector search
- Deploy: Docker Compose

## Agent 流程

```mermaid
flowchart TD
  U[客服问题] --> P[Planner / Context]
  P --> I[intent_classifier]
  I --> R[FAQ RAG]
  I --> S[相似工单检索]
  R --> E[escalation_checker]
  S --> E
  E --> G[response_generator]
  G --> F[reflection]
  F -->|证据不足且未达重试上限| Q[query_rewrite]
  Q --> R
  Q --> S
  F -->|高风险| H[interrupt: 人工审核]
  H -->|approve / edit / reject| A[finalize]
  F -->|质量通过| A
  A --> O[Final Answer]
  P --> T[(agent_traces)]
  I --> T
  R --> T
  S --> T
  E --> T
  G --> T
  F --> T
  Q --> T
  H --> T
```

最终答案包含 `category`、`intent`、`risk_level`、`need_human`、自动回复、相似工单、引用依据、Agent 执行轨迹、重试次数、人工审核结果和下一步处理建议。

### 状态与可靠性

- `session_id` 与 JWT 用户 ID 共同映射为 LangGraph `thread_id`，避免跨用户会话碰撞。
- PostgreSQL checkpointer 持久化每个节点的状态；服务重启后仍能恢复待审核工作流。
- FAQ RAG 与相似工单召回使用并行节点，每个节点创建独立 SQLAlchemy Session。
- `reflection` 是真实条件路由：证据不足时改写查询并重新检索，而不是只输出检查文案。
- 投诉、退款、支付、隐私和账号安全等高风险场景通过 `interrupt` 暂停，必须人工批准、修改或拒绝后才能完成。
- 如果 PostgreSQL checkpoint 初始化失败，开发环境会降级到内存 saver；可通过 `GET /supportops/workflow/status` 检查 `durable` 是否为 `true`。

## 数据准备

历史工单 CSV 兼容 Hugging Face Bitext customer support dataset 字段：

- `instruction`: 用户问题
- `category`: 问题大类
- `intent`: 用户意图
- `response`: 标准客服回复

可直接上传项目根目录的 `sample_tickets.csv`。FAQ / 产品说明支持 PDF、DOCX、TXT、MD。

## 启动方式

```bash
cd backend
cp .env.example .env
docker compose up -d --build
```

访问地址：

- Frontend: http://localhost:5181
- SupportOps 页面: http://localhost:5181/supportops
- Backend API docs: http://localhost:8000/docs

首次进入页面后先注册账号再登录。API Key 可在页面右侧 `API Key 管理` 中新增、测试、启用、编辑和删除；系统也支持在 `backend/.env` 中配置：

```env
DASHSCOPE_API_KEY=sk-你的真实DashScopeKey
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
SUPPORTOPS_MODEL=qwen-plus
SUPPORTOPS_CHECKPOINT_POOL_SIZE=8
DASHSCOPE_EMBEDDING_MODEL=text-embedding-v3
DATABASE_URL=postgresql://postgres:pg123456@supportops_pg:5432/gsk
ES_HOST=http://supportops_es:9200
REDIS_HOST=supportops_redis
JWT_SECRET_KEY=supportops_local_secret
```

当前版本只支持 DashScope / 阿里云百炼作为完整 AI 供应商。DeepSeek 可用于对话类接口，但不能完整覆盖本项目的 FAQ / 工单 embedding 检索链路，所以没有作为可替代提供商开放。

## 使用流程

1. 注册并登录。
2. 在 `API Key 管理` 中新增 DashScope API Key，点击 `测试当前配置`，确认对话模型和 Embedding 模型可用。
3. 上传 `sample_tickets.csv` 或自己的 Bitext 格式 CSV。
4. 上传 FAQ / 产品说明文档。
5. 在客服 Agent 对话区输入问题，查看实时执行轨迹、引用来源、相似工单、风险等级和最终处理建议。

## API 列表

- `POST /login`: 登录
- `POST /register`: 注册
- `POST /supportops/upload_tickets`: 上传历史工单 CSV
- `POST /supportops/upload_docs`: 上传 FAQ / 产品说明文档
- `POST /supportops/chat?session_id=xxx`: SSE 流式客服 Agent 问答
- `POST /supportops/chat/resume?session_id=xxx`: 提交人工审核决定并恢复工作流
- `GET /supportops/reviews/{session_id}`: 查询会话是否存在待处理人工审核
- `GET /supportops/workflow/status`: 查询 LangGraph checkpoint 后端与持久化状态
- `GET /supportops/tickets`: 获取历史工单列表
- `GET /supportops/traces/{session_id}`: 获取 Agent 执行轨迹
- `GET /supportops/metrics`: 获取看板指标
- `GET /supportops/api_keys`: 获取当前用户 API Key 列表
- `POST /supportops/api_keys`: 新增 API Key
- `POST /supportops/api_keys/test`: 测试表单中的 DashScope 配置
- `PUT /supportops/api_keys/{key_id}`: 修改 API Key
- `POST /supportops/api_keys/{key_id}/activate`: 启用指定 API Key
- `POST /supportops/api_keys/{key_id}/test`: 测试已保存的 API Key
- `DELETE /supportops/api_keys/{key_id}`: 删除 API Key

## 简历写法

- 基于 FastAPI、React、PostgreSQL、Elasticsearch、Redis 和 JWT 搭建本地可部署的客服工单 Agent 系统，支持工单 CSV 清洗入库、FAQ 文档 RAG 检索、相似历史工单召回和 SSE 实时执行轨迹展示。
- 基于 LangGraph 1.x 将意图识别、并行混合检索、风险升级、回复生成与质量反思建模为可恢复状态图，并将节点输入、输出、耗时和状态持久化到 `agent_traces`。
- 通过 PostgreSQL Checkpoint 实现会话级多轮状态、失败恢复与 Human-in-the-loop；高风险工单可暂停并由人工批准、修改或拒绝后恢复执行。
- 建立客服 Agent 离线评测工具，覆盖意图分类 Macro-F1、风险升级 Precision/Recall/F1/漏判率以及检索 Recall@K/MRR。

## 测试与离线评测

后端状态图和指标测试：

```bash
cd backend/app
python -m unittest discover -s tests -v
```

运行内置客服意图与风险规则烟雾评测：

```bash
cd backend/app
python scripts/evaluate_supportops.py
```

内置 `evals/supportops_cases.jsonl` 是小规模回归集，用来防止基础规则退化，不应当作生产效果证明。投简历或部署前，应替换或扩充为人工标注的留出集，并补充 FAQ/工单的相关文档 ID，从而计算真实的 Recall@K 与 MRR。

## 后续可扩展方向

- 增加人工客服处理状态流转和 SLA 规则。
- 为 `tickets` 增加反馈闭环字段，如满意度、是否解决、人工处理结果。
- 引入更细粒度的租户/角色权限。
- 增加附件 OCR 和结构化订单/物流查询工具。
- 使用人工处理结果和满意度构建生产反馈闭环，统计自动解决率与人工覆盖后的净收益。
