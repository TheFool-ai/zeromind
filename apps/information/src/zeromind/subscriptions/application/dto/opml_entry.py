from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OpmlEntry:
    title: str
    feed_url: str
    site_url: str | None
    categories: tuple[str, ...]
