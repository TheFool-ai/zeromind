# 多 Agent 内容分析与会话追溯设计

日期：2026-08-03

## 1. 目标

ZeroMind 使用已经注册并启用的 GLM Provider，建立一条对标 BestBlogs 内容分析职责的六 Agent 工作流，并将六个 Agent 持久化到现有 Agent Registry。

系统同时增加可追溯的 Agent 配置版本和执行会话记录。管理员应能从一次内容分析追溯到每个 Agent 当时使用的配置、动态输入摘要、结构化输出、Provider、模型、用量、耗时和错误，同时继续遵守“文章正文只在工作流运行期间存在”的原则。

## 2. 范围

本次包含：

- 六个职责单一的分析 Agent；
- 对应的多阶段工作流；
- 不可变 Agent 版本；
- 单表 Agent session 追溯；
- Agent 注册和工作流示例配置；
- API、管理界面和自动化测试的必要调整。

本次不包含：

- 长文章的持久化分段；
- Agent 工具调用；
- 多轮人工聊天；
- Agent session 事件表；
- 保存原始文章正文、网页快照或包含全文的提示词；
- 完整复制 BestBlogs 的 Dify 实现或提示词。

## 3. 核心决策

### 3.1 六个 Agent

六个 Agent 均为普通 `AgentDefinition`，绑定 Provider Profile，通过 Pi Agent Gateway 执行，并使用严格 JSON Schema 校验输入输出。

#### 1. RSS 元数据初筛

- capability：`screen-content`
- 输入：`metadata`、`audience`
- 输出：`score`、`reason`、`summary`
- 只读取 RSS 元数据，不读取或声称读取正文。
- 评分范围为 0–100；默认低于 30 时正常结束工作流。
- 重点识别目标读者相关性、信息实质性、标题党、纯营销、重复新闻和元数据不足。

#### 2. 文章核心分析

- capability：`extract-content-insights`
- 输入：`metadata`、临时 `document`、`audience`、`maximum_quotes`
- 输出：`one_sentence_summary`、`summary`、`viewpoints`、`key_quotes`
- 提取背景、问题、方法、证据、结论和实际影响。
- 输出 3–5 个主要观点；文章确实不足时允许少于 3 个，但不得用重复内容补足。
- 金句必须逐字来自正文，最多 5 条，每条不超过 300 个字符，并附带不超过 200 个字符的上下文。
- 不负责分类、标签和评分。

#### 3. 领域与标签

- capability：`classify-content`
- 输入：`metadata`、临时 `document`、`audience`、核心分析结果
- 输出：`primary_category`、`category_probabilities`、`secondary_categories`、`tags`
- 标准主领域为：`人工智能`、`软件编程`、`产品设计`、`商业科技`、`其他`。
- 各领域概率使用 0–100 整数且总和必须为 100；主领域必须是概率最高的领域。
- 标签为 3–10 个，按主题、技术或领域、应用或产品、组织或人物、趋势排序。
- 标签应标准化、去重并避免仅重复标题词汇。

#### 4. 文章质量评分

- capability：`score-content-quality`
- 输入：`metadata`、临时 `document`、`audience`、核心分析结果、分类结果
- 输出：`scores`、`recommendation_level`、`recommendation_reason`
- 六个 0–100 评分维度为：`relevance`、`information_value`、`depth`、`practicality`、`novelty`、`clarity`。
- 每个维度必须有基于原文的非空理由。
- Agent 不输出或决定最终加权总分；工作流的确定性 `score` 节点负责计算。
- 推荐等级只表达模型判断，不控制门禁。

#### 5. 分析审核反思

- capability：`review-content-analysis`
- 输入：`metadata`、临时 `document`、`audience`、核心分析、分类和评分结果
- 输出：`approved`、`issues`、`overall_assessment`
- 逐项检查事实忠实度、摘要完整性、观点覆盖、金句原文一致性、分类标签合理性、评分依据和跨字段一致性。
- 每个 issue 包含 `area`、`severity`、`description`、`suggested_change`。
- 审核只提出问题和修改建议，不覆盖上游输出。

#### 6. 最终分析优化

- capability：`finalize-content-analysis`
- 输入：`metadata`、临时 `document`、`audience`、核心分析、分类、评分和审核结果
- 输出满足 `content_analysis_v1` 投影所需的完整 content 结构，并在 Agent 输出层额外包含 `update_reasons`。
- 只有审核问题或明确的跨字段不一致支持修改时才调整上游字段。
- 最终输出包含主分类、次级分类、标签、一句话总结、摘要、主要观点、金句、六维评分、推荐等级和推荐理由。
- `update_reasons` 按字段记录修改原因；没有修改时返回空对象。工作流投影只映射既有 content 字段，`update_reasons` 保留在最终 Agent 的步骤和 session 输出中，不进入禁止额外字段的 `content_analysis_v1`。

### 3.2 动态受众

六个 Agent 中与内容判断有关的输入均接受 `audience`。Agent 的 system prompt 描述如何使用受众，但不永久写死具体受众。

首个工作流将受众预设为：

> AI 与软件开发者，关注工程实践、技术原理、开发工具、可复用方法、产品落地和重要行业变化。

以后可在工作流定义或触发输入中替换该值，无需创建新的 Agent 版本。

### 3.3 工作流

默认执行顺序：

```text
reference
  -> screening
  -> initial_gate (score >= 30)
  -> resolve
  -> core_analysis
  -> taxonomy
  -> quality_scoring
  -> review
  -> finalize
  -> deterministic_score
  -> fine_gate (total >= 70)
  -> content_analysis_v1 projection
```

工作流保持串行执行，以便下游 Agent 显式使用上游结构化结果。任何 Provider、JSON 解析或 Schema 错误均使工作流失败；初筛或细筛门禁拒绝仍是正常业务结果。

JSON Schema 负责字段形状和数值边界；领域概率总和、主领域与最高概率一致等跨字段规则由 Agent Gateway 的具名语义校验器执行。语义校验失败与输出 Schema 失败采用相同的失败和重试策略。

加权总分沿用现有六维权重：

- relevance：20%
- information_value：25%
- depth：20%
- practicality：15%
- novelty：10%
- clarity：10%

最终投影使用 `finalize` 输出，不覆盖或删除各个步骤的原始结果。

## 4. Agent 配置与版本

### 4.1 稳定 Agent 身份

`agents` 表保存稳定身份和当前状态：

- `id`
- `name`
- `description`
- `enabled`
- `current_version`
- `created_at`
- `updated_at`

Agent 名称继续全局唯一。发现能力从当前版本读取。

### 4.2 不可变 Agent 版本

新增 `agent_versions` 表：

- `id`
- `agent_id`
- `version`
- `capabilities`
- `system_prompt`
- `provider_profile_id`
- `input_schema`
- `output_schema`
- `created_at`

约束：

- `(agent_id, version)` 唯一；
- 已创建版本不可更新或删除；
- 注册 Agent 时同时创建版本 1；
- 修改 system prompt、capabilities、Provider 绑定或任一 Schema 时创建下一版本，并原子更新 `agents.current_version`；
- 启用和停用只修改稳定 Agent 身份，不创建版本；
- 执行开始时解析一次当前版本，重试继续使用同一个版本。

现有 `agents` 数据迁移为对应的版本 1，保留现有 ID、时间和启用状态。迁移完成后，执行配置只从 `agent_versions` 读取。

## 5. Agent session 追溯

### 5.1 单表模型

新增 `agent_sessions` 表，不新增 `agent_session_events`：

- `id`
- `workflow_run_id`
- `step_run_id`
- `agent_id`
- `agent_version_id`
- `attempt`
- `provider`
- `model`
- `thinking_level`
- `sanitized_input`
- `document_sha256`
- `document_character_count`
- `output`
- `response_sha256`
- `response_character_count`
- `usage`
- `status`
- `error_code`
- `error_message`
- `started_at`
- `completed_at`

约束和索引：

- `(step_run_id, attempt)` 唯一；
- `workflow_run_id`、`agent_id`、`agent_version_id`、`status` 和 `started_at` 建索引；
- workflow run 删除时级联删除 session；
- Agent 和 Agent version 使用 `RESTRICT`，防止删除破坏追溯；
- session 成功或失败后不可修改，只有 `running` 到终态的单次状态转换例外。

### 5.2 状态

状态限定为：

- `running`
- `completed`
- `provider_failed`
- `timed_out`
- `protocol_failed`
- `json_invalid`
- `schema_invalid`
- `cancelled`

session 在 Provider 调用前创建为 `running`。Provider 返回并通过 JSON 解析及输出 Schema 后保存完整结构化输出并标记 `completed`。所有失败路径都必须落终态，避免永久的 `running` 记录；进程崩溃留下的 `running` session 由恢复任务标记为 `protocol_failed`。

### 5.3 可追溯内容

system prompt 不复制到 session。历史执行通过 `agent_version_id` 关联不可变 `agent_versions.system_prompt`。

`sanitized_input` 保留元数据、动态受众和上游结构化结果，但所有嵌套的 transient document 正文替换为：

```json
{
  "sha256": "...",
  "character_count": 12345,
  "content_type": "text/markdown"
}
```

成功结果保存完整的、通过 Schema 的结构化输出。JSON 解析或 Schema 校验失败时，不保存原始响应文本，只保存 SHA-256、字符数、错误代码和有界错误摘要，避免异常响应复述大段原文。

session 不参与后续模型上下文构建。工作流仍显式传递已验证的结构化步骤输出，因此历史追溯与运行时上下文互不耦合。

## 6. Pi 与 Gateway 调整

Pi 仍使用内存 SessionManager、禁用工具，并在调用结束后销毁会话。持久化由 Python 侧 Agent Gateway 管理，不启用 Pi 自身的 session persistence。

Pi 协议需要区分以下结果：

- Provider 或运行时失败；
- 超时或取消；
- 模型返回但 JSON 无效；
- JSON 有效但不符合输出 Schema；
- 成功完成及用量。

Runner 对响应计算 SHA-256 和字符数。只有成功解析为 JSON 的响应可返回结构化 output；失败响应不通过 RPC 返回正文。Gateway 在调用前创建 session，在每个终态路径写回执行元数据。

工作流的 Agent handler 将 `workflow_run_id`、`step_run_id` 和 `attempt` 作为执行上下文传给 Gateway。session 创建失败属于基础设施错误，不能在没有追溯记录的情况下继续调用 Provider。

为满足 `agent_sessions.step_run_id` 外键，Workflow Repository 改为增量持久化步骤：创建 `StepRun` 后、调用 handler 前先插入 running 步骤；每次尝试更新 attempts；完成或失败后更新终态。保存 workflow run 时不再采用“删除全部步骤再重建”的方式。这样运行期间已经存在稳定的 step ID，session 可以安全关联，并避免工作流崩溃时丢失已经完成的步骤和会话。

## 7. API 与管理界面

### 7.1 Agent API

现有创建和更新入口保持兼容，并扩展：

- Agent 响应返回 `current_version`；
- Agent 详情可以列出历史版本；
- 更新入口允许修改 system prompt、capabilities、Provider 和两个 Schema，每次生成不可变新版本；
- 六个 Agent 可以通过现有注册 API 创建，也提供可复制的 JSON 示例。

### 7.2 Session API

新增只读管理员接口：

- 按 workflow run 查询 sessions；
- 查询单个 session；
- 按 Agent、状态和时间范围筛选 sessions。

响应不包含正文或 Provider 密钥。错误信息在返回前执行凭据和敏感头清洗。

### 7.3 管理界面

Agent 页面展示当前版本和历史版本入口。工作流运行详情按步骤展示 Agent session，包括 Agent、版本、Provider、模型、状态、用量、耗时、清洗输入和结构化输出。

管理界面不提供修改历史版本或 session 的操作。

## 8. 注册与激活

提供六份 Agent JSON 示例，默认 `provider_profile_id` 使用明确标注的无效占位 UUID。实际注册脚本从 API 查询名称为 `GLM` 的启用 Provider，逐个注册六个 Agent，并打印返回的 Agent ID；脚本不读取或输出 Provider 密钥。

脚本必须可重复执行：

- 同名 Agent 已存在且配置一致时复用；
- 同名 Agent 已存在但配置不同，不静默覆盖，明确失败并要求管理员选择创建新版本；
- 六个 Agent 全部注册成功后才生成包含真实 Agent ID 的工作流 YAML；
- 工作流必须先校验再保存和激活；
- 任一步失败时不自动删除已创建 Agent，因为 Agent 删除会破坏审计引用。

## 9. 错误处理与恢复

- Provider 不可用：session 标记 `provider_failed`，工作流按受限策略重试，每次尝试单独记录。
- 超时：session 标记 `timed_out`，Pi 子进程终止。
- JSON 无效：session 标记 `json_invalid`，仅保存响应 hash 和长度。
- 输出 Schema 无效：session 标记 `schema_invalid`，保存已解析输出需要先经过 transient 正文清洗；如果不能证明安全，则只保存 hash 和验证错误。
- 审核发现问题：这是正常业务结果，继续执行最终优化。
- 最终优化仍不一致：Schema 通过但审核未批准不自动失败；审核问题继续保留在审核 Agent 的步骤和 session 输出中。本次不增加额外 LLM 重试循环。
- 数据库无法创建或完成 session：工作流失败，不能产生无追溯的 Provider 调用。

## 10. 测试策略

### Agent 与版本

- 创建 Agent 同时创建版本 1；
- 修改配置创建新版本且旧版本不可变；
- 启停不创建版本；
- Agent 名称和版本唯一约束；
- 执行期间更新 Agent 不改变已经解析的版本。

### Session

- 成功、Provider 失败、超时、协议失败、JSON 无效和 Schema 无效分别落正确终态；
- 重试产生不同 session，attempt 递增；
- session 能关联 workflow run、step run 和 Agent version；
- 正文和 transient marker 不出现在任何 session JSON 或错误字段中；
- Provider 密钥不出现在 session、日志和 API 响应中；
- 历史 session 通过版本关联还原当时 system prompt。

### 六 Agent 工作流

- 初筛拒绝只调用第一个 Agent；
- 初筛通过时按顺序调用六个 Agent；
- 每个 Agent 输入输出通过严格 Schema；
- 审核结果传给最终优化；
- 最终投影使用优化结果和确定性总分；
- 六次调用均有独立 session；
- 正文在工作流步骤、session、最终分析和 outbox 中均不持久化。

测试使用 Fake Pi 响应和本地临时数据库，不依赖真实 GLM Provider。

## 11. 验收标准

- 数据库中存在六个启用的分析 Agent，均绑定已配置的 GLM Provider；
- Agent 配置修改产生不可变版本，历史 session 始终能解析原始版本；
- 一次完整合格分析产生六条 completed session；
- 初筛拒绝只产生一条 completed session；
- 每条 session 可追溯到 workflow run、step run、Agent version、Provider 和模型；
- 管理员可以查看清洗输入、完整有效输出、用量、耗时和错误；
- 数据库、日志和 API 中不存在文章正文与 Provider 密钥；
- 现有两 Agent 示例和已激活工作流在迁移后仍可读取和执行。

## 12. 参考

- BestBlogs 文章初评流程：<https://github.com/ginobefun/BestBlogs/blob/main/flows/Dify/ArticleFIlterFlow.md>
- BestBlogs 文章分析流程：<https://github.com/ginobefun/BestBlogs/blob/main/flows/Dify/ArticleAnalysisFlow.md>
- OpenClaw Agent Runtime：<https://docs.openclaw.ai/agent>
- OpenClaw Session Management：<https://github.com/openclaw/openclaw/blob/main/docs/reference/session-management-compaction.md>
