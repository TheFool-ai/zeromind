# 订阅微服务技术方案

状态：待审阅，尚未实施。日期：2026-09-28。

## 1. 目标与范围

订阅服务负责持续跟踪信息源，发现条目及其变化，并可靠交付给下游。服务拥有订阅配置、轮询状态、抓取记录、Feed 元数据及版本；分析进度、原文提取、评分、笔记和工作流属于 information 应用。

本方案沿用系统共享订阅源的现状，不新增多租户、用户关注关系、跨来源文章合并、可配置调度策略或多 RSSHub 实例。一个微服务可以包含 API、调度器、Worker 等多个进程。

选择独立 Subscription、PollingState 和 FeedItem 聚合。将轮询状态继续放在 Subscription 会混合用户意图和高频执行更新；另建通用定时任务微服务则超出当前需求。

## 2. 当前实现与目标结构

当前 subscriptions 聚合同时保存订阅和轮询状态；ingestion 负责 Feed 抓取、条目去重，并混有分析状态；bootstrap/tasks.py 协调采集与分析。RSSHub 仍有实例管理代码。之前确认的固定 RSSHub 方案尚未实施，纳入本次设计；旧方案中与本方案冲突的内容以本方案为准。

目标部署：

```text
Web → 网关
       ├─ 订阅 API → 订阅数据库
       └─ information API → information 数据库

订阅调度器 → Celery feeds 队列 → 订阅 Worker → HTTP Feed / RSSHub
                                    ↓
                           条目、版本、Outbox
                                    ↓
                        information 内部事件接收接口
                                    ↓
                         Inbox、分析请求 → 分析 Worker
```

保留 FastAPI、SQLAlchemy、Alembic、Celery、PostgreSQL 和 Compose。两个服务可使用同一 PostgreSQL 实例，但使用独立数据库和账号；禁止跨库外键、跨服务 SQL 查询和导入对方领域包。

第一版只有一个下游，选择 Outbox 通过内部 HTTP 可靠投递，避免增加事件中间件。Celery 用于服务内部任务；不让订阅 Worker 直接调用分析任务。将来增加消费者时可替换投递适配器，事件契约保持稳定。

## 3. 领域模型

### 3.1 Subscription：业务订阅聚合

字段：id、feed_address、title、site_url、categories、enabled、created_at、updated_at、version。

方法：create、enable、disable。第一版不新增删除或修改地址接口。

规则：规范化地址唯一；标题非空；分类去空白去重；重复启停为幂等操作。抓取失败不改变 enabled。version 用于防止配置并发覆盖。

### 3.2 PollingState：轮询状态聚合

以 subscription_id 为身份，与 Subscription 一对一。字段：next_poll_at、last_checked_at、last_success_at、consecutive_failures、health、etag、last_modified、version。

方法：schedule_now、record_success、record_failure。健康取值 unknown、healthy、degraded、error；停用是 Subscription 的状态，不是健康状态。新建为 unknown；成功后 healthy；失败前两次 degraded，第三次起 error。重新启用不伪造成功记录。

调度所需 lease_token、lease_expires_at、active_attempt_id 一并存储，但属于仓储调度机制，不作为领域值对象。next_poll_at 只表达业务轮询时间，不能再兼任租约。

### 3.3 FetchAttempt：单次执行记录

字段：id、subscription_id、lease_token、status、started_at、finished_at、http_status、error_code、脱敏 error_message、discovered_count、updated_count、unchanged_count。

状态 running → succeeded / failed / abandoned。一次实际执行一条记录；重试创建新记录。超时回收标记 abandoned。队列重复投递不创建重复执行记录。第一版它是独立记录实体，不建设通用任务聚合或完整事件溯源系统。

### 3.4 FeedItem：来源条目聚合

字段：id、subscription_id、identity_key、current_revision、first_seen_at、last_seen_at、version。

方法：discover、observe。去重范围为同一个订阅，唯一约束为 (subscription_id, identity_key)。observe 总是持久化 last_seen_at；元数据指纹相同不增加版本；变化时生成新修订。Feed 中不再出现的条目不视为删除。

FeedItem 通过 ID 关联 Subscription，不放入 Subscription 内部集合。不同来源的同一文章允许存在多个条目。

### 3.5 FeedItemRevision：不可变修订实体

以 (item_id, revision_number) 标识。保存 title、original_url、summary、author、published_at、source_updated_at、observed_at、metadata_fingerprint。不保存网页正文或分析状态。属于 FeedItem 的一致性边界，但物理上独立表存储，按需加载历史。

### 3.6 值对象与领域策略

| 对象 | 规则 |
| --- | --- |
| FeedAddress | HTTP/HTTPS、rsshub 地址校验和规范化 |
| EntryIdentity | GUID、规范化链接或兜底哈希形成的稳定身份 |
| EntryMetadata | 一次观察的规范化元数据及其指纹 |
| FeedHealth | unknown、healthy、degraded、error |
| EntryIdentityPolicy | 优先 GUID，其次 URL，最后订阅 ID、标题、发布时间、原始链接哈希 |
| PollingPolicy | 成功间隔默认 30 分钟；失败 min(30 × 2^(n-1), 1440) 分钟 |

策略不做数据库、网络或队列 I/O。固定规则可实现为纯函数，无需额外服务容器。

## 4. 应用服务和接口

SubscriptionApplicationService 组织创建、列表、启停和 OPML 导入；PollingApplicationService 组织认领、执行和完成；OutboxPublisher 负责投递。FeedClient、FixedRSSHubResolver、XML 解析器、仓储均属于适配器。

保留外部 /api/v1/subscriptions 下的创建、列表、enable、disable、opml/preview、opml/import 路径。查询 DTO 组合 Subscription 与 PollingState；前端分别呈现启停和健康。新增只读 GET /api/v1/subscriptions/{id}/fetch-attempts，采用游标分页。

OPML 保留逐条导入、重复跳过和无效条目报告。普通创建返回 409 重复、422 参数错误；不存在订阅返回 404。暂不新增手动执行和自定义间隔接口。

## 5. 事务、调度和并发

### 5.1 创建、启停

创建 Subscription 和初始 PollingState 在一个本地事务中完成。初始 next_poll_at=now。启用时锁定对应行，更新 enabled 并 schedule_now；停用只改 enabled，不清空抓取历史。重复启用不重复重排轮询。

### 5.2 认领和队列投递

调度扫描建议每分钟运行，每批最多 1000 条。筛选 enabled=true、next_poll_at<=now 且无有效租约的记录。仓储以固定顺序锁定订阅和轮询行，使用 SKIP LOCKED，避免多个调度器重复认领和与启停相互覆盖。

认领生成 lease_token，租约建议 5 分钟。事务提交后将 subscription_id、lease_token 发送到 feeds 队列。发送失败可用 token 条件释放租约；进程崩溃由租约超时恢复，业务到期时间不改变。第一版执行设置小于租期的硬时间上限，超出上限按失败恢复，不做复杂租约续期。

Worker 开始时原子验证 token、租期、enabled 和 active_attempt_id。停用且未开始的任务放弃；同一 token 已开始的重复任务退出。成功开始后创建 FetchAttempt 并登记 active_attempt_id。

### 5.3 抓取与保存

网络请求在数据库事务外执行。每批条目入库前锁定 PollingState，验证租约和 token；验证失败则禁止旧 Worker 写入。FeedItem、Revision 和对应 Outbox 消息在同一事务提交；较大 Feed 按批提交，避免长事务。

全量处理完成后再次验证 token，完成 FetchAttempt、更新 PollingState 的 ETag、Last-Modified、健康和 next_poll_at，并释放租约。HTTP 304 视为成功，保留校验信息。成功或失败后的间隔从完成时间计算。

中途失败时保留已提交批次和事件；不推进成功缓存校验信息。重试通过条目唯一约束、版本比较恢复。失败完成事务更新失败次数并安排退避。基础设施暂时无法写库时交由租约回收恢复，不声称已经记录失败。

### 5.4 停用和失效执行

已开始的任务可以完成，结果回写只更新轮询状态，绝不能覆盖 enabled。停用后不产生新认领。停用后又启用且旧任务仍在执行时，沿用现有执行；完成后按正常间隔调度，不额外并发抓取。

租约过期后，回收器将旧 running 记录标记 abandoned、计一次失败并应用退避，再释放租约；正常失败处理与回收通过条件更新确保只计一次。旧 Worker 即使后来拿到响应，也不能以失效 token 保存任何新结果。已经提交的批次仍有效。

## 6. 领域事件与集成事件

内部领域事件：SubscriptionCreated、SubscriptionEnabled、SubscriptionDisabled、FeedHealthChanged、FeedItemDiscovered、FeedItemUpdated。仅在真实状态转换时产生。每次执行详情记录在 FetchAttempt，不额外发布全部执行日志事件。没有消费者的内部事件不要求单独持久化。

第一版对外只发布：

- subscriptions.feed_item.discovered.v1
- subscriptions.feed_item.updated.v1

应用层将领域事件转换为稳定消息契约；v1 为契约版本，revision 为条目版本。

```json
{
  "event_id": "uuid",
  "event_type": "subscriptions.feed_item.discovered.v1",
  "occurred_at": "2026-09-28T10:00:00Z",
  "subscription_id": "uuid",
  "item_id": "uuid",
  "revision": 1,
  "source": {"title": "技术资讯", "feed_address": "rsshub://example/news"},
  "metadata": {
    "title": "文章标题", "url": "https://example.com/article",
    "summary": "Feed 摘要", "author": null,
    "published_at": "2026-09-28T09:00:00Z", "source_updated_at": null
  }
}
```

source 是观察时的快照；第一版改名不会反向修改历史条目事件。身份键不作为跨服务匹配依据，消费者使用稳定 item_id。

Outbox 对 (item_id, revision, event_type) 唯一，重发保持 event_id。发布器对失败投递执行有上限间隔的退避；永久拒收标记待处理并告警，保留重放能力。不得静默丢弃。

information 提供 POST /internal/v1/subscription-events，以服务端环境变量配置的服务凭据认证；请求内容不包含 RSSHub 凭据。接收端在一个本地事务内写入 Inbox、来源/条目投影和待处理分析请求，提交后返回 2xx。重复 event_id 返回成功；无效契约返回 4xx。

投递语义是至少一次。接收端按 (item_id, revision) 保证同版本只建立一次请求；先收到高版本也能建立条目，后到低版本不得回退当前版本或覆盖新结果。HTTP 2xx 仅表示可靠接收，不表示分析完成。

## 7. 数据所有权

订阅数据库：subscriptions、polling_states、fetch_attempts、feed_items、feed_item_revisions、outbox_messages。

information 数据库：来源和条目本地投影、inbox_messages、分析请求、分析结果、工作流、笔记等。原 ContentReference 的分析状态留在 information；其来源和元数据通过事件更新。前端信息流查询继续由 information 本地完成，不逐条远程查询订阅服务。

跨服务只保存逻辑 ID，不保留跨库外键。订阅内部外键继续使用数据库约束。记录历史、事件和投影的保留清理由运维策略处理，首版不自动删除待投递事件。

## 8. RSSHub 和安全边界

固定适配器读取 ZEROMIND_RSSHUB_BASE_URL=http://rsshub:1200；rsshub 容器不发布宿主机端口。来源 Token、Cookie 和代理由 RSSHub 自身配置。删除多实例管理页面、API、领域对象和仓储。

基础地址校验 HTTP/HTTPS、主机、端口和路径前缀，拒绝内嵌凭据、查询、片段和路径穿越。逻辑地址保留路由及普通查询参数；抓取时移除 key/code，不生成认证参数。

注意：在解析时移除 key/code 只防止参数被转发，不能保证原始订阅中未保存这些参数。创建/OPML 的敏感参数处理需显式落实为拒绝携带认证参数的 rsshub 地址，并测试已有数据迁移报告；不把解析器过滤误写成存储层保护。

保留网络地址校验、逐跳重定向检查、超时、响应大小限制和私有主机精确白名单。业务 API 复用现有网关访问控制；新内部事件接口必须校验服务凭据。错误记录和日志进行凭据脱敏。

## 9. 代码与部署组织

```text
apps/subscriptions/
  src/subscription_service/
    domain/
      aggregates/       # Subscription、PollingState、FeedItem
      entities/         # FeedItemRevision、FetchAttempt
      value_objects/
      policies/
      events/
      repositories/
    application/        # 用例、DTO、端口、事务协调
    infrastructure/     # SQL、Feed、RSSHub、OPML、队列和事件投递
    interfaces/http/
    bootstrap/          # API、Celery、依赖组装
  migrations/
  tests/
  Dockerfile
```

每个领域对象独立文件。Compose 增加 subscription-api、subscription-worker、subscription-beat、subscription-migrate，使用同一服务镜像和独立任务队列。information 保留分析执行进程。可共用 Redis 进程，但隔离队列命名与连接配置。迁移任务先完成，再启动服务。

健康检查区分存活与数据库/队列就绪；RSSHub 暂时故障不令管理 API 下线。监控至少覆盖到期延迟、抓取失败率、失效租约、待投递事件数量及最老事件年龄。

## 10. 分阶段迁移

1. 在现有应用内部拆出 PollingState 和 FetchAttempt，补齐事务和租约约束，前端调整启停/健康展示。
2. 实施固定 RSSHub 适配器，移除管理功能；保留旧 Alembic 历史。旧实例表清理使用新增迁移，并在部署前备份、说明删除的是实例配置。
3. 建立事件契约、Outbox 投递和 information Inbox，先测试重复、乱序、下游离线及恢复；旧直接派发与新事件消费不得同时触发同一版本分析。
4. 创建独立应用和数据库迁移，编写一次性数据迁移工具。保持 Subscription、条目和修订 ID；从旧表拆出轮询数据；不伪造不存在的抓取历史。旧 disabled 健康且无可靠历史时映射为 unknown；有成功/失败记录时按其还原。
5. 采用维护窗口切换：备份；暂停旧订阅写入和采集调度；排空或明确作废在途抓取；排空旧采集事件；复制数据；校验数量、ID、版本和指纹；启动新服务；切换网关；启用新调度和事件消费。迁移快照本身不重新触发全量分析。
6. 观察稳定后清理旧代码与冗余表。旧 information 中必要的来源、条目数据转为本地投影；保留笔记和分析的本地关联，不直接删掉整个 ingestion 包。

切换前可以恢复旧路径。切换后若新服务已经产生写入，回滚必须暂停新写入并迁回增量或重放事件；不能只切回旧容器。第一版不设计在线双写。

## 11. 验收标准

- Subscription 不再包含执行结果或抓取健康状态；重复抓取不改变订阅配置。
- 新建、停用、重新启用、304、连续失败和恢复成功符合明确状态规则。
- 重复任务仅执行一次；租约过期的旧 Worker 无法保存结果；停用不会被结果回写覆盖。
- 未变化条目更新 last_seen_at；新身份产生一个条目；变化产生一个版本和一条对应事件。
- 条目和 Outbox 原子提交；部分批次成功后重试不会漏发或重复新增版本。
- 下游离线时采集继续；恢复后事件可重放；重复、乱序事件不重复分析或回退版本。
- 两个服务能独立启动、升级和测试，不读取对方数据库或导入对方领域代码。
- HTTP Feed、RSSHub、OPML、信息流、分析详情和笔记关联通过回归验证。
- 使用真实 PostgreSQL 验证行锁、条件更新及唯一约束；临时数据库演练升级、数据迁移和恢复。

## 12. 审阅重点

本方案建议优先确认三项架构决策：订阅服务是否拥有 Feed 条目及修订；是否接受一个下游的 Outbox + HTTP 投递方式；是否接受维护窗口迁移。实现前可据此调整，不需要提前增加通用任务平台或事件中间件。
