import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, cast

AnalysisStatus = Literal["initial_rejected", "fine_rejected", "qualified"]
EffectiveDecision = Literal["qualified", "rejected"]


@dataclass(frozen=True, slots=True)
class ScoreDimension:
    value: int
    weight: float
    reason: str

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not 0 <= self.value <= 100:
            raise ValueError("score dimension value must be from 0 to 100")
        if self.weight <= 0:
            raise ValueError("score dimension weight must be positive")
        if not self.reason.strip() or len(self.reason) > 2000:
            raise ValueError("score dimension reason is invalid")


@dataclass(frozen=True, slots=True)
class Viewpoint:
    statement: str
    explanation: str

    def __post_init__(self) -> None:
        if not self.statement.strip() or len(self.statement) > 500:
            raise ValueError("viewpoint statement is invalid")
        if not self.explanation.strip() or len(self.explanation) > 2000:
            raise ValueError("viewpoint explanation is invalid")


@dataclass(frozen=True, slots=True)
class KeyQuote:
    text: str
    context: str | None

    def __post_init__(self) -> None:
        if not self.text.strip() or len(self.text) > 300:
            raise ValueError("key quote text is invalid")
        if self.context is not None and len(self.context) > 200:
            raise ValueError("key quote context is invalid")


@dataclass(frozen=True, slots=True)
class AnalysisDecisionOverride:
    id: uuid.UUID
    analysis_id: uuid.UUID
    sequence: int
    decision: EffectiveDecision
    reason: str
    actor_subject: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ContentAnalysis:
    id: uuid.UUID
    reference_id: uuid.UUID
    reference_revision: int
    subscription_id: uuid.UUID
    workflow_definition_id: uuid.UUID
    workflow_definition_version: int
    workflow_run_id: uuid.UUID
    generated_status: AnalysisStatus
    source_name: str
    source_feed_url: str
    title: str
    original_url: str | None
    author: str | None
    published_at: datetime | None
    observed_at: datetime
    screening_score: int
    screening_reason: str
    screening_summary: str | None
    primary_category: str | None
    secondary_categories: tuple[str, ...]
    tags: tuple[str, ...]
    one_sentence_summary: str | None
    summary: str | None
    viewpoints: tuple[Viewpoint, ...]
    key_quotes: tuple[KeyQuote, ...]
    total_score: int | None
    dimensions: Mapping[str, ScoreDimension]
    recommendation_level: str | None
    recommendation_reason: str | None
    provenance: Mapping[str, object]
    created_at: datetime
    _overrides: list[AnalysisDecisionOverride] = field(
        default_factory=list,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if self.generated_status not in {
            "initial_rejected",
            "fine_rejected",
            "qualified",
        }:
            raise ValueError("unknown generated analysis status")
        if self.reference_revision < 1 or self.workflow_definition_version < 1:
            raise ValueError("analysis versions must be positive")
        if (
            isinstance(self.screening_score, bool)
            or not 0 <= self.screening_score <= 100
        ):
            raise ValueError("screening score must be from 0 to 100")
        if self.total_score is not None and (
            isinstance(self.total_score, bool)
            or not 0 <= self.total_score <= 100
        ):
            raise ValueError("total score must be from 0 to 100")
        if len(self.viewpoints) > 10:
            raise ValueError("analysis cannot contain more than 10 viewpoints")
        if len(self.key_quotes) > 5:
            raise ValueError("analysis cannot contain more than 5 key quotes")

    @property
    def overrides(self) -> tuple[AnalysisDecisionOverride, ...]:
        return tuple(sorted(self._overrides, key=lambda item: item.sequence))

    @property
    def effective_decision(self) -> EffectiveDecision:
        if self._overrides:
            return max(
                self._overrides,
                key=lambda item: item.sequence,
            ).decision
        return "qualified" if self.generated_status == "qualified" else "rejected"

    def add_override(
        self,
        *,
        decision: EffectiveDecision | str,
        reason: str,
        actor_subject: str,
        now: datetime | None = None,
        identifier: uuid.UUID | None = None,
    ) -> AnalysisDecisionOverride:
        if decision not in {"qualified", "rejected"}:
            raise ValueError("override decision must be qualified or rejected")
        normalized_reason = reason.strip()
        if not 10 <= len(normalized_reason) <= 2000:
            raise ValueError("override reason must contain 10 to 2000 characters")
        normalized_actor = actor_subject.strip()
        if not normalized_actor:
            raise ValueError("override actor is required")
        if len(normalized_actor) > 255:
            raise ValueError("override actor exceeds 255 characters")
        override = AnalysisDecisionOverride(
            id=identifier or uuid.uuid4(),
            analysis_id=self.id,
            sequence=max(
                (item.sequence for item in self._overrides),
                default=0,
            )
            + 1,
            decision=cast(EffectiveDecision, decision),
            reason=normalized_reason,
            actor_subject=normalized_actor,
            created_at=now or datetime.now(UTC),
        )
        self._overrides.append(override)
        return override
