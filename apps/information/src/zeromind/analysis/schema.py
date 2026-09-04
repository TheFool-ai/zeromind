from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from zeromind.workflows.primitives import calculate_weighted_score

BoundedCategory = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]
BoundedTag = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
]


class DraftModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class ExecutionDraft(DraftModel):
    agent_id: UUID
    agent_version: int = Field(ge=1, strict=True)
    provider: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=255)
    usage: dict[str, int | float] = Field(default_factory=dict)


class ReferenceDraft(DraftModel):
    reference_id: UUID
    revision: int = Field(ge=1, strict=True)
    subscription_id: UUID
    url: str | None = Field(default=None, max_length=4096)
    title: str = Field(min_length=1, max_length=1000)
    summary: str | None = Field(default=None, max_length=5000)
    author: str | None = Field(default=None, max_length=500)
    published_at: datetime | None = None
    updated_at: datetime | None = None
    observed_at: datetime


class ScreeningDraft(DraftModel):
    score: int = Field(ge=0, le=100, strict=True)
    reason: str = Field(min_length=1, max_length=2000)
    summary: str | None = Field(default=None, max_length=1000)
    execution: ExecutionDraft = Field(alias="_execution")


class ViewpointDraft(DraftModel):
    statement: str = Field(min_length=1, max_length=500)
    explanation: str = Field(min_length=1, max_length=2000)


class KeyQuoteDraft(DraftModel):
    text: str = Field(min_length=1, max_length=300)
    context: str | None = Field(default=None, max_length=200)


class ContentScoreDraft(DraftModel):
    value: int = Field(ge=0, le=100, strict=True)
    reason: str = Field(min_length=1, max_length=2000)


class ContentDraft(DraftModel):
    primary_category: BoundedCategory
    secondary_categories: list[BoundedCategory] = Field(
        default_factory=list,
        max_length=10,
    )
    tags: list[BoundedTag] = Field(default_factory=list, max_length=20)
    one_sentence_summary: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1, max_length=5000)
    viewpoints: list[ViewpointDraft] = Field(default_factory=list, max_length=10)
    key_quotes: list[KeyQuoteDraft] = Field(default_factory=list, max_length=5)
    recommendation_level: str = Field(min_length=1, max_length=80)
    recommendation_reason: str = Field(min_length=1, max_length=2000)
    scores: dict[str, ContentScoreDraft] = Field(min_length=1, max_length=20)
    execution: ExecutionDraft = Field(alias="_execution")

    @model_validator(mode="after")
    def unique_classifications_and_tags(self) -> "ContentDraft":
        if len(self.secondary_categories) != len(set(self.secondary_categories)):
            raise ValueError("secondary categories must be unique")
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("tags must be unique")
        return self


class ScoreDimensionDraft(DraftModel):
    value: int = Field(ge=0, le=100, strict=True)
    weight: float = Field(gt=0)
    reason: str = Field(min_length=1, max_length=2000)


class ScoreDraft(DraftModel):
    total: int = Field(ge=0, le=100, strict=True)
    dimensions: dict[str, ScoreDimensionDraft] = Field(
        min_length=1,
        max_length=20,
    )

    @model_validator(mode="after")
    def deterministic_total(self) -> "ScoreDraft":
        computed = calculate_weighted_score(
            {
                name: dimension.model_dump()
                for name, dimension in self.dimensions.items()
            }
        )
        if self.total != computed["total"]:
            raise ValueError("score total does not match deterministic calculation")
        return self


class ContentAnalysisDraftV1(DraftModel):
    schema_version: Literal[1]
    status: Literal["initial_rejected", "fine_rejected", "qualified"]
    reference: ReferenceDraft
    screening: ScreeningDraft
    content: ContentDraft | None = None
    score: ScoreDraft | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_transient_content(cls, value: object) -> object:
        def scan(item: object) -> None:
            if isinstance(item, dict):
                for key, nested in item.items():
                    if str(key) == "_transient_document":
                        raise ValueError(
                            "_transient_document cannot appear in analysis output"
                        )
                    if (
                        str(key) == "text"
                        and isinstance(nested, str)
                        and len(nested) > 300
                    ):
                        raise ValueError("article body-like text is not allowed")
                    scan(nested)
                return
            if isinstance(item, list | tuple):
                for nested in item:
                    scan(nested)
                return
            if (
                isinstance(item, str)
                and "ARTICLE BODY MUST NOT BE STORED" in item
            ):
                raise ValueError("article body marker is not allowed")

        scan(value)
        return value

    @model_validator(mode="after")
    def valid_status_shape(self) -> "ContentAnalysisDraftV1":
        if self.status == "initial_rejected":
            if self.content is not None or self.score is not None:
                raise ValueError(
                    "initial_rejected cannot contain content or score"
                )
            return self
        if self.content is None or self.score is None:
            raise ValueError(
                "fine_rejected and qualified require content and score"
            )
        if set(self.content.scores) != set(self.score.dimensions):
            raise ValueError("score dimensions must match content scores")
        for name, content_score in self.content.scores.items():
            dimension = self.score.dimensions[name]
            if (
                content_score.value != dimension.value
                or content_score.reason != dimension.reason
            ):
                raise ValueError(
                    "score dimensions must match content scores"
                )
        return self
