# 订阅服务

状态：已实现领域规则、SQLAlchemy 仓储、事务工作单元、初始数据库迁移，以及订阅源管理应用层和 HTTP 入口。尚无采集或任务运行入口。

完整导航见 [订阅知识库](docs/README.md)，包括领域边界、功能、实现、ER 图、时序图和测试用例。
领域对象与方法说明见 [领域模型](docs/domain/model.md)，表结构和使用方式见 [持久化说明](docs/implementation/persistence.md)。

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

依赖通过 `pyproject.toml` 和 `uv.lock` 管理；Docker 部署后续按需添加。

## 本地启动

需要 Python 3.12+ 和 uv。以下使用服务目录下的独立 SQLite 数据库：

```bash
cd apps/subscriptions
uv sync --locked
export SUBSCRIPTIONS_DATABASE_URL=sqlite+aiosqlite:///subscriptions.db
uv run alembic upgrade head
uv run uvicorn subscription_service.bootstrap.app:create_app --factory --host 127.0.0.1 --port 8000
```

交互文档：`http://127.0.0.1:8000/api/docs`。接口和错误约定见 [HTTP API](docs/implementation/api.md)。
启动不自动迁移、不读取根目录 `.env`。当前未接入鉴权，请仅本地运行或置于有鉴权的可信网关后，不直接暴露公网。

## 本地验证

需要 Python 3.12+ 和 uv。在服务目录执行：

```bash
cd apps/subscriptions
uv sync --locked
uv run pytest
uv run ruff check src tests migrations
```

测试默认使用临时 SQLite，不读取根目录 `.env` 或连接旧项目数据库。
PostgreSQL 验证方式见持久化说明。

## 当前能力边界

已实现来源创建和修改、幂等启停、地址规范化、检查点更新、条目观察和不可变修订。
仓储支持事务、唯一约束、外键、乐观锁、分页及历史版本读取。
HTTP 支持手动创建、列表/详情、部分修改、启用和关闭；应用层协调每个用例的事务。
OPML 支持同步导入、已有来源跳过和逐项结果，见 [导入说明](docs/features/opml-import.md)。
事件类/Outbox、身份推导策略、Feed 适配器和运行调度仍待后续实现。

旧应用已归档到 Git 分支 `archive/pre-rebuild` 和标签 `pre-rebuild-2026-09-28`。本服务按新的业务边界逐步实现，不导入旧应用的内部代码。
