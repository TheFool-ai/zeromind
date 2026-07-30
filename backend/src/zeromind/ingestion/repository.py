import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from zeromind.ingestion.domain import ContentReference, ReferenceRevision
from zeromind.ingestion.models import ContentReferenceModel, ReferenceRevisionModel
from zeromind.shared.models import OutboxEventModel


class ReferenceRepository(Protocol):
    async def find_by_identity(
        self,
        subscription_id: uuid.UUID,
        identity_key: str,
    ) -> ContentReference | None: ...

    async def add_reference(
        self,
        reference: ContentReference,
        revision: ReferenceRevision,
    ) -> None: ...

    async def add_revision(
        self,
        reference: ContentReference,
        revision: ReferenceRevision,
    ) -> None: ...

    async def get_current_revision(
        self,
        reference_id: uuid.UUID,
    ) -> ReferenceRevision: ...

    async def get_revision(
        self,
        reference_id: uuid.UUID,
        number: int,
    ) -> ReferenceRevision: ...

    async def get_reference(
        self,
        reference_id: uuid.UUID,
    ) -> ContentReference | None: ...

    async def list_references(self) -> tuple[ContentReference, ...]: ...

    async def list_revisions(
        self,
        reference_id: uuid.UUID,
    ) -> tuple[ReferenceRevision, ...]: ...


class InMemoryReferenceRepository:
    def __init__(self) -> None:
        self._references: dict[uuid.UUID, ContentReference] = {}
        self._identities: dict[tuple[uuid.UUID, str], uuid.UUID] = {}
        self._revisions: dict[uuid.UUID, list[ReferenceRevision]] = defaultdict(list)

    async def find_by_identity(
        self,
        subscription_id: uuid.UUID,
        identity_key: str,
    ) -> ContentReference | None:
        reference_id = self._identities.get((subscription_id, identity_key))
        return self._references.get(reference_id) if reference_id else None

    async def add_reference(
        self,
        reference: ContentReference,
        revision: ReferenceRevision,
    ) -> None:
        identity = (reference.subscription_id, reference.identity_key)
        if identity in self._identities:
            raise ValueError("duplicate reference identity")
        self._references[reference.id] = reference
        self._identities[identity] = reference.id
        self._revisions[reference.id].append(revision)

    async def add_revision(
        self,
        reference: ContentReference,
        revision: ReferenceRevision,
    ) -> None:
        self._references[reference.id] = reference
        existing = self._revisions[reference.id]
        if any(item.fingerprint == revision.fingerprint for item in existing):
            return
        existing.append(revision)

    async def get_current_revision(self, reference_id: uuid.UUID) -> ReferenceRevision:
        revisions = self._revisions[reference_id]
        return max(revisions, key=lambda item: item.number)

    async def get_revision(
        self,
        reference_id: uuid.UUID,
        number: int,
    ) -> ReferenceRevision:
        for revision in self._revisions[reference_id]:
            if revision.number == number:
                return revision
        raise KeyError((reference_id, number))

    async def get_reference(
        self,
        reference_id: uuid.UUID,
    ) -> ContentReference | None:
        return self._references.get(reference_id)

    async def list_references(self) -> tuple[ContentReference, ...]:
        return tuple(self._references.values())

    async def list_revisions(
        self,
        reference_id: uuid.UUID,
    ) -> tuple[ReferenceRevision, ...]:
        return tuple(self._revisions[reference_id])


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _required_utc(value: datetime) -> datetime:
    normalized = _as_utc(value)
    if normalized is None:  # pragma: no cover - protected by database constraints
        raise ValueError("required timestamp is missing")
    return normalized


def _reference_to_domain(model: ContentReferenceModel) -> ContentReference:
    return ContentReference(
        id=model.id,
        subscription_id=model.subscription_id,
        identity_key=model.identity_key,
        original_url=model.original_url,
        current_revision=model.current_revision,
        first_seen_at=_required_utc(model.first_seen_at),
        last_seen_at=_required_utc(model.last_seen_at),
    )


def _revision_to_domain(model: ReferenceRevisionModel) -> ReferenceRevision:
    return ReferenceRevision(
        id=model.id,
        reference_id=model.reference_id,
        number=model.number,
        fingerprint=model.fingerprint,
        url=model.url,
        title=model.title,
        summary=model.summary,
        author=model.author,
        published_at=_as_utc(model.published_at),
        updated_at=_as_utc(model.updated_at),
        observed_at=_required_utc(model.observed_at),
    )


def _reference_model(reference: ContentReference) -> ContentReferenceModel:
    return ContentReferenceModel(
        id=reference.id,
        subscription_id=reference.subscription_id,
        identity_key=reference.identity_key,
        original_url=reference.original_url,
        current_revision=reference.current_revision,
        first_seen_at=reference.first_seen_at,
        last_seen_at=reference.last_seen_at,
    )


def _revision_model(revision: ReferenceRevision) -> ReferenceRevisionModel:
    return ReferenceRevisionModel(
        id=revision.id,
        reference_id=revision.reference_id,
        number=revision.number,
        fingerprint=revision.fingerprint,
        url=revision.url,
        title=revision.title,
        summary=revision.summary,
        author=revision.author,
        published_at=revision.published_at,
        updated_at=revision.updated_at,
        observed_at=revision.observed_at,
    )


def _outbox_model(
    *,
    event_type: str,
    reference: ContentReference,
    revision: ReferenceRevision,
) -> OutboxEventModel:
    return OutboxEventModel(
        event_type=event_type,
        aggregate_type="reference",
        aggregate_id=str(reference.id),
        payload={
            "reference_id": str(reference.id),
            "revision": revision.number,
        },
        idempotency_key=f"{event_type}:{reference.id}:{revision.number}",
        status="pending",
        attempts=0,
        occurred_at=revision.observed_at,
        available_at=revision.observed_at,
    )


class SqlAlchemyReferenceRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def find_by_identity(
        self,
        subscription_id: uuid.UUID,
        identity_key: str,
    ) -> ContentReference | None:
        async with self._sessions() as session:
            model = await session.scalar(
                select(ContentReferenceModel).where(
                    ContentReferenceModel.subscription_id == subscription_id,
                    ContentReferenceModel.identity_key == identity_key,
                )
            )
            return _reference_to_domain(model) if model else None

    async def add_reference(
        self,
        reference: ContentReference,
        revision: ReferenceRevision,
    ) -> None:
        async with self._sessions() as session, session.begin():
            session.add(_reference_model(reference))
            session.add(_revision_model(revision))
            session.add(
                _outbox_model(
                    event_type="reference.discovered",
                    reference=reference,
                    revision=revision,
                )
            )

    async def add_revision(
        self,
        reference: ContentReference,
        revision: ReferenceRevision,
    ) -> None:
        async with self._sessions() as session, session.begin():
            model = await session.get(ContentReferenceModel, reference.id)
            if model is None:
                raise KeyError(reference.id)
            model.current_revision = reference.current_revision
            model.original_url = reference.original_url
            model.last_seen_at = reference.last_seen_at
            session.add(_revision_model(revision))
            session.add(
                _outbox_model(
                    event_type="reference.updated",
                    reference=reference,
                    revision=revision,
                )
            )

    async def get_current_revision(self, reference_id: uuid.UUID) -> ReferenceRevision:
        async with self._sessions() as session:
            model = await session.scalar(
                select(ReferenceRevisionModel)
                .where(ReferenceRevisionModel.reference_id == reference_id)
                .order_by(ReferenceRevisionModel.number.desc())
                .limit(1)
            )
            if model is None:
                raise KeyError(reference_id)
            return _revision_to_domain(model)

    async def get_revision(
        self,
        reference_id: uuid.UUID,
        number: int,
    ) -> ReferenceRevision:
        async with self._sessions() as session:
            model = await session.scalar(
                select(ReferenceRevisionModel).where(
                    ReferenceRevisionModel.reference_id == reference_id,
                    ReferenceRevisionModel.number == number,
                )
            )
            if model is None:
                raise KeyError((reference_id, number))
            return _revision_to_domain(model)

    async def get_reference(
        self,
        reference_id: uuid.UUID,
    ) -> ContentReference | None:
        async with self._sessions() as session:
            model = await session.get(ContentReferenceModel, reference_id)
            return _reference_to_domain(model) if model else None

    async def list_references(self) -> tuple[ContentReference, ...]:
        async with self._sessions() as session:
            models = await session.scalars(
                select(ContentReferenceModel).order_by(
                    ContentReferenceModel.first_seen_at.desc()
                )
            )
            return tuple(_reference_to_domain(model) for model in models)

    async def list_revisions(
        self,
        reference_id: uuid.UUID,
    ) -> tuple[ReferenceRevision, ...]:
        async with self._sessions() as session:
            models = await session.scalars(
                select(ReferenceRevisionModel)
                .where(ReferenceRevisionModel.reference_id == reference_id)
                .order_by(ReferenceRevisionModel.number)
            )
            return tuple(_revision_to_domain(model) for model in models)
