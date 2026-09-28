"""领域对象与数据库模型显式转换，重建时保留 ID、时间及版本。"""

import hashlib

from subscription_service.domain.aggregates.subscription import Subscription
from subscription_service.domain.aggregates.subscription_item import SubscriptionItem
from subscription_service.domain.entities.item_revision import ItemRevision
from subscription_service.domain.value_objects.feed_address import FeedAddress
from subscription_service.domain.value_objects.fetch_checkpoint import FetchCheckpoint
from subscription_service.domain.value_objects.item_identity import ItemIdentity
from subscription_service.domain.value_objects.item_metadata import ItemMetadata
from subscription_service.infrastructure.persistence.models import (
    ItemRevisionModel,
    SubscriptionItemModel,
    SubscriptionModel,
)


def digest(value: str) -> str:
    """固定长度索引键；查找后仍核对原值，哈希碰撞不能返回错误对象。"""
    return hashlib.sha256(value.encode()).hexdigest()


def subscription_values(value: Subscription) -> dict:
    return dict(
        id=value.id,
        name=value.name,
        feed_address=value.feed_address.value,
        address_digest=digest(value.feed_address.value),
        categories=list(value.categories),
        enabled=value.enabled,
        configuration_version=value.configuration_version,
        address_version=value.address_version,
        etag=value.fetch_checkpoint.etag,
        last_modified=value.fetch_checkpoint.last_modified,
        last_successful_fetch_at=value.fetch_checkpoint.last_successful_fetch_at,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


def to_subscription(row: SubscriptionModel) -> Subscription:
    return Subscription(
        id=row.id,
        name=row.name,
        feed_address=FeedAddress(row.feed_address),
        categories=tuple(row.categories),
        enabled=row.enabled,
        configuration_version=row.configuration_version,
        address_version=row.address_version,
        fetch_checkpoint=FetchCheckpoint(row.etag, row.last_modified, row.last_successful_fetch_at),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def item_values(value: SubscriptionItem) -> dict:
    return dict(
        id=value.id,
        subscription_id=value.subscription_id,
        identity_kind=value.identity.kind,
        identity_value=value.identity.value,
        identity_digest=digest(value.identity.value),
        current_revision=value.current_revision,
        first_seen_at=value.first_seen_at,
        last_seen_at=value.last_seen_at,
    )


def to_item(row: SubscriptionItemModel) -> SubscriptionItem:
    return SubscriptionItem(
        row.id,
        row.subscription_id,
        ItemIdentity(row.identity_kind, row.identity_value),
        row.current_revision,
        row.first_seen_at,
        row.last_seen_at,
    )


def to_revision_model(value: ItemRevision) -> ItemRevisionModel:
    meta = value.metadata
    return ItemRevisionModel(
        item_id=value.item_id,
        revision_number=value.revision_number,
        title=meta.title,
        original_url=meta.original_url,
        summary=meta.summary,
        author=meta.author,
        published_at=meta.published_at,
        source_updated_at=meta.source_updated_at,
        observed_at=value.observed_at,
        metadata_fingerprint=meta.fingerprint(),
    )


def to_revision(row: ItemRevisionModel) -> ItemRevision:
    return ItemRevision(
        row.item_id,
        row.revision_number,
        ItemMetadata(
            row.title,
            row.original_url,
            row.summary,
            row.author,
            row.published_at,
            row.source_updated_at,
        ),
        row.observed_at,
    )
