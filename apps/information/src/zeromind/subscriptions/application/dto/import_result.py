from dataclasses import dataclass

from zeromind.subscriptions.application.dto.import_item_result import ImportItemResult


@dataclass(frozen=True, slots=True)
class ImportResult:
    created: int
    duplicates: int
    items: tuple[ImportItemResult, ...]
