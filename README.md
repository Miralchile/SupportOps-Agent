# SupportOps Agent

[![CI](https://github.com/Miralchile/SupportOps-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Miralchile/SupportOps-Agent/actions/workflows/ci.yml)

SupportOps Agent 是一个本地可部署的智能客服工单分类、检索与自动处理系统。代码遵循最小化原则：检索与文档解析是自研的轻量模块（`backend/app/service/retrieval/`，jieba 分词 + pdfplumber/python-docx 解析 + Elasticsearch 混合检索），不携带任何本地模型权重，依赖清单只保留实际用到的包。

## 技术栈

- Backend: FastAPI, SQLAlchemy, JWT, SSE
- Frontend: React, Vite, TypeScript, Ant Design
- Storage: PostgreSQL, Elasticsearch
- Agent Runtime: LangGraph 1.x, PostgreSQL Checkpoint, Human-in-the-loop
- AI: DashScope / 阿里云百炼 OpenAI-compatible API
- Retrieval: Elasticsearch BM25 + kNN 向量混合检索（加权融合，无 Embedding 时自动降级为纯关键词检索）
- Deploy: Docker Compose

## 目录结构

```
backend/app/
  app_main.py            # FastAPI 入口；启动时自动建表
  router/                # /login /register 与 /supportops/* 路由
  service/supportops/    # LangGraph 状态图、节点实现、数据接入、评测、API Key
  service/retrieval/     # 轻量检索层：解析 / 分词 / Embedding / ES / 混合检索
  models/  schemas/      # SQLAlchemy 模型与 Pydantic 响应模型
  tests/  evals/  scripts/
frontend/src/            # React 工作台（SSE 流式轨迹 + 人工审核 UI）
data/external/tweetsumm/ # TweetSumm 数据集与许可证
```

## Agent 流程

```mermaid
flowchart TD
  U[客服问题] --> P[planner: 路由与工具规划]
  P --> I[intent_classifier]
  I --> R[FAQ RAG]
  I --> S[相似工单检索]
  I --> T[business_tools: 订单/物流/退款资格]
  R --> E[escalation_checker]
  S --> E
  T --> E
  E --> G[response_generator]
  G --> F[reflection]
  F -->|证据不足且未达重试上限| Q[query_rewrite]
  Q --> R
  Q --> S
  F -->|高风险| H[interrupt: 人工审核]
  H -->|approve / edit / reject| A[finalize]
  F -->|质量通过| A
  A --> O[Final Answer]
```

`planner` 是真实决策节点：由 LLM 规划本轮的检索路径（FAQ / 相似工单）和业务工具调用（订单、物流、退款资格三个确定性 mock 工具），输出经白名单校验；无有效 API Key 时回退到确定性规划（订单号 + 话题检测）。被规划器跳过的路径在执行轨迹中显式记录为 `skipped`，工具结果贯穿风险判断、回复生成与反思，并随最终答案返回。所有节点的输入、输出、耗时和状态持久化到 `agent_traces` 表。

最终答案包含 `category`、`intent`、`risk_level`、`need_human`、自动回复、工具查询结果、执行计划、相似工单、引用依据、Agent 执行轨迹、重试次数、人工审核结果和下一步处理建议。

## 界面预览

工作台全景：状态卡、多轮对话与会话记录（右侧可见同一账号下自动回复 / 人工审核后回复 / 转人工三种处理结果）。

![工作台](docs/screenshots/workbench.png)

执行轨迹：planner 输出真实的路由与工具决策理由，business_tools 返回确定性查询结果，每个节点的输入输出、状态与耗时可审计。

![执行轨迹](docs/screenshots/agent-trace.png)

高风险 interrupt：投诉 + 退款请求触发人工审核，工作流暂停并展示升级理由（引用了业务工具结果与知识库案例），支持批准 / 修改后发送 / 拒绝并转人工。

![人工审核](docs/screenshots/human-review.png)

运营与配置：工单资产（含来源与数据切分治理字段）、外部数据集导入、API Key 管理与运营指标。

![运营与配置](docs/screenshots/operations.png)

### 状态与可靠性

- `session_id` 与 JWT 用户 ID 共同映射为 LangGraph `thread_id`，避免跨用户会话碰撞。
- PostgreSQL checkpointer 持久化每个节点的状态；服务重启后仍能恢复待审核工作流。
- FAQ RAG、相似工单召回与业务工具是三路并行节点，每个节点创建独立 SQLAlchemy Session。
- `reflection` 是真实条件路由：证据不足时改写查询并重新检索（重试上限由 `SUPPORTOPS_MAX_RETRIES` 配置，默认 1），业务工具在重试轮不重复执行。
- 投诉、退款、支付、隐私、账号安全、法律风险和用户明确要求人工等高风险场景通过 `interrupt` 暂停，必须人工批准、修改或拒绝后才能完成。
- 如果 PostgreSQL checkpoint 初始化失败，开发环境会降级到内存 saver；可通过 `GET /supportops/workflow/status` 检查 `durable` 是否为 `true`。

## 数据准备

历史工单 CSV 兼容 Hugging Face Bitext customer support dataset 字段：

- `instruction`: 用户问题
- `category`: 问题大类
- `intent`: 用户意图
- `response`: 标准客服回复

可直接上传项目根目录的 `sample_tickets.csv`。FAQ / 产品说明支持 PDF、DOCX、TXT、MD（仅读取文字层，扫描版 PDF 需先自行 OCR）。

### 多源数据集接入

当前版本增加了带来源治理的数据集导入流水线，而不是把外部文件直接当作可信生产工单：

- `TweetSumm`：来自真实 Twitter 客服对话的人工摘要，标记为 `real_derived`；仓库已保存官方 879/110/110 train/validation/test 数据和许可证。
- `MSDialog`：真实匿名技术支持对话，标记为 `real_anonymized`；已实现 JSON 适配器，但官方要求研究者申请访问，项目不会绕过授权分发数据。
- `Bitext`：混合合成客服数据，强制标记为 `synthetic`。
- 标准 CSV：用户自有数据，标记为 `user_provided`。

导入时会执行 HTML 清理、常见邮箱/电话/银行卡/IP 脱敏、内容哈希与幂等去重、会话级数据切分、质量打分、批次审计，并分批写入 Elasticsearch。`dataset_import_jobs` 保存文件校验和、数据版本、来源真实性、接收/拒绝/去重/脱敏/索引数量和导入参数。

为避免未经确认的外部 API 成本，外部大数据集默认只建立 Elasticsearch 关键词索引；CLI 显式增加 `--with-embeddings` 才生成向量：

```bash
docker exec supportops_api python scripts/import_support_dataset.py \
  --dataset tweetsumm \
  --file /datasets/external/tweetsumm/final_train_tweetsum.jsonl \
  --user-id 3
```

数据来源、许可和真实性边界见 `data/external/tweetsumm/README.md`。

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
ELASTIC_PASSWORD=supportops_es_password
JWT_SECRET_KEY=supportops_local_secret
```

首次启动时应用会自动创建全部数据库表（`SQLAlchemy create_all`），无需手动执行迁移。

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
- `GET /supportops/datasets`: 查询支持的数据集及真实性类型
- `POST /supportops/datasets/import?dataset=tweetsumm`: 导入标准 CSV、Bitext、TweetSumm 或经授权的 MSDialog
- `GET /supportops/dataset_imports`: 查询数据导入批次与质量统计
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

- 基于 FastAPI、React、PostgreSQL、Elasticsearch 和 JWT 搭建本地可部署的客服工单 Agent 系统，支持工单 CSV 清洗入库、FAQ 文档 RAG 检索、相似历史工单召回和 SSE 实时执行轨迹展示；检索层为自研轻量模块（jieba 分词 + BM25/kNN 加权融合，Embedding 缺失时自动降级）。
- 基于 LangGraph 1.x 将意图识别、并行混合检索、风险升级、回复生成与质量反思建模为可恢复状态图，并将节点输入、输出、耗时和状态持久化到 `agent_traces`。
- 通过 PostgreSQL Checkpoint 实现会话级多轮状态、失败恢复与 Human-in-the-loop；高风险工单可暂停并由人工批准、修改或拒绝后恢复执行。
- 建立客服 Agent 离线评测工具，覆盖意图分类 Macro-F1、风险升级 Precision/Recall/F1/漏判率以及检索 Recall@K/MRR。

## 测试与离线评测

后端状态图和指标测试：

```bash
cd backend/app
python -m unittest discover -s tests -v
```

## 评测结果

评测可完整复现（容器内运行，`--user-id` 复用与生产一致的 API Key 解析链路）：

```bash
# 意图分类 + 风险升级：规则基线 vs LLM（qwen-plus），60 例人工构造评测集
docker exec supportops_api python scripts/evaluate_supportops.py --mode both --user-id 1 --output evals/reports/intent_risk.json

# 检索：关键词 BM25 vs 混合检索（+text-embedding-v3 kNN），TweetSumm 真实客服数据 100 例
docker exec supportops_api python scripts/evaluate_retrieval.py --with-embeddings --user-id 1 --limit 100 --output evals/reports/retrieval.json
```

### 意图分类与风险升级（60 例，2026-07 实测）

评测集按三层构造：`keyword`（规则关键词命中且标签一致，26 例）、`paraphrase`（无关键词、需语义理解，30 例）、`trap`（关键词误导，如"退款政策是什么"，4 例）。

| 模式 | category 准确率 / Macro-F1 | intent 准确率 | 升级 Precision / Recall / F1 | 漏判率 FNR |
|---|---|---|---|---|
| 规则基线 | 0.533 / 0.545 | 0.300 | 0.682 / 0.536 / 0.600 | 0.464 |
| LLM（qwen-plus） | **0.950 / 0.951** | **0.867** | 0.636 / **1.000** / **0.778** | **0.000** |

分层升级召回：规则在 keyword 层 0.857、在 paraphrase 层跌到 0.214；LLM 两层均为 1.0。这组数字量化了纯关键词规则的语义盲区，也说明系统在无 API Key 时的降级路径能保住多少能力。

已知局限：4 个 trap 难例（含风险关键词但实际是政策咨询）规则与 LLM 均误升级，体现当前提示词在资金相关词汇上刻意保守——高风险场景按"宁可误升、不可漏判"取舍，代价是精确率（0.682→0.636）。评测集为人工构造的小样本，用于对比方法差异，不代表生产分布。

### 检索 Recall@K / MRR（TweetSumm 100 例，2026-07 实测）

任务设计为 known-item 问答检索：索引仅存客服侧回答文本，用客户侧问题查询，正确答案是同一会话的回答——衡量生产中"新问题找历史标准回复"的问答不对称匹配，不存在字面重合捷径。

| 模式 | Recall@1 | Recall@5 | MRR |
|---|---|---|---|
| 关键词（BM25） | 0.190 | 0.260 | 0.218 |
| 混合（BM25 + kNN，w=0.6） | **0.240** | **0.350** | **0.277** |

混合检索相对纯关键词：Recall@5 +35%，MRR +27%。评测索引按次创建、跑完即删，不污染业务索引。

## 后续可扩展方向

- 增加人工客服处理状态流转和 SLA 规则。
- 为 `tickets` 增加反馈闭环字段，如满意度、是否解决、人工处理结果。
- 引入更细粒度的租户/角色权限。
- 把 mock 业务工具替换为真实订单/物流系统 API，并为 trap 类误升级补充针对性提示词或小样本分类器。
- 使用人工处理结果和满意度构建生产反馈闭环，统计自动解决率与人工覆盖后的净收益。
