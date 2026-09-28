"""使用真实 SQL 数据库验证事务、唯一性、修订及并发，禁止连接业务库。

默认临时 SQLite。TEST_SUBSCRIPTIONS_DATABASE_URL 只能指向可清空的独立测试库。
"""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from subscription_service.domain.aggregates.subscription import Subscription
from subscription_service.domain.aggregates.subscription_item import SubscriptionItem
from subscription_service.domain.value_objects.feed_address import FeedAddress
from subscription_service.domain.value_objects.item_identity import ItemIdentity
from subscription_service.domain.value_objects.item_metadata import ItemMetadata

NOW = datetime(2026, 9, 28, tzinfo=UTC)
SERVICE = Path(__file__).resolve().parents[1]


def migrate(connection, target="head", downgrade=False):
    config = Config(str(SERVICE / "alembic.ini"))
    config.attributes["connection"] = connection
    (command.downgrade if downgrade else command.upgrade)(config, target)


@pytest.fixture
async def database(tmp_path):
    from subscription_service.infrastructure.persistence.database import create_database

    url = os.environ.get(
        "TEST_SUBSCRIPTIONS_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    )
    # 显式限制外部数据库名称，避免误把真实数据用于迁移升降级测试。
    from sqlalchemy.engine import make_url

    if not url.startswith("sqlite") and not make_url(url).database.startswith("test_"):
        raise ValueError("测试数据库名称必须以 test_ 开头")
    db = create_database(url)
    async with db.engine.begin() as connection:
        await connection.run_sync(migrate)
    try:
        yield db
    finally:
        async with db.engine.begin() as connection:
            await connection.run_sync(lambda conn: migrate(conn, "base", downgrade=True))
        await db.dispose()


def source(address="https://example.com/feed"):
    return Subscription.create(name="新闻", feed_address=FeedAddress(address), now=NOW)


def meta(title="第一篇"):
    return ItemMetadata(title, "https://example.com/article", "摘要", None, NOW, None)


async def seed(db):
    sub = source()
    item, revision = SubscriptionItem.discover(
        subscription_id=sub.id,
        identity=ItemIdentity("guid", "entry-1"),
        metadata=meta(),
        observed_at=NOW,
    )
    async with db.unit_of_work() as uow:
        await uow.subscriptions.add(sub)
        await uow.items.add(item, revision)
        await uow.commit()
    return sub, item


async def test_subscription_roundtrip_and_explicit_save(database):
    sub = source()
    async with database.unit_of_work() as uow:
        await uow.subscriptions.add(sub)
        await uow.commit()
    async with database.unit_of_work() as uow:
        loaded = await uow.subscriptions.find_by_address(
            FeedAddress("HTTPS://EXAMPLE.com:443/feed")
        )
        assert loaded.id == sub.id and loaded.created_at == NOW
        loaded.disable(now=NOW)
        await uow.commit()  # 不 save，不持久化领域对象的内存变化。
    async with database.unit_of_work() as uow:
        loaded = await uow.subscriptions.get(sub.id)
        assert loaded.enabled is True
        loaded.disable(now=NOW + timedelta(seconds=1))
        await uow.subscriptions.save(loaded)
        await uow.commit()
    async with database.unit_of_work() as uow:
        rows = await uow.subscriptions.list(enabled=False)
        assert len(rows) == 1 and rows[0].configuration_version == 2
        assert await uow.subscriptions.get(uuid4()) is None


async def test_missing_commit_and_exception_rollback_all_changes(database):
    sub = source()
    async with database.unit_of_work() as uow:
        await uow.subscriptions.add(sub)
    async with database.unit_of_work() as uow:
        assert await uow.subscriptions.get(sub.id) is None
    with pytest.raises(RuntimeError):
        async with database.unit_of_work() as uow:
            await uow.subscriptions.add(sub)
            raise RuntimeError("simulate failure")
    async with database.unit_of_work() as uow:
        assert await uow.subscriptions.list() == ()


async def test_duplicate_address_has_specific_error(database):
    from subscription_service.domain.errors import DuplicateSubscriptionError

    async with database.unit_of_work() as uow:
        await uow.subscriptions.add(source())
        await uow.commit()
    with pytest.raises(DuplicateSubscriptionError):
        async with database.unit_of_work() as uow:
            await uow.subscriptions.add(source("HTTPS://EXAMPLE.COM:443/feed#x"))
            await uow.commit()


async def test_item_roundtrip_revisions_and_unchanged_observation(database):
    sub, item = await seed(database)
    async with database.unit_of_work() as uow:
        loaded = await uow.items.find_by_identity(sub.id, ItemIdentity("guid", "entry-1"))
        first = await uow.items.get_revision(loaded.id, 1)
        assert first.metadata.title == "第一篇" and first.observed_at == NOW
        assert (
            loaded.observe(
                current_revision=first, metadata=meta(), observed_at=NOW + timedelta(minutes=1)
            )
            is None
        )
        await uow.items.save(loaded)
        await uow.commit()
    async with database.unit_of_work() as uow:
        loaded = await uow.items.get(item.id)
        assert loaded.last_seen_at == NOW + timedelta(minutes=1)
        first = await uow.items.get_revision(item.id, 1)
        new = loaded.observe(
            current_revision=first, metadata=meta("新标题"), observed_at=NOW + timedelta(minutes=2)
        )
        await uow.items.save(loaded, new)
        await uow.commit()
    async with database.unit_of_work() as uow:
        revisions = await uow.items.list_revisions(item.id)
        assert [r.metadata.title for r in revisions] == ["第一篇", "新标题"]
        assert (await uow.items.list_by_subscription(sub.id))[0].current_revision == 2
        assert await uow.items.get_revision(item.id, 99) is None


async def test_duplicate_item_and_foreign_key_are_not_confused(database):
    from subscription_service.domain.errors import DuplicateItemError

    sub, _ = await seed(database)
    duplicate, rev = SubscriptionItem.discover(
        subscription_id=sub.id,
        identity=ItemIdentity("guid", "entry-1"),
        metadata=meta(),
        observed_at=NOW,
    )
    with pytest.raises(DuplicateItemError):
        async with database.unit_of_work() as uow:
            await uow.items.add(duplicate, rev)
    orphan, rev = SubscriptionItem.discover(
        subscription_id=uuid4(),
        identity=ItemIdentity("guid", "orphan"),
        metadata=meta(),
        observed_at=NOW,
    )
    with pytest.raises(IntegrityError):
        async with database.unit_of_work() as uow:
            await uow.items.add(orphan, rev)


async def test_stale_source_write_cannot_reenable_disabled_source(database):
    from subscription_service.domain.errors import ConcurrentModificationError

    sub, _ = await seed(database)
    async with database.unit_of_work() as first, database.unit_of_work() as second:
        stale = await first.subscriptions.get(sub.id)
        fresh = await second.subscriptions.get(sub.id)
        fresh.disable(now=NOW)
        await second.subscriptions.save(fresh)
        await second.commit()
        stale.record_fetch_success(etag="old", last_modified=None, completed_at=NOW)
        with pytest.raises(ConcurrentModificationError):
            await first.subscriptions.save(stale)
    async with database.unit_of_work() as uow:
        loaded = await uow.subscriptions.get(sub.id)
        assert loaded.enabled is False and loaded.fetch_checkpoint.etag is None


async def test_conflicting_item_revision_rolls_back_entire_transaction(database):
    from subscription_service.domain.errors import ConcurrentModificationError

    _, item = await seed(database)
    async with database.unit_of_work() as first, database.unit_of_work() as second:
        left = await first.items.get(item.id)
        right = await second.items.get(item.id)
        old_left = await first.items.get_revision(item.id, 1)
        old_right = await second.items.get_revision(item.id, 1)
        right_new = right.observe(
            current_revision=old_right, metadata=meta("赢家"), observed_at=NOW
        )
        await second.items.save(right, right_new)
        await second.commit()
        left_new = left.observe(current_revision=old_left, metadata=meta("旧写入"), observed_at=NOW)
        with pytest.raises(ConcurrentModificationError):
            await first.items.save(left, left_new)
    async with database.unit_of_work() as uow:
        revisions = await uow.items.list_revisions(item.id)
        assert len(revisions) == 2 and revisions[-1].metadata.title == "赢家"


async def test_new_revision_must_accompany_version_change(database):
    _, item = await seed(database)
    async with database.unit_of_work() as uow:
        loaded = await uow.items.get(item.id)
        first = await uow.items.get_revision(item.id, 1)
        loaded.observe(current_revision=first, metadata=meta("changed"), observed_at=NOW)
        with pytest.raises(ValueError):
            await uow.items.save(loaded)


async def test_migration_matches_models_and_can_roundtrip(database):
    from subscription_service.infrastructure.persistence.models import Base

    async with database.engine.begin() as connection:
        diffs = await connection.run_sync(
            lambda conn: compare_metadata(MigrationContext.configure(conn), Base.metadata)
        )
        assert diffs == []
        await connection.run_sync(lambda conn: migrate(conn, "base", downgrade=True))
        names = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
        assert "subscriptions" not in names and "subscription_items" not in names
        await connection.run_sync(migrate)
        names = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
        assert {"subscriptions", "subscription_items", "item_revisions"} <= set(names)


async def test_database_constraints_reject_invalid_revision(database):
    _, item = await seed(database)
    with pytest.raises(IntegrityError):
        async with database.engine.begin() as connection:
            await connection.execute(text("UPDATE subscription_items SET current_revision = 0"))


async def test_address_change_roundtrip_and_duplicate_update_rollback(database):
    from subscription_service.domain.errors import DuplicateSubscriptionError

    first, second = source(), source("https://second.example/feed")
    async with database.unit_of_work() as uow:
        await uow.subscriptions.add(first)
        await uow.subscriptions.add(second)
        await uow.commit()
    with pytest.raises(DuplicateSubscriptionError):
        async with database.unit_of_work() as uow:
            changed = await uow.subscriptions.get(first.id)
            changed.change_address(feed_address=second.feed_address, now=NOW)
            await uow.subscriptions.save(changed)
    async with database.unit_of_work() as uow:
        changed = await uow.subscriptions.get(first.id)
        assert changed.address_version == 1 and changed.feed_address == first.feed_address
        changed.change_address(feed_address=FeedAddress("https://third.example/feed"), now=NOW)
        changed.record_fetch_success(
            etag='"version-2"',
            last_modified="Mon, 28 Sep 2026 00:00:00 GMT",
            completed_at=NOW,
            expected_address_version=2,
        )
        await uow.subscriptions.save(changed)
        await uow.commit()
    async with database.unit_of_work() as uow:
        loaded = await uow.subscriptions.get(first.id)
        assert loaded.address_version == 2
        assert loaded.fetch_checkpoint.etag == '"version-2"'
        assert loaded.fetch_checkpoint.last_successful_fetch_at == NOW


async def test_item_and_revision_rollback_together(database):
    sub, _ = await seed(database)
    item, revision = SubscriptionItem.discover(
        subscription_id=sub.id,
        identity=ItemIdentity("guid", "rollback"),
        metadata=meta(),
        observed_at=NOW,
    )
    async with database.unit_of_work() as uow:
        await uow.items.add(item, revision)
        # 未 commit，条目和修订必须同时回滚。
    async with database.unit_of_work() as uow:
        assert await uow.items.get(item.id) is None
        assert await uow.items.get_revision(item.id, 1) is None


async def test_pagination_and_cross_source_identity_scope(database):
    first, second = source(), source("https://second.example/feed")
    # 超长 GUID 的数据库索引必须使用固定长度键，不能触发 PostgreSQL 索引长度限制。
    identity = ItemIdentity("guid", "内容" * 3000)
    async with database.unit_of_work() as uow:
        for sub in (first, second):
            await uow.subscriptions.add(sub)
            item, rev = SubscriptionItem.discover(
                subscription_id=sub.id, identity=identity, metadata=meta(), observed_at=NOW
            )
            await uow.items.add(item, rev)
        await uow.commit()
    async with database.unit_of_work() as uow:
        page1 = await uow.subscriptions.list(limit=1)
        page2 = await uow.subscriptions.list(limit=1, offset=1)
        assert {page1[0].id, page2[0].id} == {first.id, second.id}
        assert (await uow.items.find_by_identity(first.id, identity)).subscription_id == first.id
        assert (await uow.items.find_by_identity(second.id, identity)).subscription_id == second.id
        with pytest.raises(ValueError):
            await uow.subscriptions.list(limit=0)


async def test_repository_rejects_detached_entities_and_revision_overwrite(database):
    sub, item = await seed(database)
    async with database.unit_of_work() as uow:
        with pytest.raises(ValueError):
            await uow.subscriptions.save(sub)
        loaded = await uow.items.get(item.id)
        revision = await uow.items.get_revision(item.id, 1)
        with pytest.raises(ValueError):
            await uow.items.save(loaded, revision)
