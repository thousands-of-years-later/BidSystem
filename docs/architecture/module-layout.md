# 招标产品组合系统：模块与目录拆分设计

> 状态：建议基线  
> 日期：2026-07-21  
> 前提：后端以 Python 为主，前端独立；首期采用模块化单体，API 与异步 Worker 可独立部署。

## 1. 结论

本项目不应直接照搬通用 Agent 框架的目录，而应同时保留两种边界：

1. **业务领域边界**：文档、产品、招标、匹配、方案、审核各自拥有模型、用例和数据。
2. **Agent 能力边界**：运行循环、工具、上下文、会话、技能和可观测性作为通用运行时，不拥有业务事实。

推荐采用：

- **模块化单体**承载核心业务，先避免微服务带来的分布式事务和运维成本。
- **独立 Agent Runtime**借鉴 HelloAgents 的分层，但业务 Agent 只负责编排 LLM 能力。
- **确定性内核**负责单位换算、参数比较、硬需求判定和 OR-Tools 求解。
- **端口/适配器**隔离 PostgreSQL、MinIO、Redis、模型供应商、OCR 与向量检索。
- **线上运行时技能**与 **Claude Code 研发配置**使用不同目录，避免含义混淆。

## 2. 顶层目录

```text
bid-system/
├── AGENTS.md                         # 跨编码 Agent 的项目事实与硬约束，精简
├── CLAUDE.md                         # 导入 AGENTS.md，补充 Claude Code 说明
├── PROJECT_MEMORY.md                 # 当前产品与业务设计基线
├── pyproject.toml                    # 后端工作区、统一 lint/test 配置
├── package.json                      # 仅在前端/工作区需要时添加
│
├── backend/
│   ├── src/bid_system/
│   │   ├── bootstrap/                # 配置、依赖装配、应用生命周期
│   │   ├── entrypoints/              # HTTP、Worker、CLI 等进程入口
│   │   ├── shared/                   # 极小的共享内核与跨模块契约
│   │   ├── platform/                 # 通用外部基础设施适配
│   │   ├── agent_runtime/            # 与业务无关的 Agent 框架能力
│   │   ├── orchestration/            # 业务 Agent、工作流和领域工具适配
│   │   └── modules/                  # 按业务能力拆分的核心模块
│   └── tests/
│       ├── unit/
│       ├── integration/
│       ├── contract/
│       └── e2e/
│
├── frontend/                         # 管理台/审核台，建议单独 TypeScript 工程
│   ├── src/app/
│   ├── src/features/
│   ├── src/entities/
│   └── src/shared/
│
├── runtime_skills/                   # 线上业务 Agent 按需加载的领域知识
├── prompts/                          # 有版本号、可评测的提示词模板
├── evals/                            # 抽取、判定、工具调用、方案说明评测集
├── migrations/                       # 数据库迁移；按模块命名或分 schema
├── deploy/                           # Docker/Compose/K8s/监控配置
├── scripts/                          # 本地开发、导入和运维脚本
├── docs/
│   ├── architecture/
│   ├── adr/                          # Architecture Decision Records
│   ├── domain/
│   └── operations/
└── .claude/                          # Claude Code 研发辅助，不参与线上运行
    ├── agents/
    ├── skills/
    ├── rules/
    └── settings.json
```

## 3. 后端业务模块

```text
backend/src/bid_system/modules/
├── documents/          # 文件版本、DocumentIR、解析任务、块与定位信息
├── product_catalog/    # ProductFamily/Model/Line/Alias 与主数据
├── product_knowledge/  # Evidence、FactCandidate、ProductFact、Relation、冲突
├── tenders/            # Project/Lot/Item、Requirement、ScoringRule、Constraint
├── matching/           # PASS/FAIL/UNKNOWN/CONFLICT、产品线初筛、证据覆盖
├── planning/           # ItemCandidate、BidPlan、CP-SAT 约束与多目标优化
├── reviews/            # 人工审核任务、决策、发布门禁、审计轨迹
└── reporting/          # 方案说明、证据包、差异报告、导出；只读投影为主
```

### 3.1 为什么这样拆

| 模块                  | 拥有的核心事实                     | 不负责          |
| ------------------- | --------------------------- | ------------ |
| `documents`         | 原文件版本、解析状态、DocumentIR、文档块坐标 | 产品事实、招标需求发布  |
| `product_catalog`   | 型号身份、别名、产品线归属、生命周期          | 从文档推断技术参数    |
| `product_knowledge` | 证据、候选事实、正式事实、产品关系、冲突        | 招标侧要求与组合求解   |
| `tenders`           | 招标层级、原子需求、评分规则、全局约束         | 判断某型号是否满足    |
| `matching`          | 需求对事实的判定结果、拒绝原因、产品线候选池      | 修改正式事实或需求    |
| `planning`          | 组合候选、求解模型、目标值、最终方案快照        | 用 LLM 猜测可行性  |
| `reviews`           | 审核任务、人工决定、发布门禁、审计日志         | 持有被审核对象的业务模型 |
| `reporting`         | 查询投影与可追溯输出                  | 成为新的权威数据源    |

`product_catalog` 与 `product_knowledge` 分开，是因为“型号是谁”属于主数据，而“可以证明型号具备什么能力”属于带版本和审核生命周期的知识数据。两者变化频率、权限和质量门禁不同。

## 4. 每个领域模块的内部结构

所有业务模块使用相同模板，但只创建实际需要的文件：

```text
modules/product_knowledge/
├── domain/
│   ├── entities.py             # 聚合、实体、值对象
│   ├── policies.py             # 纯业务规则
│   ├── events.py               # 领域事件
│   ├── errors.py
│   └── repositories.py         # 仓储端口，不含 ORM 实现
├── application/
│   ├── commands.py             # 改变状态的输入
│   ├── queries.py              # 查询输入
│   ├── handlers.py             # 用例编排与事务边界
│   ├── dto.py                  # 跨边界数据结构
│   └── ports.py                # OCR/LLM/搜索等外部能力端口
├── infrastructure/
│   ├── persistence.py          # SQLAlchemy/数据库仓储适配
│   ├── search.py               # pgvector/全文检索适配
│   └── consumers.py            # 消息/任务消费者
├── interfaces/
│   ├── http.py                 # 路由及请求/响应映射
│   └── events.py               # 对外事件映射
└── public.py                   # 其他模块唯一允许依赖的公开门面
```

约束：

- `domain` 不依赖 Web、ORM、Redis、LLM SDK 或 Agent Runtime。
- `application` 只依赖本模块 `domain`、端口以及极小的 `shared`。
- `infrastructure` 实现端口，不允许把 ORM 模型泄漏到应用层。
- 跨模块调用只经过对方 `public.py`、稳定契约或领域事件。
- 禁止直接导入其他模块的 `infrastructure`、数据库表或内部实体。
- 一个请求的强一致修改尽量限制在单模块聚合内；跨模块流程使用工作流、事件和幂等处理。

## 5. Agent Runtime 与业务编排

借鉴 HelloAgents 的 `core / agents / tools / context / skills / observability` 分层，但拆成“框架运行时”和“业务编排”两部分：

```text
backend/src/bid_system/
├── agent_runtime/                    # 可复用、无招标领域概念
│   ├── core/
│   │   ├── agent.py                  # Agent/RunContext 基类和执行循环
│   │   ├── llm.py                    # ModelPort、消息与结构化输出协议
│   │   ├── lifecycle.py              # cancel/timeout/retry/async lifecycle
│   │   └── streaming.py              # 统一事件流/SSE 事件
│   ├── tools/
│   │   ├── base.py                   # Tool 接口
│   │   ├── response.py               # ToolResponse/Error 协议
│   │   ├── registry.py               # 注册与按 Agent 过滤
│   │   ├── executor.py               # 超时、并发、重试
│   │   └── circuit_breaker.py
│   ├── context/
│   │   ├── builder.py
│   │   ├── history.py
│   │   ├── token_counter.py
│   │   └── truncator.py
│   ├── sessions/
│   │   ├── store.py
│   │   └── checkpoints.py
│   ├── skills/
│   │   ├── loader.py
│   │   └── manifest.py
│   └── observability/
│       ├── traces.py
│       ├── events.py
│       └── metrics.py
│
└── orchestration/                    # 招标领域专用，依赖应用层公开门面
    ├── agents/
    │   ├── product_document_agent.py
    │   ├── tender_document_agent.py
    │   ├── evidence_review_agent.py
    │   └── plan_explainer_agent.py
    ├── tools/
    │   ├── document_tools.py
    │   ├── product_tools.py
    │   ├── tender_tools.py
    │   ├── matching_tools.py
    │   └── planning_tools.py
    ├── workflows/
    │   ├── ingest_product_document.py
    │   ├── ingest_tender_document.py
    │   └── generate_bid_plan.py
    └── policies/
        ├── tool_permissions.py
        ├── human_gate.py
        └── budgets.py
```

### 5.1 Agent、Tool、Skill 的职责

- **Agent**：选择下一步、请求结构化抽取、处理信息不完整、形成解释。
- **Tool**：把一个受控应用用例暴露给 Agent；工具不直接写表，也不绕过审核门禁。
- **Skill**：按需加载的领域说明、抽取策略和检查清单；不是 Python 业务逻辑。
- **Workflow**：持久化的长流程状态机，负责重试、暂停、人工审核和恢复。
- **Domain Service**：确定性规则，任何 Agent 都不能覆盖其结果。

禁止把以下能力实现成自由推理 Agent：

- 数值/区间/单位比较。
- `PASS / FAIL / UNKNOWN / CONFLICT` 的最终硬规则。
- 事实或需求的正式发布门禁。
- 产品兼容、互斥、数量比例约束。
- CP-SAT 可行性判断、成本和评分计算。

这些能力应作为应用服务或纯领域服务，通过只读/受控 Tool 被 Agent 调用。

## 6. 一条主流程如何跨模块

```text
entrypoints/api
  -> documents.application（保存文件版本、创建解析任务）
  -> orchestration.workflow（解析和抽取流程）
  -> agent + document/product tools（生成候选，不发布）
  -> product_knowledge.application（标准化、冲突检测）
  -> reviews.application（必要时人工确认）
  -> product_knowledge.application（发布 ProductFact）
  -> matching.application（确定性匹配）
  -> planning.application（CP-SAT 求解）
  -> reporting.application（基于计算快照生成说明）
```

流程状态不应只存在 Agent 对话历史中。每个重要步骤都要保存：输入版本、输出版本、模型/提示词版本、工具调用、规则版本、审核决定和错误信息。

## 7. 通用基础设施

```text
backend/src/bid_system/platform/
├── config/                    # 环境配置与密钥引用
├── database/                  # session、transaction、outbox 基础设施
├── object_store/              # MinIO
├── queue/                     # Redis/任务队列适配
├── llm/                       # OpenAI-compatible/Anthropic/local adapters
├── ocr/                       # OCR provider adapters
├── search/                    # PostgreSQL FTS/pgvector
├── telemetry/                 # OpenTelemetry/logging/metrics
└── security/                  # auth、tenant、redaction、audit helpers
```

`platform` 只能提供技术能力，不能出现 `ProductFact`、`TenderRequirement`、`BidPlan` 等业务决策。

## 8. shared 允许放什么

```text
shared/
├── kernel/       # EntityId、Clock、Money、UnitValue、Result、PageToken
├── contracts/    # 稳定的跨模块事件和外部 API contract
└── testing/      # 测试 fixture 基础，不进入生产依赖
```

不要创建 `shared/utils.py`、`common/service.py` 或 `helpers/` 垃圾桶。代码只有满足以下条件才进入共享层：

1. 至少被两个业务模块使用；
2. 不包含任何一个模块独有的业务语义；
3. 有明确维护者和兼容性要求。

## 9. 数据所有权与集成

首期可共用一个 PostgreSQL 实例，但建议按模块划分 schema 或至少表名前缀。表只能由所属模块的仓储写入。

- 同步查询：调用目标模块 `public.py`，返回 DTO，不返回 ORM 对象。
- 异步传播：使用 `outbox_event`，消费者必须幂等。
- 长任务：队列消息只携带 ID 和版本，不携带大型 DocumentIR。
- 原文件和大型解析产物：MinIO；数据库保存哈希、URI、版本和元数据。
- Redis：仅队列、锁、缓存和临时状态，不作为权威状态。
- 向量结果：只做召回，不能直接作为合规判断证据。

## 10. 线上 Skill 与 Prompt

```text
runtime_skills/
├── common/document-evidence/SKILL.md
├── product/model-scope/SKILL.md
├── product/fact-extraction/SKILL.md
├── tender/requirement-scope/SKILL.md
├── tender/scoring-rule/SKILL.md
└── review/conflict-check/SKILL.md

prompts/
├── product_fact_extract/v1/system.md
├── tender_requirement_extract/v1/system.md
└── plan_explanation/v1/system.md
```

Skill 存放较稳定、按需加载的领域知识；Prompt 存放某个模型调用的明确指令和输出 schema。二者都必须版本化，并在运行记录中保存版本号。

## 11. Claude Code 研发目录

Claude Code 的配置用于帮助开发者维护仓库，不能被线上 Agent Runtime 扫描：

```text
.claude/
├── agents/
│   ├── domain/
│   │   ├── product-knowledge-reviewer.md
│   │   └── tender-rules-reviewer.md
│   ├── engineering/
│   │   ├── architecture-reviewer.md
│   │   └── test-reviewer.md
│   └── research/
│       └── document-parser-researcher.md
├── skills/
│   ├── add-domain-module/SKILL.md
│   ├── add-agent-tool/SKILL.md
│   ├── database-migration/SKILL.md
│   └── run-architecture-check/SKILL.md
├── rules/
│   ├── architecture.md
│   ├── testing.md
│   ├── security.md
│   └── python.md
└── settings.json
```

建议：

- `AGENTS.md` 作为跨工具的唯一项目规则源。
- 根 `CLAUDE.md` 使用 `@AGENTS.md` 导入，再写少量 Claude Code 专属说明。
- 根规则保持短小；模块专属规则使用 path-scoped `.claude/rules/*.md`。
- 多步骤、低频工作流写成 `.claude/skills/<name>/SKILL.md`，按需加载。
- 子 Agent 只做边界清晰、权限受限的研究或审查；名称全仓唯一。
- 不把全部业务文档塞入启动上下文，按路径、Skill 或工具按需读取。

## 12. 依赖方向

```text
entrypoints ──> orchestration ──> module.application ──> module.domain
      │               │                    ▲
      │               └──> agent_runtime   │
      └──> bootstrap                       │

module.infrastructure ──implements─────────┘
platform adapters ──────implements ports───┘
```

允许：

- `orchestration.tools` 调用模块 `public.py` 或 application port。
- `infrastructure` 依赖自己的 domain/application 来实现端口。
- `reporting` 读取稳定查询投影。

禁止：

- `domain -> agent_runtime/platform/entrypoints`。
- `module A -> module B.infrastructure`。
- Agent Tool 直接持有数据库 session 并更新业务表。
- API 路由内编写抽取、匹配或求解规则。
- 为复用 ORM 模型而共享领域实体。

## 13. 首期最小落地目录

不要一次创建所有空文件。第一阶段只落地：

```text
backend/src/bid_system/
├── bootstrap/
├── entrypoints/api/
├── entrypoints/worker/
├── shared/kernel/
├── platform/{database,object_store,llm,queue}/
├── agent_runtime/{core,tools,context,observability}/
├── orchestration/{agents,tools,workflows}/
└── modules/
    ├── documents/
    ├── product_catalog/
    ├── product_knowledge/
    └── reviews/
```

第二阶段增加 `tenders` 与 `matching`，第三阶段增加 `planning` 与 `reporting`。这样每个新增目录都对应已运行的用例，而不是预先制造空抽象。

## 14. 建议的实施顺序

1. 建立 `AGENTS.md`、`CLAUDE.md` 和架构依赖规则。
2. 创建 Python 工程、bootstrap、API/Worker 入口和统一测试配置。
3. 实现 `documents`、`product_catalog`、`product_knowledge` 的最小纵向链路。
4. 抽出 Agent Runtime 的最小能力：结构化输出、ToolResponse、ToolRegistry、上下文和 Trace。
5. 用 `product_document_agent` 连接应用服务，但只产出 `FactCandidate`。
6. 增加 `reviews` 发布门禁和完整审计。
7. 再实现招标抽取、确定性匹配、CP-SAT 方案生成和报告。
8. 当模块确有独立扩缩容、发布或团队所有权需求时，再拆服务；保持 application port 和事件契约不变。

## 15. 参考与取舍说明

- [HelloAgents GitHub](https://github.com/jjyaoao/HelloAgents)：采用其核心/Agent/工具/上下文/技能/可观测性分层思想，不复制其教育型“万物皆工具”到业务领域模型。
- [Hello-Agents 框架设计章节](https://github.com/datawhalechina/hello-agents/blob/main/docs/chapter7/Chapter7-Building-Your-Agent-Framework.md)：采用统一工具协议、注册机制和分层解耦。
- [Claude Code 子 Agent 文档](https://code.claude.com/docs/en/sub-agents)：项目 Agent 放在 `.claude/agents/`，使用独立上下文与最小工具权限。
- [Claude Code Skills 文档](https://code.claude.com/docs/en/skills)：项目 Skill 放在 `.claude/skills/<name>/SKILL.md` 并按需加载。
- [Claude Code memory/rules 文档](https://code.claude.com/docs/en/memory)：根说明保持简洁，使用 `.claude/rules/` 做模块化和路径范围约束。
