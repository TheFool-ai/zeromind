import uuid
from dataclasses import dataclass, replace
from datetime import datetime

from zeromind.analysis.domain import ContentAnalysis
from zeromind.analysis.repository import AnalysisRepository
from zeromind.content.resolver import ContentResolver, ResolvedDocument
from zeromind.ingestion.domain import (
    AnalysisStatus,
    ContentReference,
    ReferenceRevision,
    normalized_entry_url,
)
from zeromind.ingestion.repository import ReferenceRepository
from zeromind.subscriptions.domain import Subscription
from zeromind.subscriptions.repository import SubscriptionRepository
from zeromind.workflows.constants import MAIN_ANALYSIS_WORKFLOW_NAME
from zeromind.workflows.domain import WorkflowDefinition
from zeromind.workflows.repository import WorkflowRepository


@dataclass(frozen=True, slots=True)
class ReferenceListQuery:
    status: AnalysisStatus | None = None
    category: str | None = None
    minimum_score: int | None = None
    subscription_id: uuid.UUID | None = None
    published_from: datetime | None = None
    published_to: datetime | None = None

    def __post_init__(self) -> None:
        if self.minimum_score is not None and not 0 <= self.minimum_score <= 100:
            raise ValueError("minimum score must be from 0 to 100")


@dataclass(frozen=True, slots=True)
class ReferenceListItem:
    reference: ContentReference
    revision: ReferenceRevision
    subscription: Subscription | None
    analysis: ContentAnalysis | None


@dataclass(frozen=True, slots=True)
class ReferenceReadingDetail:
    reference: ContentReference
    revision: ReferenceRevision
    subscription: Subscription | None
    analysis: ContentAnalysis | None
    iframe_url: str | None


class ContentResolverUnavailable(RuntimeError):
    pass


class ReferenceReadService:
    def __init__(
        self,
        references: ReferenceRepository,
        subscriptions: SubscriptionRepository,
        analyses: AnalysisRepository,
        workflows: WorkflowRepository,
        content_resolver: ContentResolver | None = None,
    ) -> None:
        self._references = references
        self._subscriptions = subscriptions
        self._analyses = analyses
        self._workflows = workflows
        self._content_resolver = content_resolver

    async def _main_workflow(self) -> WorkflowDefinition | None:
        matches = [
            definition
            for definition in await self._workflows.list_definitions()
            if definition.name == MAIN_ANALYSIS_WORKFLOW_NAME
            and definition.status == "active"
        ]
        return matches[0] if len(matches) == 1 else None

    async def _analysis(
        self,
        reference: ContentReference,
        workflow: WorkflowDefinition | None,
    ) -> ContentAnalysis | None:
        if workflow is None:
            return None
        return await self._analyses.get_by_identity(
            reference.id,
            reference.current_revision,
            workflow.id,
            workflow.version,
        )

    @staticmethod
    def _matches(
        item: ReferenceListItem,
        query: ReferenceListQuery,
    ) -> bool:
        if query.status is not None and item.reference.analysis_status != query.status:
            return False
        if (
            query.subscription_id is not None
            and item.reference.subscription_id != query.subscription_id
        ):
            return False
        if (
            query.published_from is not None
            and (
                item.revision.published_at is None
                or item.revision.published_at < query.published_from
            )
        ):
            return False
        if (
            query.published_to is not None
            and (
                item.revision.published_at is None
                or item.revision.published_at > query.published_to
            )
        ):
            return False
        if query.category is not None and (
            item.analysis is None
            or (
                item.analysis.primary_category != query.category
                and query.category not in item.analysis.secondary_categories
            )
        ):
            return False
        return not (
            query.minimum_score is not None
            and (
                item.analysis is None
                or item.analysis.total_score is None
                or item.analysis.total_score < query.minimum_score
            )
        )

    async def list(self, query: ReferenceListQuery) -> tuple[ReferenceListItem, ...]:
        workflow = await self._main_workflow()
        items: list[ReferenceListItem] = []
        for reference in await self._references.list_references():
            revision = await self._references.get_current_revision(reference.id)
            item = ReferenceListItem(
                reference=reference,
                revision=revision,
                subscription=await self._subscriptions.get(reference.subscription_id),
                analysis=await self._analysis(reference, workflow),
            )
            if self._matches(item, query):
                items.append(item)
        return tuple(items)

    async def get(self, reference_id: uuid.UUID) -> ReferenceReadingDetail:
        reference = await self._references.get_reference(reference_id)
        if reference is None:
            raise KeyError(reference_id)
        revision = await self._references.get_current_revision(reference_id)
        workflow = await self._main_workflow()
        return ReferenceReadingDetail(
            reference=reference,
            revision=revision,
            subscription=await self._subscriptions.get(reference.subscription_id),
            analysis=await self._analysis(reference, workflow),
            iframe_url=normalized_entry_url(
                revision.url or reference.original_url
            ),
        )

    async def resolve_content(self, reference_id: uuid.UUID) -> ResolvedDocument:
        reference = await self._references.get_reference(reference_id)
        if reference is None:
            raise KeyError(reference_id)
        if self._content_resolver is None:
            raise ContentResolverUnavailable
        revision = await self._references.get_current_revision(reference_id)
        current_url = normalized_entry_url(revision.url or reference.original_url)
        transient_reference = (
            replace(reference, original_url=current_url)
            if current_url != reference.original_url
            else reference
        )
        return await self._content_resolver.resolve(transient_reference)
