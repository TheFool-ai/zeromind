import uuid

from zeromind.analysis.repository import AnalysisRepository
from zeromind.ingestion.repository import ReferenceRepository
from zeromind.notes.domain import Note
from zeromind.notes.repository import NoteRepository


class NoteService:
    def __init__(
        self,
        notes: NoteRepository,
        references: ReferenceRepository,
        analyses: AnalysisRepository,
    ) -> None:
        self._notes = notes
        self._references = references
        self._analyses = analyses

    async def list(
        self,
        *,
        reference_id: uuid.UUID | None = None,
        analysis_id: uuid.UUID | None = None,
    ) -> tuple[Note, ...]:
        return await self._notes.list(
            reference_id=reference_id,
            analysis_id=analysis_id,
        )

    async def create(
        self,
        *,
        reference_id: uuid.UUID,
        analysis_id: uuid.UUID | None,
        body: str,
    ) -> Note:
        await self._validate_relationship(reference_id, analysis_id)
        note = Note.create(
            reference_id=reference_id,
            analysis_id=analysis_id,
            owner_subject="local",
            body=body,
        )
        await self._notes.add(note)
        return note

    async def update(
        self,
        note_id: uuid.UUID,
        *,
        body: str,
        analysis_id: uuid.UUID | None,
    ) -> Note:
        note = await self._notes.get(note_id)
        if note is None:
            raise KeyError(note_id)
        await self._validate_relationship(note.reference_id, analysis_id)
        note.update(body=body, analysis_id=analysis_id)
        await self._notes.save(note)
        return note

    async def delete(
        self,
        note_id: uuid.UUID,
    ) -> None:
        note = await self._notes.get(note_id)
        if note is None:
            raise KeyError(note_id)
        await self._notes.delete(note_id)

    async def _validate_relationship(
        self,
        reference_id: uuid.UUID,
        analysis_id: uuid.UUID | None,
    ) -> None:
        reference = await self._references.get_reference(reference_id)
        if reference is None:
            raise ValueError(f"reference_not_found:{reference_id}")
        if analysis_id is None:
            return
        analysis = await self._analyses.get(analysis_id)
        if analysis is None:
            raise ValueError(f"analysis_not_found:{analysis_id}")
        if analysis.reference_id != reference_id:
            raise ValueError(
                f"analysis_reference_mismatch:{analysis_id}:{reference_id}"
            )
