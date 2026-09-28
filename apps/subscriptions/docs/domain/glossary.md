# 统一术语

| 名称 | 本上下文含义 |
| --- | --- |
| Subscription / 订阅源 | 可配置的 Feed 来源，独立聚合根，不代表定时任务或付费订阅 |
| FeedAddress | HTTP/HTTPS 或 RSSHub 来源地址，创建时规范化 |
| SubscriptionItem / 条目 | 某来源下稳定身份的一条内容，独立聚合根 |
| ItemIdentity | guid、url、hash 类型和身份原值；当前不自动推导 |
| ItemMetadata | 标题、链接、摘要、作者、来源时间等元数据 |
| ItemRevision / 修订 | 条目某次内容版本的不可变快照 |
| FetchCheckpoint / 检查点 | ETag、Last-Modified、最近成功获取时间，不是执行日志 |
| configuration_version | 来源配置变化版本，用于客户端过期配置校验 |
| address_version | 仅地址变化时递增，改走又改回也改变版本 |
| row_version | 数据库存储层乐观锁，不是领域字段或公开 DTO 字段 |
| current_revision | 条目当前修订号，不是来源配置版本 |
| 工作单元 / UoW | 一次数据库会话及事务边界，显式提交，失败回滚 |
| 领域服务 | 承载不自然属于某个实体的领域规则；不等同于 HTTP 服务 |
| SubscriptionService | 当前应用服务，编排来源管理用例及事务，不是聚合或领域服务 |
| 运行管理 | 未来管理任务调度、重试与运行状态的独立上下文 |

参见 [领域模型](model.md)。
