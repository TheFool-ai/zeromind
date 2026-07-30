import copy
import uuid
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from zeromind.notes.domain import Note
from zeromind.notes.models import NoteModel


class NoteRepository(Protocol):
    async def add(self, note: Note) -> None: ...

    async def get_owned(
        self,
        note_id: uuid.UUID,
        owner_subject: str,
    ) -> Note | None: ...

    async def list_owned(
        self,
        owner_subject: str,
        *,
        reference_id: uuid.UUID | None = None,
        analysis_id: uuid.UUID | None = None,
    ) -> tuple[Note, ...]: ...

    async def save(self, note: Note) -> None: ...

    async def delete(
        self,
        note_id: uuid.UUID,
        owner_subject: str,
    ) -> None: ...


class InMemoryNoteRepository:
    def __init__(self) -> None:
        self._notes: dict[uuid.UUID, Note] = {}

    @staticmethod
    def _copy(note: Note) -> Note:
        return copy.deepcopy(note)

    async def add(self, note: Note) -> None:
        if note.id in self._notes:
            raise ValueError("duplicate note")
        self._notes[note.id] = self._copy(note)

    async def get_owned(
        self,
        note_id: uuid.UUID,
        owner_subject: str,
    ) -> Note | None:
        note = self._notes.get(note_id)
        if note is None or note.owner_subject != owner_subject:
            return None
        return self._copy(note)

    async def list_owned(
        self,
        owner_subject: str,
        *,
        reference_id: uuid.UUID | None = None,
        analysis_id: uuid.UUID | None = None,
    ) -> tuple[Note, ...]:
        items = [
            note
            for note in self._notes.values()
            if note.owner_subject == owner_subject
            and (reference_id is None or note.reference_id == reference_id)
            and (analysis_id is None or note.analysis_id == analysis_id)
        ]
        items.sort(key=lambda item: (item.created_at, item.id))
        return tuple(self._copy(item) for item in items)

    async def save(self, note: Note) -> None:
        current = self._notes.get(note.id)
        if current is None or current.owner_subject != note.owner_subject:
            raise KeyError(note.id)
        self._notes[note.id] = self._copy(note)

    async def delete(
        self,
        note_id: uuid.UUID,
        owner_subject: str,
    ) -> None:
        note = self._notes.get(note_id)
        if note is not None and note.owner_subject == owner_subject:
            del self._notes[note_id]


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _to_domain(model: NoteModel) -> Note:
    return Note(
        id=model.id,
        reference_id=model.reference_id,
        analysis_id=model.analysis_id,
        owner_subject=model.owner_subject,
        body=model.body,
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


def _to_model(note: Note) -> NoteModel:
    return NoteModel(
        id=note.id,
        reference_id=note.reference_id,
        analysis_id=note.analysis_id,
        owner_subject=note.owner_subject,
        body=note.body,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


class SqlAlchemyNoteRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def add(self, note: Note) -> None:
        async with self._sessions() as session, session.begin():
            session.add(_to_model(note))

    async def get_owned(
        self,
        note_id: uuid.UUID,
        owner_subject: str,
    ) -> Note | None:
        async with self._sessions() as session:
            model = await session.scalar(
                select(NoteModel).where(
                    NoteModel.id == note_id,
                    NoteModel.owner_subject == owner_subject,
                )
            )
            return _to_domain(model) if model else None

    async def list_owned(
        self,
        owner_subject: str,
        *,
        reference_id: uuid.UUID | None = None,
        analysis_id: uuid.UUID | None = None,
    ) -> tuple[Note, ...]:
        statement = select(NoteModel).where(
            NoteModel.owner_subject == owner_subject
        )
        if reference_id is not None:
            statement = statement.where(NoteModel.reference_id == reference_id)
        if analysis_id is not None:
            statement = statement.where(NoteModel.analysis_id == analysis_id)
        statement = statement.order_by(NoteModel.created_at, NoteModel.id)
        async with self._sessions() as session:
            models = await session.scalars(statement)
            return tuple(_to_domain(model) for model in models)

    async def save(self, note: Note) -> None:
        async with self._sessions() as session, session.begin():
            model = await session.scalar(
                select(NoteModel).where(
                    NoteModel.id == note.id,
                    NoteModel.owner_subject == note.owner_subject,
                )
            )
            if model is None:
                raise KeyError(note.id)
            model.analysis_id = note.analysis_id
            model.body = note.body
            model.updated_at = note.updated_at

    async def delete(
        self,
        note_id: uuid.UUID,
        owner_subject: str,
    ) -> None:
        async with self._sessions() as session, session.begin():
            await session.execute(
                delete(NoteModel).where(
                    NoteModel.id == note_id,
                    NoteModel.owner_subject == owner_subject,
                )
            )
