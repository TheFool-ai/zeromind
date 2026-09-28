# 流程时序索引

图中 API 负责协议转换，App 是应用服务，UoW 是工作单元。Repository 的 flush 不等于 commit。

| 流程 | 状态 | 图 |
| --- | --- | --- |
| SUB-001 创建来源 | 已实现 | [创建](create-source.md) |
| SUB-002 列表与详情 | 已实现 | [查询](query-sources.md) |
| SUB-003 修改、地址变更、并发冲突 | 已实现 | [修改](update-source.md) |
| SUB-004 启用与关闭 | 已实现 | [启停](toggle-source.md) |
| SUB-006 发现与观察、SUB-007 条目查询 | 领域/仓储已实现，无 HTTP | [条目与修订](item-revisions.md) |
| SUB-005 OPML | 已实现 | [导入](opml-import.md) |
| SUB-008 网络获取 | 规划中 | [规划流程](planned-flows.md) |

图中省略连接池等实现细节，不省略影响业务结果的校验、提交和回滚。规划流程不构成既有 API 契约。
