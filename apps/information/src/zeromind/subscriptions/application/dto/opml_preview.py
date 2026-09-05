from dataclasses import dataclass

from zeromind.subscriptions.application.dto.invalid_opml_entry import InvalidOpmlEntry
from zeromind.subscriptions.application.dto.opml_entry import OpmlEntry


@dataclass(frozen=True, slots=True)
class OpmlPreview:
    title: str | None
    entries: tuple[OpmlEntry, ...]
    invalid_entries: tuple[InvalidOpmlEntry, ...]
    duplicate_count: int
