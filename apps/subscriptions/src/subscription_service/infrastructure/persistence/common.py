"""仓储共用的分页校验和数据库错误翻译。"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from subscription_service.domain.errors import (
    ConcurrentModificationError,
    DuplicateItemError,
    DuplicateSubscriptionError,
)


def validate_page(limit: int, offset: int) -> None:
    if not 1 <= limit <= 1000 or offset < 0:
        raise ValueError("limit 必须为 1～1000，offset 必须非负")


async def flush(session: AsyncSession) -> None:
    """只翻译已知唯一约束；外键、非空、其他错误保留原异常，不能误报重复。"""
    try:
        await session.flush()
    except StaleDataError as exc:
        raise ConcurrentModificationError("数据已被其他事务修改，请重新加载") from exc
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        message = str(exc.orig)
        if constraint == "uq_subscription_address" or message == (
            "UNIQUE constraint failed: subscriptions.address_digest"
        ):
            raise DuplicateSubscriptionError("订阅地址已存在") from exc
        if constraint == "uq_item_identity" or message == (
            "UNIQUE constraint failed: subscription_items.subscription_id, "
            "subscription_items.identity_kind, subscription_items.identity_digest"
        ):
            raise DuplicateItemError("同一来源内的条目身份已存在") from exc
        raise
