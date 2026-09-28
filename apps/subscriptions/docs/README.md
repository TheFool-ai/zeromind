# 订阅服务知识库

以代码现状为事实来源，规划内容显式标注；文档不是另一套实现。
本知识库分为领域、功能、实现、测试和运行指南，各主题只维护一份正文。

## 阅读入口

| 我想了解 | 入口 |
| --- | --- |
| 订阅服务负责什么、不负责什么 | [限界上下文](domain/context.md) |
| 名词、聚合、实体与规则 | [术语](domain/glossary.md)、[领域模型](domain/model.md) |
| 事件如何设计 | [候选事件，尚未实现](domain/events.md) |
| 录入、查询、修改、启停 | [来源管理功能](features/source-management.md) |
| 条目和内容修订 | [条目管理功能](features/item-management.md) |
| 批量导入 | [OPML 导入](features/opml-import.md) |
| 分层和事务如何组织 | [实现架构](implementation/architecture.md) |
| 有哪些表、字段和约束 | [ER 图](implementation/er-diagram.md)、[持久化](implementation/persistence.md) |
| 接口与调用流程 | [API](implementation/api.md)、[时序图目录](implementation/sequences/README.md) |
| 如何验证 | [测试入口](testing/README.md)、[覆盖映射](testing/coverage.md) |
| 如何启动 | [本地开发](operations/local-development.md) |

## 能力状态

| 编号 | 功能 | 状态 |
| --- | --- | --- |
| SUB-001 | 手动创建来源 | 已实现 HTTP、应用层、领域和仓储 |
| SUB-002 | 来源列表与详情 | 已实现 HTTP 查询 |
| SUB-003 | 修改来源配置和地址 | 已实现，支持版本检查 |
| SUB-004 | 启用和关闭来源 | 已实现，重复操作幂等 |
| SUB-005 | OPML 批量导入 | 已实现安全解析、逐项事务、重复跳过及 HTTP 报告 |
| SUB-006 | 条目发现、去重与修订 | 领域和仓储已实现；自动身份推导、采集编排未实现 |
| SUB-007 | 条目与历史查询 | 仓储已实现；应用层和 HTTP 未实现 |
| SUB-008 | 获取 Feed 与更新检查点 | 检查点领域方法已实现；网络适配器和应用流程未实现 |

## 维护约定

遵守 [项目文档约定](../../../docs/conventions/documentation.md)。每篇文档正文不超过 2000 行（图表除外），优先按主题拆分。
功能编号连接规则、实现流程和测试，不用复制源码代替解释。
项目级边界见 [上下文地图](../../../docs/architecture/context-map.md)。
