import uuid
from dataclasses import dataclass
from datetime import datetime

from zeromind.ingestion.domain import (
    ContentReference,
    FeedEntry,
    ReferenceEvent,
    ReferenceRevision,
    derive_entry_identity,
    metadata_fingerprint,
    normalized_entry_url,
)
from zeromind.ingestion.repository import ReferenceRepository


@dataclass(frozen=True, slots=True)
class IngestionResult:
    discovered: int
    updated: int
    unchanged: int
    events: tuple[ReferenceEvent, ...]


class IngestionService:
    def __init__(self, repository: ReferenceRepository) -> None:
        self._repository = repository

    async def ingest(
        self,
        *,
        subscription_id: uuid.UUID,
        entries: tuple[FeedEntry, ...],
        fetched_at: datetime,
        window_start: datetime | None = None,
    ) -> IngestionResult:
        del window_start  # New stable identities are accepted even outside the overlap.
        discovered = 0
        updated = 0
        unchanged = 0
        events: list[ReferenceEvent] = []

        for entry in entries:
            identity = derive_entry_identity(subscription_id, entry)
            reference = await self._repository.find_by_identity(
                subscription_id,
                identity,
            )
            if reference is None:
                reference = ContentReference(
                    id=uuid.uuid4(),
                    subscription_id=subscription_id,
                    identity_key=identity,
                    original_url=normalized_entry_url(entry.url) or entry.url,
                    current_revision=1,
                    first_seen_at=fetched_at,
                    last_seen_at=fetched_at,
                )
                revision = ReferenceRevision.from_entry(
                    reference_id=reference.id,
                    number=1,
                    entry=entry,
                    observed_at=fetched_at,
                )
                await self._repository.add_reference(reference, revision)
                discovered += 1
                events.append(
                    ReferenceEvent(
                        event_type="reference.discovered",
                        reference_id=reference.id,
                        revision=1,
                        idempotency_key=f"reference.discovered:{reference.id}:1",
                    )
                )
                continue

            reference.last_seen_at = fetched_at
            current = await self._repository.get_current_revision(reference.id)
            if current.fingerprint == metadata_fingerprint(entry):
                unchanged += 1
                continue

            reference.current_revision += 1
            revision = ReferenceRevision.from_entry(
                reference_id=reference.id,
                number=reference.current_revision,
                entry=entry,
                observed_at=fetched_at,
            )
            await self._repository.add_revision(reference, revision)
            updated += 1
            events.append(
                ReferenceEvent(
                    event_type="reference.updated",
                    reference_id=reference.id,
                    revision=revision.number,
                    idempotency_key=(
                        f"reference.updated:{reference.id}:{revision.number}"
                    ),
                )
            )

        return IngestionResult(
            discovered=discovered,
            updated=updated,
            unchanged=unchanged,
            events=tuple(events),
        )

