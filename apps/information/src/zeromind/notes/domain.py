import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

MAX_NOTE_BYTES = 65_536


@dataclass(slots=True)
class Note:
    id: uuid.UUID
    reference_id: uuid.UUID
    analysis_id: uuid.UUID | None
    owner_subject: str
    body: str
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def normalize_body(value: str) -> str:
        body = value.strip()
        if not body:
            raise ValueError("note body is required")
        if len(body.encode("utf-8")) > MAX_NOTE_BYTES:
            raise ValueError("note body exceeds 65536 UTF-8 bytes")
        return body

    @classmethod
    def create(
        cls,
        *,
        reference_id: uuid.UUID,
        analysis_id: uuid.UUID | None,
        owner_subject: str,
        body: str,
        now: datetime | None = None,
        identifier: uuid.UUID | None = None,
    ) -> "Note":
        owner = owner_subject.strip()
        if not owner:
            raise ValueError("note owner is required")
        if len(owner) > 255:
            raise ValueError("note owner exceeds 255 characters")
        current = now or datetime.now(UTC)
        return cls(
            id=identifier or uuid.uuid4(),
            reference_id=reference_id,
            analysis_id=analysis_id,
            owner_subject=owner,
            body=cls.normalize_body(body),
            created_at=current,
            updated_at=current,
        )

    def update(
        self,
        *,
        body: str,
        analysis_id: uuid.UUID | None,
        now: datetime | None = None,
    ) -> None:
        self.body = self.normalize_body(body)
        self.analysis_id = analysis_id
        self.updated_at = now or datetime.now(UTC)
