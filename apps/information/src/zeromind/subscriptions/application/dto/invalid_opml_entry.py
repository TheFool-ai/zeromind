from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InvalidOpmlEntry:
    title: str
    feed_url: str
    reason: str
