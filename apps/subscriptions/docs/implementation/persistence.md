# 库表、仓储和事务

状态：已实现并配有 SQLite / PostgreSQL 共用的仓储测试。

关联：[物理 ER 图](er-diagram.md)、[领域模型](../domain/model.md)、[测试说明](../testing/README.md)。

## 数据库选择

使用 SQLAlchemy 2 异步接口和 Alembic。支持 SQLite + aiosqlite（本地/测试）及 PostgreSQL + psycopg（独立服务部署）。连接 URL 必须显式传入，不加载根目录 `.env`。创建连接不会自动建表。

## subscriptions：订阅源

| 字段 | 用途 |
| --- | --- |
| id | UUID 主键，来源身份 |
| name | 1～300 字符的展示名称 |
| feed_address | 规范化后的来源地址，最长 2048 字符 |
| address_digest | 地址 SHA-256 唯一索引，避免长 Unicode 地址超出索引限制 |
| categories | 来源分类 JSON 数组，不是文章分类 |
| enabled | 是否允许后续获取 |
| configuration_version | 名称、分类、地址或启停变化时递增 |
| address_version | 仅地址变化时递增，包括地址改走又改回 |
| etag / last_modified | 下次条件请求使用的原始头信息 |
| last_successful_fetch_at | 最近完整成功处理时间 |
| created_at / updated_at | 来源创建和配置修改时间，UTC |
| row_version | ORM 内部乐观锁版本，任意已保存的行变化都会推进 |

获取检查点作为聚合值对象，物理上平铺在来源表中，无需独立表。没有 site_url、调度计划或执行记录列。

## subscription_items：来源条目

| 字段 | 用途 |
| --- | --- |
| id | 系统条目 UUID 主键 |
| subscription_id | 来源外键，限制删除有条目的来源 |
| identity_kind / identity_value | GUID、URL 或哈希身份，保留原值 |
| identity_digest | 身份原值的 SHA-256，用于固定长度索引 |
| current_revision | 当前修订号，必须大于等于 1 |
| first_seen_at / last_seen_at | 首次和最近实际观察时间，UTC |
| row_version | 条目更新的乐观锁版本 |

唯一键为 (subscription_id, identity_kind, identity_digest)。不同来源允许相同身份。哈希查询同时核对原值，不会把碰撞值返回成另一个对象；极低概率的碰撞仍会导致唯一冲突，而不是覆盖数据。

## item_revisions：不可变修订

| 字段 | 用途 |
| --- | --- |
| item_id / revision_number | 复合主键，条目外键与连续修订号 |
| title / original_url / summary / author | Feed 元数据，不含 AI 结果 |
| published_at / source_updated_at | 来源发布时间和更新时间，可空 |
| observed_at | 系统观察到本版本的时间 |
| metadata_fingerprint | 规范化元数据指纹，不包含本地观察时间 |

仓储只提供追加修订和查询，不提供覆盖历史的接口。数据库约束保证外键与版本为正；版本连续性和“条目版本推进必须伴随修订写入”由仓储保证。数据库管理员直接执行 SQL 不受该应用层约束保护。

## 仓储接口

- SubscriptionRepository：add、get、find_by_address、list、save。
- SubscriptionItemRepository：add、get、find_by_identity、save、get_revision、list_revisions、list_by_subscription。
- get / find 不存在时返回 None；列表返回元组，按明确字段排序。
- limit 为 1～1000，offset 非负；第一版使用 offset 分页。
- save 只接受当前工作单元加载或添加的同一实例；不能拿其他事务的对象直接覆盖。
- 读取对象后只修改字段但不 save，不会自动持久化。
- 修订和领域对象用显式 mapper 转换，数据库读取不调用 create/discover。

## 事务使用

```python
from datetime import UTC, datetime

from subscription_service.domain.aggregates.subscription import Subscription
from subscription_service.domain.value_objects.feed_address import FeedAddress
from subscription_service.infrastructure.persistence.database import create_database


async def create_source(database_url: str):
    database = create_database(database_url)
    try:
        async with database.unit_of_work() as uow:
            source = Subscription.create(
                name="技术资讯",
                feed_address=FeedAddress.parse("https://example.com/feed"),
                now=datetime.now(UTC),
            )
            await uow.subscriptions.add(source)
            await uow.commit()
            return source.id
    finally:
        await database.dispose()
```

工作单元内的两个仓储共享事务。add/save 会 flush 校验约束，但不提交；只有显式 commit 才提交。退出时未提交的修改回滚，异常继续抛出。每个用例使用一个新工作单元，提交后结束使用。

条目新增必须传入版本 1；更新条目版本必须同时传入新修订，版本必须连续。没有新修订也需 save，以持久化 last_seen_at。

唯一地址冲突抛出 DuplicateSubscriptionError，同来源身份冲突抛出 DuplicateItemError，过期写入抛出 ConcurrentModificationError。外键等其他完整性错误保留原异常，不伪装成“重复”。失败后退出工作单元；若重试，重新加载并重新执行业务判断，不能重发旧对象。

乐观锁保护“从读取到提交”期间的变化。外部网络请求跨越事务时，还应保存请求开始的 address_version，并在 record_fetch_success 中传入 expected_address_version。接收条目前同样需要应用层校验地址版本；本轮没有实现采集应用层。

## 数据库迁移

在服务目录执行。以下仅创建本地开发库：

```bash
uv sync --locked
SUBSCRIPTIONS_DATABASE_URL=sqlite+aiosqlite:///subscriptions.db uv run alembic upgrade head
uv run alembic current
```

部署时将 SUBSCRIPTIONS_DATABASE_URL 设为独立 PostgreSQL 数据库连接。不要使用旧 information 数据库；本迁移不搬迁归档数据。

首个迁移为 0001_subscription_domain，建立三张表、外键、唯一索引及版本检查。生产运行不调用 metadata.create_all。降级到 base 会删除这三张表及数据，仅应在明确要销毁的数据库上执行。

## 测试

```bash
uv run pytest
uv run ruff check src tests migrations
```

默认每个仓储测试使用临时 SQLite，并实际运行 Alembic 升级/降级。若验证 PostgreSQL，将 TEST_SUBSCRIPTIONS_DATABASE_URL 指向专用且可销毁、数据库名以 test_ 开头的库，再执行相同测试。测试会删除并重建三张业务表，禁止连接业务数据库。

锁定依赖记录在 uv.lock。所有时间入库前转 UTC；SQLite 无时区返回值在适配器中恢复 UTC。

## 尚未接入

来源管理及 OPML 导入 HTTP 已实现；OPML 逐来源创建新工作单元，不新增数据表，不保证整批原子性。
领域事件、Outbox 和网络抓取尚未实现。当前工作单元保证单个本地事务的一致性，不声称已保证跨服务消息可靠交付。
