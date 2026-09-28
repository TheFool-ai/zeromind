# ZeroMind

ZeroMind 正在按业务领域重新设计。本分支从订阅服务开始逐步重建。

## 当前结构

```text
docs/                    # 项目整体架构、服务边界和归档说明
apps/
  subscriptions/         # 订阅领域、SQL 仓储及数据库迁移
```

订阅服务负责来源录入、OPML 导入、修改、启停、数据获取、条目管理与查询。调度、重试和任务执行记录由后续运行管理模块负责。

订阅服务已实现领域方法、SQL 仓储、工作单元、独立数据库迁移，以及订阅源管理应用层和 HTTP API，并配有自动化测试。
已支持 OPML 批量导入，已有来源跳过不覆盖。网络采集、事件发布和 Compose 部署尚未实现，不沿用旧部署命令。

- [项目知识库](docs/README.md)
- [订阅服务](apps/subscriptions/README.md)
- [旧项目归档与恢复](docs/legacy-archive.md)

## 旧版本

旧项目完整保存在 Git 分支 `archive/pre-rebuild` 和标签 `pre-rebuild-2026-09-28`，对应提交 `8f8976384b471b349a7ea236f82c1c5b81a51cb6`。

订阅服务功能分支为 `feature/subscription-service`，从 `codex/rebuild` 创建。归档分支和标签目前仅保留在本地。

本地环境文件不纳入版本控制。重构不操作已有数据库、Docker 容器或数据卷。
