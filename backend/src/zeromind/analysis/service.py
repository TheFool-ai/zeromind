import base64
import json
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from zeromind.analysis.domain import ContentAnalysis, EffectiveDecision
from zeromind.analysis.repository import AnalysisQuery, AnalysisRepository, AnalysisSort


@dataclass(frozen=True, slots=True)
class AnalysisPage:
    items: tuple[ContentAnalysis, ...]
    next_cursor: str | None


def encode_cursor(
    sort: AnalysisSort,
    sort_score: int,
    content_time: datetime,
    analysis_id: uuid.UUID,
) -> str:
    normalized_time = (
        content_time.replace(tzinfo=UTC)
        if content_time.tzinfo is None
        else content_time.astimezone(UTC)
    )
    payload = json.dumps(
        {
            "v": 1,
            "sort": sort,
            "score": sort_score,
            "time": normalized_time.isoformat(),
            "id": str(analysis_id),
        },
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(
    value: str,
    *,
    expected_sort: AnalysisSort,
) -> tuple[int, datetime, uuid.UUID]:
    try:
        padding = "=" * (-len(value) % 4)
        decoded = base64.b64decode(
            value + padding,
            altchars=b"-_",
            validate=True,
        )
        payload = json.loads(decoded)
        if not isinstance(payload, dict) or payload.get("v") != 1:
            raise ValueError("cursor payload version is invalid")
        if payload.get("sort") != expected_sort:
            raise ValueError("cursor sort does not match query")
        raw_score = payload.get("score")
        raw_time = payload.get("time")
        raw_id = payload.get("id")
        if (
            isinstance(raw_score, bool)
            or not isinstance(raw_score, int)
            or not -1 <= raw_score <= 100
        ):
            raise ValueError("cursor score is invalid")
        if not isinstance(raw_time, str) or not isinstance(raw_id, str):
            raise ValueError("cursor values have invalid types")
        content_time = datetime.fromisoformat(raw_time)
        if content_time.tzinfo is None:
            raise ValueError("cursor time must include a timezone")
        return (
            raw_score,
            content_time.astimezone(UTC),
            uuid.UUID(raw_id),
        )
    except (UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("invalid_cursor") from error


def _content_time(analysis: ContentAnalysis) -> datetime:
    return analysis.published_at or analysis.observed_at


class AnalysisService:
    def __init__(self, repository: AnalysisRepository) -> None:
        self._repository = repository

    async def list(self, query: AnalysisQuery) -> AnalysisPage:
        if not 1 <= query.limit <= 100:
            raise ValueError("analysis list limit must be from 1 to 100")
        fetched = await self._repository.list(
            replace(query, limit=query.limit + 1)
        )
        items = fetched[: query.limit]
        next_cursor = None
        if len(fetched) > query.limit and items:
            last = items[-1]
            next_cursor = encode_cursor(
                query.sort,
                last.total_score if last.total_score is not None else -1,
                _content_time(last),
                last.id,
            )
        return AnalysisPage(items=items, next_cursor=next_cursor)

    async def get(self, analysis_id: uuid.UUID) -> ContentAnalysis:
        analysis = await self._repository.get(analysis_id)
        if analysis is None:
            raise KeyError(analysis_id)
        return analysis

    async def override(
        self,
        analysis_id: uuid.UUID,
        *,
        decision: EffectiveDecision,
        reason: str,
        actor_subject: str,
    ) -> ContentAnalysis:
        analysis = await self.get(analysis_id)
        override = analysis.add_override(
            decision=decision,
            reason=reason,
            actor_subject=actor_subject,
        )
        return await self._repository.add_override(override)
