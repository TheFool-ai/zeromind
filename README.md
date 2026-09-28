# ZeroMind

ZeroMind 正在按业务领域重新设计。本分支从订阅服务开始逐步重建。

## 当前结构

```text
docs/                    # 项目整体架构、服务边界和归档说明
apps/
  subscriptions/         # 订阅微服务目录骨架
```

订阅服务负责来源录入、OPML 导入、修改、启停、数据获取、条目管理与查询。调度、重试和任务执行记录由后续运行管理模块负责。

目前只有目录和设计约定，尚无可运行的应用、依赖配置、数据库迁移或 Compose 部署。后续逐步实现，不沿用旧部署命令。

- [项目设计约定](docs/README.md)
- [订阅服务](apps/subscriptions/README.md)
- [旧项目归档与恢复](docs/legacy-archive.md)

## 旧版本

旧项目完整保存在 Git 分支 `archive/pre-rebuild` 和标签 `pre-rebuild-2026-09-28`，对应提交 `8f8976384b471b349a7ea236f82c1c5b81a51cb6`。

当前重构分支为 `codex/rebuild`。归档引用目前在本地创建，尚未推送到远程。

本地环境文件不纳入版本控制。重构不操作已有数据库、Docker 容器或数据卷。
