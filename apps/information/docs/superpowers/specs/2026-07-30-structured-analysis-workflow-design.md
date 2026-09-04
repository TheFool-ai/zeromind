# 结构化信息分析工作流设计

## 1. 目标

ZeroMind 要把 RSS 新发现的内容引用转化为可查询的信息流，帮助用户判断哪些内容真正值得投入时间。安全的 YAML DSL 负责依次编排：

1. 低成本的元数据初筛；
2. 临时读取原文；
3. 基于全文进行分类和深度分析；
4. 采用确定性算法计算可解释的分数；
5. 执行第二阶段细筛；
6. 将结果投影为统一的结构化分析。

结构化结果包含分类、标签、摘要、观点、各维度评分、总分、推荐理由和受限长度的金句。用户可以针对内容引用或分析结果添加自己的笔记。

第一版的初筛和细筛都由 Agent 自动完成。管理员可以纠正最终结论，但纠正操作以追加审计记录的方式保存，不覆盖 Agent 的原始结果。

本次范围明确不包含多篇文章的比较阅读报告。用户已经确认“比较阅读”不是所需能力。

## 2. 产品原则

### 2.1 信息要少而有价值，并且说明理由

ZeroMind 的目标不是最大化展示数量。默认信息流只展示通过筛选的内容，并说明每条内容为什么值得阅读。被筛掉的内容仍然可以在审计视图中查询，用于校准提示词和筛选阈值。

### 2.2 公共质量判断与个人判断分离

结构化分析是针对某一内容引用修订版本、可复现的质量判断。用户笔记属于个人阅读资产。笔记不会成为 Agent 输出的一部分，修改笔记也不会改变内容评分。

### 2.3 所有判断尽量可解释

Agent 为每个配置的评分维度提供证据、分数和理由。内置 DSL 节点根据权重确定性地计算总分。阈值、权重、Agent 版本、Provider、模型、评分理由和人工改判记录都可以被查看。

### 2.4 保持“引用优先”的内容策略

ZeroMind 继续保存内容引用，而不是保存文章副本。原文只在工作流运行期间读取，并在工作流状态持久化前删除。

每份分析最多保存五条金句，每条不超过 300 个 Unicode 字符，附带的上下文最多 200 个字符。这种受限的派生结果不能用于还原整篇文章。

## 3. BestBlogs 调研结论

BestBlogs 展示了与 ZeroMind 高度相关的产品模式：

- 在深度处理前进行低成本 AI 初筛；
- 基于全文生成结构化分析；
- 输出质量维度、摘要、观点、标签和金句；
- 将公共质量池与个人阅读资产分离；
- 在自动筛选后允许人工纠正；
- 为推荐结果提供明确理由。

ZeroMind 借鉴的是这些产品机制，不直接复制 BestBlogs 的源码或提示词。BestBlogs 的公共仓库主要开放产品文档、Dify 工作流、OpenAPI 资料和单独声明许可证的 CLI。ZeroMind 将使用现有 Pi Agent Gateway、Python 领域模型和安全工作流 DSL 独立实现。

## 4. 限界上下文

### 4.1 内容摄取 `ingestion`

现有 `ingestion` 上下文继续作为 `ContentReference` 和 `ReferenceRevision` 的唯一事实来源。评分、分析、笔记或文章正文都不会加入引用聚合。

### 4.2 工作流 `workflows`

`workflows` 上下文继续作为通用编排引擎，并新增：

- 在安全映射中使用字面量的能力；
- 只读取 RSS 元数据、不访问原文的 `reference` 节点；
- 确定性计算权重总分的 `score` 节点；
- 可以正常终止流程的 `gate` 节点；
- 工作流定义上的具名结果投影；
- 门禁拒绝时的成功提前终止语义。

工作流上下文本身不负责保存或查询信息卡片。

### 4.3 结构化分析 `analysis`

新增 `analysis` 上下文，负责维护某个内容引用修订版本的统一结构化评估。`ContentAnalysis` 是该上下文的聚合根。

`AnalysisProjector` 负责校验已完成的工作流结果，并以幂等方式创建聚合。`AnalysisDecisionOverride` 负责记录人工改判，同时保留生成时的原始结论。

### 4.4 用户笔记 `notes`

新增 `notes` 上下文，负责维护用户编写的 Markdown 笔记。`Note` 是聚合根，必须关联一个 `ContentReference`，也可以关联某一份具体的 `ContentAnalysis`。

当前应用只有一个配置的管理员账号，还没有完整的用户聚合。笔记使用鉴权令牌中的 subject 作为 `owner_subject`。这样既能保证当前的归属语义，也能在以后接入多用户身份系统时避免重写笔记数据。

### 4.5 Agent 管理 `agents`

现有 Agent Gateway 继续负责 Agent 查找、Provider 选择、Pi 执行、JSON Schema 校验、用量元数据和超时控制。

初筛 Agent 与深度分析 Agent 是两个普通的已注册 Agent，可以使用不同的提示词、模型和输出 Schema。系统不会引入绕过 Gateway 的分析专用模型客户端。

## 5. 运行时数据流

```text
reference.discovered / reference.updated / manual
  |
  v
reference 元数据节点
  |
  v
初筛 Agent -------------------------+
  |                                 |
  v                                 |
初筛 gate -- 拒绝 ----------------->+--> 工作流正常完成
  |
  v
临时原文解析
  |
  v
深度分析 Agent
  |
  v
确定性 score 节点
  |
  v
细筛 gate -- 拒绝 ----------------->+--> 工作流正常完成
  |
  v
以 qualified 状态正常完成
  |
  v
统一 AnalysisProjector
  |
  v
ContentAnalysis 信息卡片
```

门禁拒绝属于正常业务结果，不是工作流失败。Provider 错误、Schema 不匹配、URL 被网络策略阻止、超时、无效映射或投影校验失败，仍然属于工作流失败。

新增 `WorkflowRunService`，统一协调工作流执行和结果投影。手工 API 运行与 Worker 事件触发都必须通过该服务，从而避免把分析持久化逻辑放进通用执行器，并保证两种入口行为一致。

## 6. DSL 演进

### 6.1 安全映射和字面量

与受限 `$.path` 语法完全匹配的字符串继续从运行时上下文取值。

其他 YAML 标量作为字面量处理。以 `$` 开头但不符合合法路径语法的字符串直接被拒绝，避免把路径拼写错误悄悄当成普通文本。字典和列表可以递归混合路径和字面量。

DSL 仍然不支持表达式求值、字符串插值、模板执行、任意代码或动态创建节点。

示例：

```yaml
input:
  document: $.steps.resolve
  audience: software-builders
  include_evidence: true
  maximum_quotes: 5
```

### 6.2 `reference` 节点

该节点读取指定引用及其修订版本，但不会访问原文地址：

```yaml
- id: metadata
  type: reference
  input:
    reference_id: $.trigger.reference_id
    revision: $.trigger.revision
```

输出字段包括：

- 内容引用 ID；
- 修订版本号；
- 订阅源 ID；
- 原文地址；
- 标题；
- RSS 摘要；
- 作者；
- 发布时间和更新时间；
- 系统观察时间。

如果没有传入 `revision`，节点读取当前修订版本。事件触发的运行必须携带修订版本号，使历史事件重放仍然具有确定性。

### 6.3 `score` 节点

`score` 节点接收一组具名评分维度。每个维度包含：

- 0 到 100 的分值；
- 大于零的权重；
- Agent 生成的非空评分理由。

```yaml
- id: quality_score
  type: score
  depends_on: [analyze]
  input:
    dimensions:
      relevance:
        value: $.steps.analyze.scores.relevance.value
        reason: $.steps.analyze.scores.relevance.reason
        weight: 0.20
      information_value:
        value: $.steps.analyze.scores.information_value.value
        reason: $.steps.analyze.scores.information_value.reason
        weight: 0.25
      depth:
        value: $.steps.analyze.scores.depth.value
        reason: $.steps.analyze.scores.depth.reason
        weight: 0.20
      practicality:
        value: $.steps.analyze.scores.practicality.value
        reason: $.steps.analyze.scores.practicality.reason
        weight: 0.15
      novelty:
        value: $.steps.analyze.scores.novelty.value
        reason: $.steps.analyze.scores.novelty.reason
        weight: 0.10
      clarity:
        value: $.steps.analyze.scores.clarity.value
        reason: $.steps.analyze.scores.clarity.reason
        weight: 0.10
```

所有权重之和必须在很小的小数误差范围内等于 `1.0`。节点按照加权平均值计算总分，并四舍五入为整数。输出包含总分和归一化后的各维度信息。该节点不会调用模型。

上面六个维度是默认工作流配置，不是写死的应用字段。其他工作流可以使用不同的维度名称和权重，统一结果投影会保存实际使用的维度映射。

### 6.4 `gate` 节点

`gate` 将解析后的左操作数与字面量或解析后的右操作数进行比较。第一版支持：

- 数值比较：`gt`、`gte`、`lt`、`lte`；
- 相等比较：`eq`、`ne`；
- 集合成员判断：`in`、`not_in`。

```yaml
- id: fine_gate
  type: gate
  depends_on: [quality_score]
  predicate:
    left: $.steps.quality_score.total
    operator: gte
    right: 70
  reject:
    output:
      schema_version: 1
      status: fine_rejected
      reference: $.steps.metadata
      screening: $.steps.screen
      content: $.steps.analyze
      score: $.steps.quality_score
```

谓词为真时继续执行；谓词为假时，工作流立即使用解析后的 `reject.output` 正常完成。门禁之后的节点不会启动，也不会生成容易误导的失败或跳过步骤记录。

门禁步骤会记录操作数、比较符、结果和终止状态。操作数类型不兼容属于工作流错误，不能被当作业务拒绝。

### 6.5 结果投影声明

工作流可以声明一个统一结果投影：

```yaml
projection: content_analysis_v1
```

声明后，每一种正常终止输出——包括门禁拒绝输出——都必须通过 `ContentAnalysisDraftV1` 校验。没有声明投影的工作流继续支持任意 JSON 输出。

激活时的校验器负责检查投影名称是否存在。由于映射路径和 Agent 返回值是动态数据，运行时投影校验仍然是最终判断。

### 6.6 完整示例

```yaml
name: valuable-article-analysis
trigger:
  events: [reference.discovered, reference.updated, manual]
projection: content_analysis_v1
nodes:
  - id: metadata
    type: reference
    input:
      reference_id: $.trigger.reference_id
      revision: $.trigger.revision

  - id: screen
    type: agent
    agent_id: 00000000-0000-0000-0000-000000000001
    depends_on: [metadata]
    input:
      metadata: $.steps.metadata
      audience: software-builders

  - id: initial_gate
    type: gate
    depends_on: [screen]
    predicate:
      left: $.steps.screen.score
      operator: gte
      right: 30
    reject:
      output:
        schema_version: 1
        status: initial_rejected
        reference: $.steps.metadata
        screening: $.steps.screen

  - id: resolve
    type: resolve
    depends_on: [initial_gate]
    input:
      reference_id: $.trigger.reference_id

  - id: analyze
    type: agent
    agent_id: 00000000-0000-0000-0000-000000000002
    depends_on: [resolve]
    input:
      metadata: $.steps.metadata
      document: $.steps.resolve
      audience: software-builders
      maximum_quotes: 5

  - id: quality_score
    type: score
    depends_on: [analyze]
    input:
      dimensions:
        relevance:
          value: $.steps.analyze.scores.relevance.value
          reason: $.steps.analyze.scores.relevance.reason
          weight: 0.20
        information_value:
          value: $.steps.analyze.scores.information_value.value
          reason: $.steps.analyze.scores.information_value.reason
          weight: 0.25
        depth:
          value: $.steps.analyze.scores.depth.value
          reason: $.steps.analyze.scores.depth.reason
          weight: 0.20
        practicality:
          value: $.steps.analyze.scores.practicality.value
          reason: $.steps.analyze.scores.practicality.reason
          weight: 0.15
        novelty:
          value: $.steps.analyze.scores.novelty.value
          reason: $.steps.analyze.scores.novelty.reason
          weight: 0.10
        clarity:
          value: $.steps.analyze.scores.clarity.value
          reason: $.steps.analyze.scores.clarity.reason
          weight: 0.10

  - id: fine_gate
    type: gate
    depends_on: [quality_score]
    predicate:
      left: $.steps.quality_score.total
      operator: gte
      right: 70
    reject:
      output:
        schema_version: 1
        status: fine_rejected
        reference: $.steps.metadata
        screening: $.steps.screen
        content: $.steps.analyze
        score: $.steps.quality_score

output:
  schema_version: 1
  status: qualified
  reference: $.steps.metadata
  screening: $.steps.screen
  content: $.steps.analyze
  score: $.steps.quality_score
```

示例中的 Agent ID 只是文档占位符。注册对应 Agent 之前，这份工作流不能被激活。

## 7. 统一分析模型

`ContentAnalysis` 包含：

- `id`；
- `reference_id` 和 `reference_revision`；
- `workflow_definition_id`、`workflow_definition_version` 和 `workflow_run_id`；
- 生成状态：`initial_rejected`、`fine_rejected` 或 `qualified`；
- 初筛分数、初筛理由和可选的初筛摘要；
- 可选的主分类、次级分类和标签；
- 可选的一句话摘要和完整摘要；
- 0 到 10 个主要观点，每个观点包含陈述和解释；
- 0 到 5 条金句，每条包含受限长度的原文和可选上下文；
- 可选的确定性总分；
- 评分维度映射，每个维度包含分值、权重和理由；
- 可选的推荐等级和推荐理由；
- 从工作流步骤复制的 Agent 执行溯源信息；
- `created_at`。

聚合创建后不可修改。内容引用出现新修订版本，或者工作流版本发生变化时，系统创建新的分析聚合。

投影的唯一业务标识为：

```text
(reference_id, reference_revision,
 workflow_definition_id, workflow_definition_version)
```

因此，重放同一次业务分析会返回已存在的结果。`workflow_run_id` 同样具有唯一约束，并能从运行记录直接定位投影结果。

### 7.1 投影校验

`ContentAnalysisDraftV1` 强制保证：

- 输出中的内容引用与工作流触发参数一致；
- 修订版本存在，并且属于该内容引用；
- 所有分数都是 0 到 100 的整数；
- 维度权重大于零，且总和约等于 `1.0`；
- 输出总分与确定性算法计算结果一致；
- 初筛拒绝结果不能包含伪造的全文分析；
- 细筛拒绝和通过结果必须包含分类、摘要、观点、多维评分和推荐信息；
- 所有集合数量和文本长度都受到限制；
- 投影值的任何位置都不能出现临时文档标识或原文正文。

投影失败会使工作流运行失败，并且不会留下部分分析数据。

### 7.2 人工决策改判

`AnalysisDecisionOverride` 包含：

- `id` 和 `analysis_id`；
- `decision`：`qualified` 或 `rejected`；
- 10 到 2,000 个字符的必填改判理由；
- `actor_subject`；
- `created_at`。

改判记录只能追加，不能覆盖。有效结论取最新一条改判记录；没有改判时使用 Agent 生成的状态。原始分数、原始状态、Agent 输出和历史改判记录始终保持不变。

人工改判会改变内容在默认信息流中的可见性，但不会修改数值评分。因此，后续阈值校准仍然可以基于未被篡改的原始证据。

## 8. 笔记模型

`Note` 包含：

- `id`；
- `reference_id`；
- 可选的 `analysis_id`；
- `owner_subject`；
- 1 到 65,536 个 UTF-8 字节的 Markdown `body`；
- `created_at` 和 `updated_at`。

笔记不能关联到其他内容引用的分析。一个用户可以针对同一内容引用创建多条笔记。第一版单用户应用采用硬删除；删除笔记不会影响内容引用或分析结果。

笔记不会保存系统解析出的文章正文。用户可以主动在自己的笔记中引用原文，但产品不会自动把整篇文章复制进笔记。

收藏、划线、文件夹、协作笔记、笔记全文搜索和阅读历史不在本次范围内。

## 9. API 设计

### 9.1 结构化分析

- `GET /api/v1/analyses`
  - 支持按有效状态、生成状态、最低分数、分类、标签、订阅源、内容引用和观察日期范围筛选；
  - 默认只返回有效状态为 `qualified` 的内容；
  - 默认先按分数降序，再按发布时间或观察时间降序；
  - 使用游标分页返回信息卡片。
- `GET /api/v1/analyses/{analysis_id}`
  - 返回全部结构化字段、溯源信息、生成结论、有效结论、改判历史和关联笔记。
- `POST /api/v1/analyses/{analysis_id}/overrides`
  - 请求必须包含新结论和改判理由；
  - 从鉴权上下文记录管理员 subject。

API 永远不返回系统解析出的文章正文，只返回引用中的原文地址，供用户跳转阅读。

### 9.2 用户笔记

- `GET /api/v1/notes`：支持按内容引用和分析结果筛选；
- `POST /api/v1/notes`：创建当前用户的笔记；
- `PUT /api/v1/notes/{note_id}`：替换正文和可选的分析关联；
- `DELETE /api/v1/notes/{note_id}`：删除笔记。

所有操作都从鉴权令牌获取 `owner_subject`。客户端请求不能提交或修改归属字段。

### 9.3 工作流校验

现有工作流校验响应增加：

- 投影名称；
- 所有终止门禁 ID；
- 阈值超出常用 0 到 100 评分范围时的警告；
- 拓扑执行顺序。

以下情况不能通过校验：

- 未知的投影版本；
- 无效谓词操作符；
- 不安全映射；
- 无效评分权重；
- 缺少拒绝输出的门禁。

## 10. 用户界面

当前单一应用新增“信息流”入口，不重新拆分管理端和用户端。

### 10.1 信息流

信息卡片展示：

- 标题、来源、发布时间和原文链接；
- 分类和标签；
- 总分和推荐等级；
- 一句话摘要；
- 简短的通过理由；
- 是否存在管理员人工改判。

用户可以按状态、最低分、分类、来源和日期筛选。被拒绝的内容放在次级审计视图中，用于校准和检查，不干扰默认信息流。

### 10.2 分析详情

详情页展示：

- 摘要；
- 主要观点及解释；
- 各评分维度的分值、权重和理由；
- 受限长度的金句；
- 初筛和细筛结论；
- 工作流与 Agent 溯源信息；
- 改判历史和管理员纠正表单；
- 当前内容引用的笔记列表与 Markdown 编辑器。

原文在新的浏览器标签页中打开。第一版 ZeroMind 不渲染也不缓存完整原文。

### 10.3 工作流编辑器

编辑器中的默认示例改为完整的分析工作流。校验结果展示终止门禁和投影名称。现有工作流保持兼容，不声明投影时继续按照原有方式运行。

## 11. 失败与恢复行为

- 找不到内容引用或修订：分别以 `reference_not_found` 或 `reference_revision_not_found` 失败；
- 原文 URL 无效或被网络策略阻止：解析步骤失败，不创建分析；
- Agent 超时或 Provider 失败：按照现有受限重试策略执行，耗尽后运行失败；
- Agent 输出不符合 JSON Schema：Agent 步骤失败；
- 门禁操作数类型不兼容：门禁失败，不能当作筛选拒绝；
- 分数或权重无效：评分步骤失败；
- 统一投影不符合 Schema：以 `analysis_projection_invalid` 失败，不保存部分结果；
- 重复投影：返回已有聚合；
- 无效改判：拒绝请求，不改变有效状态；
- 笔记归属不匹配：返回未找到，避免泄露其他用户笔记的存在。

门禁提前拒绝会正常完成工作流、投影一份被拒绝的分析，并且不会调用后续 Agent。这是系统控制模型成本的主要机制。

## 12. 安全与隐私

- DSL 中的所有值都只是数据，不引入可执行表达式语言；
- 原文正文继续从持久化的工作流输入、输出、步骤记录、日志和事件中移除；
- 金句和摘要的数量与长度限制可防止 Agent 把投影结果当成文章复制通道；
- Agent 输出先通过其注册的 JSON Schema，再通过统一投影 Schema；
- Provider 凭据继续保存在 Provider Profile 所引用的环境变量中；
- 改判操作者和笔记归属从已验证的身份上下文获取，不接受客户端传入的身份字段；
- API 错误和日志只记录标识符，不记录原文正文或用户笔记正文。

## 13. 测试策略

### 13.1 DSL 与执行器

- 支持字面量，同时保持受限路径的原有行为；
- 拒绝格式错误的 `$` 路径和疑似可执行映射；
- 校验 `reference`、`score` 和 `gate` 节点契约；
- 确定性计算权重总分；
- 覆盖所有谓词操作符和类型不匹配；
- 证明门禁为假时工作流正常终止，且不会调用下游处理器；
- 保持工作流运行幂等；
- 证明成功和失败时都不会持久化临时原文；
- 证明现有工作流 DSL 保持向后兼容。

### 13.2 分析领域与持久化

- 校验每种终止状态的统一结果结构；
- 拒绝不一致的内容引用、修订版本或计算总分；
- 强制执行金句、观点、标签、摘要和理由的数量与长度限制；
- 对同一结果进行幂等投影；
- 内容修订或工作流版本变化时创建不同结果；
- 追加人工改判，并正确计算有效结论；
- 覆盖列表筛选和稳定的游标排序；
- 使用兼容 PostgreSQL 的 SQLAlchemy 模型进行仓储测试。

### 13.3 用户笔记

- 创建、更新、查询和删除当前用户的笔记；
- 拒绝空正文、超长正文、跨引用关联和跨用户操作；
- 证明笔记操作不会修改分析结果。

### 13.4 端到端

使用一组固定测试数据完成：

1. 导入三个内容引用；
2. 在元数据初筛阶段拒绝其中一个；
3. 解析第二个原文并在细筛阶段拒绝；
4. 解析第三个原文并通过细筛；
5. 验证只发生两次全文 Agent 调用；
6. 验证三份结构化结果均已保存，且数据库中没有文章正文；
7. 人工把细筛拒绝结果改判为通过；
8. 验证该内容进入默认信息流；
9. 创建并修改一条笔记；
10. 验证 API 和前端渲染。

测试使用确定性的 Fake Pi 结果和本地公共地址 HTTP 服务，不依赖公开 RSSHub 或真实模型 Provider。

## 14. 交付顺序与提交边界

实现会拆成以下可独立评审的提交：

1. `docs: design structured analysis workflows`
2. `feat: add safe workflow scoring and gates`
3. `feat: persist canonical content analyses`
4. `feat: project workflow results into analyses`
5. `feat: expose analysis feed and decision overrides`
6. `feat: add owned reading notes`
7. `feat: add structured information flow UI`
8. `docs: document and verify the analysis workflow`

每个提交都包含对应测试。现有与本功能无关的迁移启动改动不会混入这些提交。

## 15. 调研来源

- [BestBlogs 官方仓库](https://github.com/ginobefun/BestBlogs)：公开产品文档、Dify 工作流资料、OpenAPI、CLI 和 Agent Skills。
- [BestBlogs 工作原理](https://www.bestblogs.dev/docs/how-it-works)：介绍内容聚合、AI 初筛、结构化质量判断、专家纠正和可解释推荐。
- [BestBlogs 文章初评流程](https://github.com/ginobefun/BestBlogs/blob/main/flows/Dify/ArticleFIlterFlow.md)：介绍第一阶段的低成本输出及放行阈值。
- [BestBlogs 文章分析流程](https://github.com/ginobefun/BestBlogs/blob/main/flows/Dify/ArticleAnalysisFlow.md)：介绍全文分析、分类、评分、反思和结构化输出。
- [BestBlogs Capture API](https://github.com/ginobefun/BestBlogs/blob/main/openapi/05-capture.md)：将个人收藏和笔记与系统生成的内容分析分离。

## 16. 延后能力

- 多篇文章的比较阅读报告；
- 完整的多用户注册与授权；
- 根据用户行为学习的个性化排序；
- 收藏、划线、文件夹和阅读历史；
- 独立人工审核队列；
- 根据人工改判历史自动校准提示词；
- 长文 Map/Reduce 节点；
- 翻译和跨语言结果；
- 语义搜索或向量嵌入；
- 同一新闻的跨来源去重聚类与主题综合。

这些能力以后可以建立在统一的内容分析与笔记标识之上，不需要改变第一版“引用优先”的存储策略。
