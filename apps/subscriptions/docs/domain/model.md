# 领域对象与接口

状态：已实现领域规则、校验、SQL 仓储及订阅源管理应用层和 HTTP 接口。网络抓取和事件发布后续接入。

## 对象清单

| 对象 | 类型 | 位置 |
| --- | --- | --- |
| Subscription | 订阅源聚合根 | domain/aggregates/subscription.py |
| SubscriptionItem | 来源条目聚合根 | domain/aggregates/subscription_item.py |
| ItemRevision | 不可变修订实体 | domain/entities/item_revision.py |
| FeedAddress | 来源地址值对象 | domain/value_objects/feed_address.py |
| ItemIdentity | 条目身份值对象 | domain/value_objects/item_identity.py |
| ItemMetadata | 元数据值对象 | domain/value_objects/item_metadata.py |
| FetchCheckpoint | 获取检查点值对象 | domain/value_objects/fetch_checkpoint.py |

以上路径相对于 src/subscription_service/。每个字段的用途见源码中文注释。
来源、条目按 ID 比较身份；修订按 (item_id, revision_number) 比较身份；值对象按字段值比较。
时间必须包含时区，统一转换成 UTC，拒绝时间倒退。

## 聚合接口

| 对象 | 方法 | 行为 |
| --- | --- | --- |
| Subscription | create | 创建默认启用、版本 1、空检查点的来源 |
| Subscription | update_details | 校验并替换名称和分类；相同内容不推进版本 |
| Subscription | change_address | 同一来源迁移地址，清空检查点并推进配置与地址版本 |
| Subscription | enable / disable | 幂等启停，不改写历史条目或伪造成功记录 |
| Subscription | record_fetch_success | 完整成功后更新检查点，不修改配置版本、启停或 updated_at |
| SubscriptionItem | discover | 返回新条目及版本 1，必须一起保存 |
| SubscriptionItem | observe | 内容变化返回新修订，否则只更新 last_seen_at |
| ItemRevision | create | 校验正修订号、时间并规范化元数据，创建不可变快照 |

observe 必须传入所属条目的当前修订，拒绝其他条目和过期修订。校验失败不推进聚合状态。
返回 None 也必须保存条目，不能漏掉最后观察时间。

## 值对象规则

- FeedAddress 的直接构造和 parse 都进行校验；HTTP 地址统一协议、主机、默认端口和查询参数，移除片段；RSSHub 保留路由大小写和查询顺序，拒绝认证参数与路径穿越。
- FeedAddress 不执行 DNS 或内网限制检查，网络安全策略属于后续网络适配器。
- ItemMetadata.normalized 返回规范化副本；可选空字符串变 None，缺失标题使用 (untitled)，链接只接受 HTTP/HTTPS，时间转 UTC。
- ItemMetadata.fingerprint 使用规范化内容计算 SHA-256；has_same_content_as 按规范化内容比较。
- ItemIdentity 校验类型及非空值，但不自动选择 GUID、URL 或哈希；身份推导策略后续实现。
- FetchCheckpoint 保存条件请求头和最近成功时间；304 时调用方传入已有头信息。

## 版本与并发

configuration_version 表示配置变化。address_version 只表示地址变化，解决改走又改回的问题；改名不使地址版本失效。record_fetch_success 支持 expected_address_version 校验旧请求。

row_version 是仓储内部的乐观锁，不泄露为领域字段。即使配置版本没变，其他事务保存检查点也能被检测，避免过期聚合覆盖新状态。冲突后必须重新加载并重新执行业务操作。

## 已实现和后续范围

已实现两个仓储契约、SQLAlchemy 适配器和显式工作单元，见 [持久化说明](../implementation/persistence.md)。
不保留 site_url；不将调度、租约、重试或执行日志放进订阅领域。

领域事件仍处于设计阶段，当前未加入事件类、事件收集器或 Outbox，候选契约见 [事件设计](events.md)。创建和观察方法目前只改变领域状态。订阅源管理和 OPML 导入应用服务及 HTTP 接口已接入，Feed 获取后续实现。

## 聚合边界

Subscription 与 SubscriptionItem 是两个独立聚合根。条目通过 subscription_id 引用来源，不把全部条目装载进来源聚合。
ItemRevision 是条目聚合内的不可变历史实体；ItemMetadata 是修订携带的内容值对象。
FetchCheckpoint 属于来源聚合，FeedAddress 描述来源地址，ItemIdentity 描述来源范围内的条目身份。
这些逻辑关系不意味着每个领域对象都有独立表，物理关系见 [ER 图](../implementation/er-diagram.md)。

同一服务的工作单元可以协调来源与条目的持久化事务，但不跨服务共享事务或数据库。
