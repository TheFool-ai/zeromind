# 内容引用分析状态机与阅读详情设计

日期：2026-08-04

## 1. 目标

ZeroMind 为每条内容引用保存当前分析状态。RSS 首次发现内容后，引用从 `pending`
进入唯一的主分析流程；RSS 元数据产生新 revision 时，引用直接覆盖回 `pending`，以最新
revision 重新分析。状态随着六 Agent DSL 的执行阶段更新，最终进入通过、业务拒绝或技术失败
终态。

主工作流由 `bestblogs-six-agent-analysis` 原地更名为“信息分析工作流”，保留已有工作流 ID，
并作为唯一有权修改引用分析状态的工作流。

管理端同时重做内容引用列表和详情页。列表展示 RSS 元数据、分析进度和分析摘要；详情页参考
BestBlogs 的阅读详情信息架构，左侧嵌入原文，右侧展示摘要、观点、金句、分类和六维评分。
BestBlogs 官方文档将其阅读详情描述为原文阅读页面中的右侧 AI 侧栏，提供结构化摘要、核心
观点和金句等能力：<https://www.bestblogs.dev/docs/personal/ai-reading>。

## 2. 范围

本次包含：

- 引用级当前分析状态机；
- revision 条件更新，防止过期工作流覆盖新内容状态；
- 主分析工作流重命名和唯一性规则；
- 工作流步骤到引用状态的实时映射；
- 正常门禁拒绝、技术失败、人工重跑和崩溃恢复；
- 历史内容引用的幂等回填和批量分析；
- 内容引用列表 API、筛选和卡片改版；
- 内容引用阅读详情聚合 API；
- 原文 iframe 与结构化分析侧栏；
- 数据迁移、自动化测试和本地历史数据处理。

本次不包含：

- 状态变更事件表或完整状态历史；
- 按 revision 保存多份引用状态；
- 持久化文章正文、网页 HTML 或网页快照；
- 绕过原网站的 CSP、`X-Frame-Options`、登录或访问限制；
- AI 问答、段落跳转或翻译功能。

## 3. 设计选择

### 3.1 采用引用表当前状态

状态直接保存在 `content_references`。列表查询无需扫描 workflow run，RSS 更新也可以在同一
事务中重置状态。workflow run、step run 和 agent session 继续负责详细执行追溯。

不采用动态推导状态：它会让失败、重试、多工作流和无 workflow run 的 `pending` 状态产生
歧义。不新增状态事件表：当前需求只关心引用最新状态，已有运行和 session 表已提供执行审计。

### 3.2 状态属于引用的当前 revision

引用只保存一份当前状态，不保留旧 revision 的状态副本。`analysis_status_revision` 标识当前状态
对应的 revision。工作流更新状态必须携带其启动时的 revision，Repository 使用条件更新：

```sql
UPDATE content_references
SET analysis_status = :next_status, ...
WHERE id = :reference_id
  AND current_revision = :revision
  AND analysis_status_revision = :revision
```

若影响行数为零，说明 RSS 已产生更新；旧工作流继续保留自己的运行记录，但不得改变引用当前
状态或当前分析投影。

### 3.3 唯一主分析工作流

只有名称为“信息分析工作流”、投影为 `content_analysis_v1` 的激活工作流可以改变引用状态。
现有 `bestblogs-six-agent-analysis` 原地改名并更新 YAML 中的 `name`，保留 ID 和版本历史关联。
注册脚本识别旧名称并幂等迁移，不能并存两个激活的主分析工作流。

其他手工或辅助工作流仍可运行，但不改变引用状态。没有激活主工作流时，引用保持 `pending`，
API 暴露等待主流程配置的原因。

## 4. 数据模型

`content_references` 新增：

| 字段 | 类型 | 说明 |
|---|---|---|
| `analysis_status` | varchar(32) | 当前分析状态，默认 `pending` |
| `analysis_status_revision` | integer | 状态对应的 revision |
| `analysis_workflow_run_id` | UUID nullable | 当前或最近一次主分析 run |
| `analysis_error_code` | varchar(64) nullable | 最近一次技术失败代码 |
| `analysis_error_message` | text nullable | 脱敏且限长的失败信息 |
| `analysis_status_updated_at` | timestamptz | 最近状态更新时间 |
| `analysis_started_at` | timestamptz nullable | 本轮分析开始时间 |
| `analysis_completed_at` | timestamptz nullable | 本轮终态时间 |

`analysis_workflow_run_id` 外键指向 `workflow_runs.id`，删除 run 时使用 `SET NULL`，避免删除执行
历史影响引用。对 `analysis_status`、`analysis_status_updated_at` 建索引。

允许状态集合：

- `pending`
- `queued`
- `screening`
- `resolving`
- `analyzing`
- `classifying`
- `scoring`
- `reviewing`
- `finalizing`
- `initial_rejected`
- `fine_rejected`
- `completed`
- `failed`

Domain 提供显式状态转换方法，Repository 不接受任意字符串。开始新一轮时清空 run、错误、
started/completed 时间；进入 `queued` 时绑定 run；进入技术失败时写错误；进入三个正常终态时
清空错误。

## 5. 状态机

```text
pending
  -> queued
  -> screening
       -> initial_rejected
  -> resolving
  -> analyzing
  -> classifying
  -> scoring
  -> reviewing
  -> finalizing
       -> fine_rejected
       -> completed
```

任何非终态都可进入 `failed`。`failed`、`completed`、`initial_rejected` 和 `fine_rejected` 在人工
重新分析或 RSS 更新时可进入 `pending`。业务拒绝不是错误，不写 `analysis_error_*`。

节点映射：

| 工作流时机或节点 | 引用状态 |
|---|---|
| 分析请求已认领、run 已创建 | `queued` |
| `screening` 开始 | `screening` |
| `initial_gate` 拒绝 | `initial_rejected` |
| `resolve` 开始 | `resolving` |
| `core_analysis` 开始 | `analyzing` |
| `taxonomy` 开始 | `classifying` |
| `quality_scoring` 开始 | `scoring` |
| `review` 开始 | `reviewing` |
| `finalize`、确定性评分和细筛门禁 | `finalizing` |
| `fine_gate` 拒绝且投影成功 | `fine_rejected` |
| qualified 投影成功 | `completed` |
| 执行或投影异常 | `failed` |

状态观察器在主工作流中启用。Workflow Executor 只发出通用生命周期通知，不依赖 ingestion；
`ReferenceAnalysisLifecycleObserver` 负责节点映射和 revision 条件更新。终态必须在 Analysis
Projector 成功后写入，避免 workflow 输出有效但内容分析投影失败时错误标记为完成。

## 6. RSS、排队和重跑

### 6.1 RSS 首次发现

创建引用和 revision 1 时同时写入 `analysis_status=pending`、
`analysis_status_revision=1`，并继续使用事务型 outbox 发布 `reference.discovered`。

### 6.2 RSS 更新

新增 revision 的同一事务中：

- 更新 `current_revision`；
- 将状态重置为 `pending`；
- 将 `analysis_status_revision` 更新为新 revision；
- 清空当前 run、错误和本轮时间；
- 发布 `reference.updated`。

旧 workflow run 的后续状态条件更新自然失效。

### 6.3 人工重新分析

新增 `POST /api/v1/references/{reference_id}/reanalyze`。它将当前 revision 重置为 `pending`，并
写入 `reference.analysis.requested` outbox。请求包含唯一 request ID，因此不会复用已失败的
workflow run 幂等键；重复点击由短期幂等键或当前处理中状态拒绝，返回 409。

### 6.4 崩溃恢复

恢复任务每五分钟扫描超过 30 分钟仍处于处理状态的引用：

- run 已失败：引用标记 `failed`；
- run 已完成但引用未写终态：根据已投影分析修复终态；
- run 仍为 `running` 且超时：run 和引用均标记失败，错误码 `stale_workflow`；
- 引用没有 run：重置 `pending` 并重新发布分析请求。

## 7. 历史数据处理

迁移为所有已有引用设置：

- `analysis_status = pending`
- `analysis_status_revision = current_revision`
- `analysis_status_updated_at = migration time`

提供 `backfill_reference_analysis.py`：

- 默认选择没有当前主流程分析结果的引用；首次上线使用 `--all` 处理全部历史引用；
- 分页读取并按批次写入 `reference.analysis.requested` outbox；
- 幂等键包含 reference ID、revision、主工作流版本和 backfill generation；
- 不直接在命令中调用 LLM；由现有 Worker 消费；
- 支持 `--batch-size`、`--limit`、`--dry-run`；
- 输出 pending、queued、processing、completed、rejected、failed 计数；
- 重复运行不会为同一 generation 创建重复事件。

当前本地数据库有 73 条引用且没有成功分析。上线验证后运行一次 `--all`，持续观察 Worker、
Provider 配额和失败数，直到所有引用进入终态。

## 8. API

### 8.1 引用列表

`GET /api/v1/references` 增加筛选参数：

- `status`
- `category`
- `minimum_score`
- `subscription_id`
- `published_from` / `published_to`

列表项聚合当前 revision 和当前主流程分析，返回：

- 引用 ID、revision、URL；
- 标题、摘要、作者、发布时间；
- 来源名称；
- 分析状态、状态时间、错误摘要；
- 一句话摘要；
- 主分类、标签、总分；
- 当前 workflow run ID。

没有分析结果时，分析字段为 null，但引用仍返回。

### 8.2 阅读详情

新增 `GET /api/v1/references/{reference_id}/reading-detail`，一次返回：

- 当前引用和 RSS revision 元数据；
- 当前分析状态和错误；
- 当前 `ContentAnalysis` 的完整摘要、观点、金句、分类、标签、评分和溯源；
- `iframe_url`，仅为经过现有 URL 规范化后的 HTTP(S) 原文地址；
- `can_embed` 不做虚假保证，前端始终提供降级入口。

聚合端点只读取已有结构化数据，不重新抓取正文。

## 9. 管理界面

### 9.1 内容引用列表

列表由 URL 卡片改为信息卡片：

- 标题为主信息；
- 来源、作者和发布时间为次信息；
- 状态徽标显示当前阶段；
- 已分析内容显示一句话摘要、主分类、标签和总分；
- `failed` 显示安全错误摘要和重新分析按钮；
- pending/处理中内容保持可见；
- 顶部提供全部、待处理、处理中、已完成、已拒绝、失败快捷筛选。

点击卡片进入 `/references/:id`。

### 9.2 阅读详情

桌面端使用约 65/35 双栏：

- 左侧：受限 iframe 加载原文；
- 右侧：sticky 分析侧栏；
- 顶部：标题、来源、发布时间、状态、总分和“新窗口打开原文”；
- 侧栏区块：一句话总结、摘要、主要观点、金句、六维评分、分类标签、执行溯源。

iframe 安全属性：

- `sandbox="allow-scripts allow-same-origin allow-forms allow-popups"`；
- 不允许 top navigation；
- `referrerPolicy="no-referrer-when-downgrade"`；
- URL 只来自后端规范化的当前 revision；
- 始终展示新窗口入口和 RSS 元数据回退卡。

浏览器无法可靠判断跨域页面因 `X-Frame-Options` 或 CSP 被阻止，因此界面不宣称自动检测
成功。用户看到浏览器阻止页时仍可打开原站，分析侧栏不受影响。

移动端使用“AI 分析 / 原文”页签，默认先显示 AI 分析，避免窄屏 iframe 破坏阅读体验。

处理中详情页显示当前阶段时间线；终态详情展示结构化结果；失败详情展示错误和重新分析操作。

## 10. 错误、安全和一致性

- 正文仍只在工作流运行期间存在，不进入引用、状态、API、outbox 或新详情端点。
- 错误消息沿用安全截断和敏感值清洗。
- iframe 不代理、不改写、不缓存目标站点内容。
- 状态和分析投影均校验 revision；过期 run 不成为引用当前分析。
- 主工作流不存在或未激活时不把引用标记失败，保持 `pending` 并暴露等待原因。
- 多 Worker 通过数据库条件更新和现有 outbox 幂等键避免重复状态推进。
- 状态字段是便于查询的当前投影；workflow runs 和 agent sessions 才是执行事实来源。

## 11. 测试与验收

### 11.1 Domain 和 Repository

- 新引用默认 pending；
- 新 revision 重置 pending 并清空旧运行信息；
- 合法状态转换通过，非法跳转失败；
- 旧 revision 状态写入不影响当前引用；
- SQL 条件更新在并发时只成功一次。

### 11.2 工作流集成

- 主工作流节点依次产生正确状态；
- 初筛拒绝进入 `initial_rejected`；
- 细筛拒绝进入 `fine_rejected`；
- 投影成功才进入 `completed`；
- 任一 Agent、Schema 或投影失败进入 `failed`；
- 辅助工作流不改变引用状态；
- RSS 更新期间旧 run 不能覆盖新 revision pending。

### 11.3 历史回填

- dry run 不修改数据；
- 重复运行不重复排队；
- 中断后可以继续；
- 73 条本地历史引用均被排队并最终进入某个终态；
- 数据库中不存在永久卡住的处理中引用。

### 11.4 API 和 UI

- 列表包含未分析、处理中、完成、拒绝和失败引用；
- 状态和筛选与数据库一致；
- 详情聚合当前 revision 的分析；
- iframe URL 安全规范化且带 sandbox；
- 摘要、观点、金句、六维评分、分类和标签正确渲染；
- 无分析、被拒绝、失败和 iframe 被阻止均有明确回退界面；
- 桌面与移动布局通过构建、组件测试和浏览器截图检查。

## 12. 上线顺序

1. 部署数据库迁移和兼容旧数据的后端；
2. 原地重命名并激活“信息分析工作流”；
3. 部署 Worker、API 和管理端；
4. 对少量引用执行 backfill 验证状态、Provider 和投影；
5. 对现有 73 条引用运行 `--all`；
6. 监控直至全部进入终态，失败项按错误类型重试；
7. 验证列表、详情、iframe 回退和结构化分析展示。
