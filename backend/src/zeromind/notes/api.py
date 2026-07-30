from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict

from zeromind.identity.context import request_identity
from zeromind.notes.domain import Note
from zeromind.notes.service import NoteService


class NoteResponse(BaseModel):
    id: UUID
    reference_id: UUID
    analysis_id: UUID | None
    owner_subject: str
    body: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, note: Note) -> "NoteResponse":
        return cls(
            id=note.id,
            reference_id=note.reference_id,
            analysis_id=note.analysis_id,
            owner_subject=note.owner_subject,
            body=note.body,
            created_at=note.created_at,
            updated_at=note.updated_at,
        )


class NoteListResponse(BaseModel):
    items: list[NoteResponse]


class CreateNoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_id: UUID
    analysis_id: UUID | None = None
    body: str


class UpdateNoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_id: UUID | None = None
    body: str


def _invalid_note(error: ValueError) -> HTTPException:
    code = str(error).partition(":")[0]
    if code not in {
        "reference_not_found",
        "analysis_not_found",
        "analysis_reference_mismatch",
    }:
        code = "invalid_note"
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": code, "message": str(error)},
    )


def create_note_router(service: NoteService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/notes", tags=["notes"])

    @router.get("", response_model=NoteListResponse)
    async def list_notes(
        request: Request,
        reference_id: UUID | None = None,
        analysis_id: UUID | None = None,
    ) -> NoteListResponse:
        identity = request_identity(request)
        notes = await service.list_owned(
            identity.username,
            reference_id=reference_id,
            analysis_id=analysis_id,
        )
        return NoteListResponse(
            items=[NoteResponse.from_domain(note) for note in notes]
        )

    @router.post(
        "",
        response_model=NoteResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_note(
        payload: CreateNoteRequest,
        request: Request,
    ) -> NoteResponse:
        identity = request_identity(request)
        try:
            note = await service.create(
                owner_subject=identity.username,
                reference_id=payload.reference_id,
                analysis_id=payload.analysis_id,
                body=payload.body,
            )
        except ValueError as error:
            raise _invalid_note(error) from error
        return NoteResponse.from_domain(note)

    @router.put("/{note_id}", response_model=NoteResponse)
    async def update_note(
        note_id: UUID,
        payload: UpdateNoteRequest,
        request: Request,
    ) -> NoteResponse:
        identity = request_identity(request)
        try:
            note = await service.update(
                note_id,
                owner_subject=identity.username,
                body=payload.body,
                analysis_id=payload.analysis_id,
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "note_not_found"},
            ) from error
        except ValueError as error:
            raise _invalid_note(error) from error
        return NoteResponse.from_domain(note)

    @router.delete(
        "/{note_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_note(note_id: UUID, request: Request) -> Response:
        identity = request_identity(request)
        try:
            await service.delete(note_id, owner_subject=identity.username)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "note_not_found"},
            ) from error
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
