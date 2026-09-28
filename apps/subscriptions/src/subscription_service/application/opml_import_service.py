"""同步批量导入用例：先解析全文件，再逐来源事务提交；已存在只跳过。"""

from collections.abc import Callable
from datetime import UTC, datetime

from subscription_service.application.dto.opml_import import (
    ImportItemResult,
    OpmlEntry,
    OpmlImportResult,
)
from subscription_service.application.opml_errors import OpmlImportInterruptedError
from subscription_service.application.ports.opml_reader import OpmlReader
from subscription_service.application.ports.unit_of_work import UnitOfWork
from subscription_service.domain.aggregates.subscription import Subscription
from subscription_service.domain.errors import DuplicateSubscriptionError
from subscription_service.domain.value_objects.feed_address import FeedAddress


class OpmlImportService:
    """复用来源聚合规则，独立组织批量结果，不改变单条创建的重复地址 409 语义。"""

    def __init__(
        self,
        unit_of_work: Callable[[], UnitOfWork],
        reader: OpmlReader,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._reader = reader
        self._clock = clock or (lambda: datetime.now(UTC))

    async def import_document(self, content: bytes) -> OpmlImportResult:
        entries = self._reader.parse(content)  # 完整解析失败时尚未打开任何写事务。
        results: list[ImportItemResult] = []
        handled: set[str] = set()
        for entry in entries:
            try:
                address = FeedAddress.parse(entry.feed_address)
            except ValueError:
                results.append(ImportItemResult(entry.index, "failed", "invalid_address"))
                continue
            if address.value in handled:
                results.append(ImportItemResult(entry.index, "skipped", "duplicate_in_file"))
                continue
            try:
                result = await self._import_entry(entry, address)
            except DuplicateSubscriptionError:
                # 先查后插仍存在竞争窗口，以数据库唯一约束为最终保障。
                # 已在 _import_entry 的工作单元退出时回滚，不能在失败事务内继续查。
                result = ImportItemResult(entry.index, "skipped", "already_exists")
            except Exception as exc:
                # 非业务故障立即停止，不将存储故障当成逐项校验失败后继续写入。
                results.append(ImportItemResult(entry.index, "failed", "storage_error"))
                raise OpmlImportInterruptedError(
                    OpmlImportResult(len(entries), tuple(results))
                ) from exc
            results.append(result)
            if result.status != "failed":
                handled.add(address.value)
        return OpmlImportResult(len(entries), tuple(results))

    async def _import_entry(self, entry: OpmlEntry, address: FeedAddress) -> ImportItemResult:
        async with self._unit_of_work() as uow:
            existing = await uow.subscriptions.find_by_address(address)
            if existing is not None:
                # 不校验新名称或分类，不调用 save，不重新启用已有来源。
                return ImportItemResult(entry.index, "skipped", "already_exists", existing.id)
            try:
                source = Subscription.create(
                    name=entry.name or address.value[:300],
                    feed_address=address,
                    categories=entry.categories,
                    now=self._clock(),
                )
            except ValueError:
                return ImportItemResult(entry.index, "failed", "invalid_subscription")
            await uow.subscriptions.add(source)
            await uow.commit()
            return ImportItemResult(entry.index, "created", "created", source.id)
