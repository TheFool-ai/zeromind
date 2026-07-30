import copy
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from zeromind.analysis.domain import (
    AnalysisDecisionOverride,
    AnalysisStatus,
    ContentAnalysis,
    EffectiveDecision,
    KeyQuote,
    ScoreDimension,
    Viewpoint,
)
from zeromind.analysis.models import (
    AnalysisDecisionOverrideModel,
    ContentAnalysisModel,
    ContentAnalysisTagModel,
)


@dataclass(frozen=True, slots=True)
class AnalysisQuery:
    generated_status: str | None = None
    effective_decision: str | None = "qualified"
    minimum_score: int | None = None
    category: str | None = None
    tag: str | None = None
    subscription_id: uuid.UUID | None = None
    reference_id: uuid.UUID | None = None
    observed_from: datetime | None = None
    observed_to: datetime | None = None
    limit: int = 20
    cursor: tuple[int, datetime, uuid.UUID] | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= 101:
            raise ValueError("analysis query limit must be from 1 to 101")
        if self.minimum_score is not None and not 0 <= self.minimum_score <= 100:
            raise ValueError("minimum score must be from 0 to 100")


class AnalysisRepository(Protocol):
    async def add(self, analysis: ContentAnalysis) -> ContentAnalysis: ...

    async def get(self, analysis_id: uuid.UUID) -> ContentAnalysis | None: ...

    async def get_by_run(
        self,
        run_id: uuid.UUID,
    ) -> ContentAnalysis | None: ...

    async def get_by_identity(
        self,
        reference_id: uuid.UUID,
        reference_revision: int,
        workflow_definition_id: uuid.UUID,
        workflow_definition_version: int,
    ) -> ContentAnalysis | None: ...

    async def list(self, query: AnalysisQuery) -> tuple[ContentAnalysis, ...]: ...

    async def add_override(
        self,
        override: AnalysisDecisionOverride,
    ) -> ContentAnalysis: ...


def _content_time(analysis: ContentAnalysis) -> datetime:
    return analysis.published_at or analysis.observed_at


def _sort_tuple(analysis: ContentAnalysis) -> tuple[int, datetime, uuid.UUID]:
    return (
        analysis.total_score if analysis.total_score is not None else -1,
        _content_time(analysis),
        analysis.id,
    )


class InMemoryAnalysisRepository:
    def __init__(self) -> None:
        self._analyses: dict[uuid.UUID, ContentAnalysis] = {}
        self._runs: dict[uuid.UUID, uuid.UUID] = {}
        self._identities: dict[
            tuple[uuid.UUID, int, uuid.UUID, int],
            uuid.UUID,
        ] = {}

    @staticmethod
    def _copy(analysis: ContentAnalysis) -> ContentAnalysis:
        return copy.deepcopy(analysis)

    async def add(self, analysis: ContentAnalysis) -> ContentAnalysis:
        identity = (
            analysis.reference_id,
            analysis.reference_revision,
            analysis.workflow_definition_id,
            analysis.workflow_definition_version,
        )
        if (
            analysis.id in self._analyses
            or analysis.workflow_run_id in self._runs
            or identity in self._identities
        ):
            raise ValueError("duplicate analysis")
        stored = self._copy(analysis)
        self._analyses[stored.id] = stored
        self._runs[stored.workflow_run_id] = stored.id
        self._identities[identity] = stored.id
        return self._copy(stored)

    async def get(self, analysis_id: uuid.UUID) -> ContentAnalysis | None:
        analysis = self._analyses.get(analysis_id)
        return self._copy(analysis) if analysis else None

    async def get_by_run(
        self,
        run_id: uuid.UUID,
    ) -> ContentAnalysis | None:
        analysis_id = self._runs.get(run_id)
        return await self.get(analysis_id) if analysis_id else None

    async def get_by_identity(
        self,
        reference_id: uuid.UUID,
        reference_revision: int,
        workflow_definition_id: uuid.UUID,
        workflow_definition_version: int,
    ) -> ContentAnalysis | None:
        analysis_id = self._identities.get(
            (
                reference_id,
                reference_revision,
                workflow_definition_id,
                workflow_definition_version,
            )
        )
        return await self.get(analysis_id) if analysis_id else None

    async def list(self, query: AnalysisQuery) -> tuple[ContentAnalysis, ...]:
        items = [
            analysis
            for analysis in self._analyses.values()
            if self._matches(analysis, query)
        ]
        items.sort(key=_sort_tuple, reverse=True)
        if query.cursor is not None:
            items = [
                analysis
                for analysis in items
                if _sort_tuple(analysis) < query.cursor
            ]
        return tuple(self._copy(item) for item in items[: query.limit])

    @staticmethod
    def _matches(analysis: ContentAnalysis, query: AnalysisQuery) -> bool:
        if (
            query.generated_status is not None
            and analysis.generated_status != query.generated_status
        ):
            return False
        if (
            query.effective_decision is not None
            and analysis.effective_decision != query.effective_decision
        ):
            return False
        if query.minimum_score is not None and (
            analysis.total_score is None
            or analysis.total_score < query.minimum_score
        ):
            return False
        if query.category is not None and (
            analysis.primary_category != query.category
            and query.category not in analysis.secondary_categories
        ):
            return False
        if query.tag is not None and query.tag not in analysis.tags:
            return False
        if (
            query.subscription_id is not None
            and analysis.subscription_id != query.subscription_id
        ):
            return False
        if (
            query.reference_id is not None
            and analysis.reference_id != query.reference_id
        ):
            return False
        if (
            query.observed_from is not None
            and analysis.observed_at < query.observed_from
        ):
            return False
        return not (
            query.observed_to is not None
            and analysis.observed_at > query.observed_to
        )

    async def add_override(
        self,
        override: AnalysisDecisionOverride,
    ) -> ContentAnalysis:
        analysis = self._analyses.get(override.analysis_id)
        if analysis is None:
            raise KeyError(override.analysis_id)
        analysis.add_override(
            decision=override.decision,
            reason=override.reason,
            actor_subject=override.actor_subject,
            now=override.created_at,
            identifier=override.id,
        )
        return self._copy(analysis)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _required_utc(value: datetime) -> datetime:
    normalized = _as_utc(value)
    if normalized is None:  # pragma: no cover - protected by database constraints
        raise ValueError("required timestamp is missing")
    return normalized


def _required_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    return value


def _required_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field_name} must be numeric")
    return float(value)


def _score_dimension(value: object) -> ScoreDimension:
    if not isinstance(value, dict):
        raise ValueError("stored score dimension must be an object")
    return ScoreDimension(
        value=_required_int(value.get("value"), "score dimension value"),
        weight=_required_number(value.get("weight"), "score dimension weight"),
        reason=str(value.get("reason", "")),
    )


def _analysis_model(analysis: ContentAnalysis) -> ContentAnalysisModel:
    return ContentAnalysisModel(
        id=analysis.id,
        reference_id=analysis.reference_id,
        reference_revision=analysis.reference_revision,
        subscription_id=analysis.subscription_id,
        workflow_definition_id=analysis.workflow_definition_id,
        workflow_definition_version=analysis.workflow_definition_version,
        workflow_run_id=analysis.workflow_run_id,
        generated_status=analysis.generated_status,
        effective_decision=analysis.effective_decision,
        source_name=analysis.source_name,
        source_feed_url=analysis.source_feed_url,
        title=analysis.title,
        original_url=analysis.original_url,
        author=analysis.author,
        published_at=analysis.published_at,
        observed_at=analysis.observed_at,
        screening={
            "score": analysis.screening_score,
            "reason": analysis.screening_reason,
            "summary": analysis.screening_summary,
        },
        primary_category=analysis.primary_category,
        secondary_categories=list(analysis.secondary_categories),
        one_sentence_summary=analysis.one_sentence_summary,
        summary=analysis.summary,
        viewpoints=[
            {
                "statement": viewpoint.statement,
                "explanation": viewpoint.explanation,
            }
            for viewpoint in analysis.viewpoints
        ],
        key_quotes=[
            {"text": quote.text, "context": quote.context}
            for quote in analysis.key_quotes
        ],
        total_score=analysis.total_score,
        dimensions={
            name: {
                "value": dimension.value,
                "weight": dimension.weight,
                "reason": dimension.reason,
            }
            for name, dimension in analysis.dimensions.items()
        },
        recommendation_level=analysis.recommendation_level,
        recommendation_reason=analysis.recommendation_reason,
        provenance=dict(analysis.provenance),
        created_at=analysis.created_at,
    )


class SqlAlchemyAnalysisRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def add(self, analysis: ContentAnalysis) -> ContentAnalysis:
        try:
            async with self._sessions() as session, session.begin():
                session.add(_analysis_model(analysis))
                session.add_all(
                    ContentAnalysisTagModel(
                        analysis_id=analysis.id,
                        tag=tag,
                    )
                    for tag in analysis.tags
                )
                await session.flush()
        except IntegrityError as error:
            raise ValueError("duplicate analysis") from error
        restored = await self.get(analysis.id)
        if restored is None:  # pragma: no cover - insert and read share a database
            raise RuntimeError("inserted analysis is missing")
        return restored

    async def get(self, analysis_id: uuid.UUID) -> ContentAnalysis | None:
        async with self._sessions() as session:
            model = await session.get(ContentAnalysisModel, analysis_id)
            return await self._to_domain(session, model) if model else None

    async def get_by_run(
        self,
        run_id: uuid.UUID,
    ) -> ContentAnalysis | None:
        async with self._sessions() as session:
            model = await session.scalar(
                select(ContentAnalysisModel).where(
                    ContentAnalysisModel.workflow_run_id == run_id
                )
            )
            return await self._to_domain(session, model) if model else None

    async def get_by_identity(
        self,
        reference_id: uuid.UUID,
        reference_revision: int,
        workflow_definition_id: uuid.UUID,
        workflow_definition_version: int,
    ) -> ContentAnalysis | None:
        async with self._sessions() as session:
            model = await session.scalar(
                select(ContentAnalysisModel).where(
                    ContentAnalysisModel.reference_id == reference_id,
                    ContentAnalysisModel.reference_revision == reference_revision,
                    ContentAnalysisModel.workflow_definition_id
                    == workflow_definition_id,
                    ContentAnalysisModel.workflow_definition_version
                    == workflow_definition_version,
                )
            )
            return await self._to_domain(session, model) if model else None

    async def list(self, query: AnalysisQuery) -> tuple[ContentAnalysis, ...]:
        score = func.coalesce(ContentAnalysisModel.total_score, -1)
        content_time = func.coalesce(
            ContentAnalysisModel.published_at,
            ContentAnalysisModel.observed_at,
        )
        statement = select(ContentAnalysisModel)
        if query.tag is not None:
            statement = statement.join(
                ContentAnalysisTagModel,
                ContentAnalysisTagModel.analysis_id == ContentAnalysisModel.id,
            ).where(ContentAnalysisTagModel.tag == query.tag)
        if query.generated_status is not None:
            statement = statement.where(
                ContentAnalysisModel.generated_status == query.generated_status
            )
        if query.effective_decision is not None:
            statement = statement.where(
                ContentAnalysisModel.effective_decision
                == query.effective_decision
            )
        if query.minimum_score is not None:
            statement = statement.where(
                ContentAnalysisModel.total_score >= query.minimum_score
            )
        if query.category is not None:
            statement = statement.where(
                or_(
                    ContentAnalysisModel.primary_category == query.category,
                    ContentAnalysisModel.secondary_categories.contains(
                        [query.category]
                    ),
                )
            )
        if query.subscription_id is not None:
            statement = statement.where(
                ContentAnalysisModel.subscription_id == query.subscription_id
            )
        if query.reference_id is not None:
            statement = statement.where(
                ContentAnalysisModel.reference_id == query.reference_id
            )
        if query.observed_from is not None:
            statement = statement.where(
                ContentAnalysisModel.observed_at >= query.observed_from
            )
        if query.observed_to is not None:
            statement = statement.where(
                ContentAnalysisModel.observed_at <= query.observed_to
            )
        if query.cursor is not None:
            cursor_score, cursor_time, cursor_id = query.cursor
            statement = statement.where(
                or_(
                    score < cursor_score,
                    and_(score == cursor_score, content_time < cursor_time),
                    and_(
                        score == cursor_score,
                        content_time == cursor_time,
                        ContentAnalysisModel.id < cursor_id,
                    ),
                )
            )
        statement = statement.order_by(
            score.desc(),
            content_time.desc(),
            ContentAnalysisModel.id.desc(),
        ).limit(query.limit)
        async with self._sessions() as session:
            models = tuple(await session.scalars(statement))
            return tuple(
                [await self._to_domain(session, model) for model in models]
            )

    async def add_override(
        self,
        override: AnalysisDecisionOverride,
    ) -> ContentAnalysis:
        async with self._sessions() as session, session.begin():
            analysis = await session.scalar(
                select(ContentAnalysisModel)
                .where(ContentAnalysisModel.id == override.analysis_id)
                .with_for_update()
            )
            if analysis is None:
                raise KeyError(override.analysis_id)
            last_sequence = await session.scalar(
                select(
                    func.max(AnalysisDecisionOverrideModel.sequence)
                ).where(
                    AnalysisDecisionOverrideModel.analysis_id
                    == override.analysis_id
                )
            )
            sequence = (last_sequence or 0) + 1
            session.add(
                AnalysisDecisionOverrideModel(
                    id=override.id,
                    analysis_id=override.analysis_id,
                    sequence=sequence,
                    decision=override.decision,
                    reason=override.reason,
                    actor_subject=override.actor_subject,
                    created_at=override.created_at,
                )
            )
            analysis.effective_decision = override.decision
        restored = await self.get(override.analysis_id)
        if restored is None:  # pragma: no cover - row was locked above
            raise RuntimeError("updated analysis is missing")
        return restored

    @staticmethod
    async def _to_domain(
        session: AsyncSession,
        model: ContentAnalysisModel,
    ) -> ContentAnalysis:
        tags = tuple(
            await session.scalars(
                select(ContentAnalysisTagModel.tag)
                .where(ContentAnalysisTagModel.analysis_id == model.id)
                .order_by(ContentAnalysisTagModel.tag)
            )
        )
        override_models = tuple(
            await session.scalars(
                select(AnalysisDecisionOverrideModel)
                .where(AnalysisDecisionOverrideModel.analysis_id == model.id)
                .order_by(AnalysisDecisionOverrideModel.sequence)
            )
        )
        screening = model.screening
        return ContentAnalysis(
            id=model.id,
            reference_id=model.reference_id,
            reference_revision=model.reference_revision,
            subscription_id=model.subscription_id,
            workflow_definition_id=model.workflow_definition_id,
            workflow_definition_version=model.workflow_definition_version,
            workflow_run_id=model.workflow_run_id,
            generated_status=cast(AnalysisStatus, model.generated_status),
            source_name=model.source_name,
            source_feed_url=model.source_feed_url,
            title=model.title,
            original_url=model.original_url,
            author=model.author,
            published_at=_as_utc(model.published_at),
            observed_at=_required_utc(model.observed_at),
            screening_score=_required_int(screening["score"], "screening score"),
            screening_reason=str(screening["reason"]),
            screening_summary=(
                str(screening["summary"])
                if screening.get("summary") is not None
                else None
            ),
            primary_category=model.primary_category,
            secondary_categories=tuple(model.secondary_categories),
            tags=tags,
            one_sentence_summary=model.one_sentence_summary,
            summary=model.summary,
            viewpoints=tuple(
                Viewpoint(
                    statement=str(item["statement"]),
                    explanation=str(item["explanation"]),
                )
                for item in model.viewpoints
            ),
            key_quotes=tuple(
                KeyQuote(
                    text=str(item["text"]),
                    context=(
                        str(item["context"])
                        if item.get("context") is not None
                        else None
                    ),
                )
                for item in model.key_quotes
            ),
            total_score=model.total_score,
            dimensions={
                name: _score_dimension(item)
                for name, item in model.dimensions.items()
            },
            recommendation_level=model.recommendation_level,
            recommendation_reason=model.recommendation_reason,
            provenance=model.provenance,
            created_at=_required_utc(model.created_at),
            _overrides=[
                AnalysisDecisionOverride(
                    id=item.id,
                    analysis_id=item.analysis_id,
                    sequence=item.sequence,
                    decision=cast(EffectiveDecision, item.decision),
                    reason=item.reason,
                    actor_subject=item.actor_subject,
                    created_at=_required_utc(item.created_at),
                )
                for item in override_models
            ],
        )
