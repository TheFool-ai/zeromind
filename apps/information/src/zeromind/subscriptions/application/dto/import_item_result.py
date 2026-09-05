from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ImportItemResult:
    feed_url: str
    status: str
    subscription_id: str | None
