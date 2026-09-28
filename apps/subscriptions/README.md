# 订阅服务

状态：目录骨架，尚未实现运行入口、业务代码或数据库迁移。

订阅服务负责订阅源的手动录入、OPML 批量导入、修改、启用和关闭，以及来源数据的获取、条目去重、修订和查询。运行调度、任务重试与执行记录由运行管理负责。

## 目录约定

- `docs/`：本服务的上下文、领域模型、业务规则、事件、接口及运维文档。
- `src/subscription_service/domain/`：聚合、实体、值对象、领域服务、领域事件和仓储接口。
- `src/subscription_service/application/`：应用用例、DTO、端口与事务协调。
- `src/subscription_service/infrastructure/`：数据库、Feed、RSSHub 和 OPML 等适配器。
- `src/subscription_service/interfaces/http/`：HTTP 接口与协议模型。
- `src/subscription_service/bootstrap/`：启动入口和依赖组装。
- `tests/`：服务测试。
- `migrations/`：本服务拥有的数据库迁移。

空目录通过 `.gitkeep` 纳入版本控制。后续添加实际文件时移除对应占位文件。

依赖配置 `pyproject.toml`、容器定义 `Dockerfile` 和启动命令在运行骨架实现时添加，不提供空的可执行配置。

现有应用尚未迁移或归档。本目录不导入旧应用的内部代码。
