import uuid
from datetime import UTC, datetime

from zeromind.analysis.domain import (
    ContentAnalysis,
    KeyQuote,
    ScoreDimension,
    Viewpoint,
)
from zeromind.analysis.repository import AnalysisRepository
from zeromind.analysis.schema import ContentAnalysisDraftV1
from zeromind.ingestion.repository import ReferenceRepository
from zeromind.subscriptions.public import SubscriptionService
from zeromind.workflows.domain import WorkflowDefinition, WorkflowRun


class AnalysisProjector:
    def __init__(
        self,
        analysis_repository: AnalysisRepository,
        reference_repository: ReferenceRepository,
        subscription_service: SubscriptionService,
    ) -> None:
        self._analyses = analysis_repository
        self._references = reference_repository
        self._subscriptions = subscription_service

    async def project(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
    ) -> ContentAnalysis | None:
        projection = definition.spec.projection
        if projection is None:
            return None
        if projection != "content_analysis_v1":  # pragma: no cover - DSL is closed
            raise ValueError(f"unsupported analysis projection: {projection}")
        if run.status != "completed" or run.output is None:
            raise ValueError("analysis projection requires a completed workflow run")
        if (
            run.definition_id != definition.id
            or run.definition_version != definition.version
        ):
            raise ValueError("workflow run definition provenance does not match")
        existing = await self._analyses.get_by_run(run.id)
        if existing is not None:
            return existing

        draft = ContentAnalysisDraftV1.model_validate(run.output)
        trigger_reference_id, trigger_revision = self._trigger_identity(run)
        if draft.reference.reference_id != trigger_reference_id:
            raise ValueError("output reference does not match workflow trigger")
        if draft.reference.revision != trigger_revision:
            raise ValueError("output revision does not match workflow trigger")

        existing = await self._analyses.get_by_identity(
            trigger_reference_id,
            trigger_revision,
            definition.id,
            definition.version,
        )
        if existing is not None:
            return existing

        reference = await self._references.get_reference(trigger_reference_id)
        if reference is None:
            raise ValueError(f"reference not found: {trigger_reference_id}")
        if reference.subscription_id != draft.reference.subscription_id:
            raise ValueError("output subscription does not match reference")
        try:
            revision = await self._references.get_revision(
                trigger_reference_id,
                trigger_revision,
            )
        except KeyError as error:
            raise ValueError(
                f"reference revision not found: {trigger_reference_id}:{trigger_revision}"
            ) from error
        if revision.reference_id != trigger_reference_id:
            raise ValueError("reference revision belongs to another reference")

        subscription = await self._subscriptions.get(reference.subscription_id)
        if subscription is None:
            raise ValueError(f"subscription not found: {reference.subscription_id}")

        content = draft.content
        score = draft.score
        provenance: dict[str, object] = {
            "screening": draft.screening.execution.model_dump(mode="json"),
        }
        if content is not None:
            provenance["analysis"] = content.execution.model_dump(mode="json")
        analysis = ContentAnalysis(
            id=uuid.uuid4(),
            reference_id=trigger_reference_id,
            reference_revision=trigger_revision,
            subscription_id=reference.subscription_id,
            workflow_definition_id=definition.id,
            workflow_definition_version=definition.version,
            workflow_run_id=run.id,
            generated_status=draft.status,
            source_name=subscription.title,
            source_feed_url=subscription.feed_url,
            title=draft.reference.title,
            original_url=draft.reference.url or reference.original_url,
            author=draft.reference.author,
            published_at=draft.reference.published_at,
            observed_at=draft.reference.observed_at,
            screening_score=draft.screening.score,
            screening_reason=draft.screening.reason,
            screening_summary=draft.screening.summary,
            primary_category=(
                content.primary_category if content is not None else None
            ),
            secondary_categories=(
                tuple(content.secondary_categories)
                if content is not None
                else ()
            ),
            tags=tuple(content.tags) if content is not None else (),
            one_sentence_summary=(
                content.one_sentence_summary if content is not None else None
            ),
            summary=content.summary if content is not None else None,
            viewpoints=(
                tuple(
                    Viewpoint(
                        statement=item.statement,
                        explanation=item.explanation,
                    )
                    for item in content.viewpoints
                )
                if content is not None
                else ()
            ),
            key_quotes=(
                tuple(
                    KeyQuote(text=item.text, context=item.context)
                    for item in content.key_quotes
                )
                if content is not None
                else ()
            ),
            total_score=score.total if score is not None else None,
            dimensions=(
                {
                    name: ScoreDimension(
                        value=item.value,
                        weight=item.weight,
                        reason=item.reason,
                    )
                    for name, item in score.dimensions.items()
                }
                if score is not None
                else {}
            ),
            recommendation_level=(
                content.recommendation_level if content is not None else None
            ),
            recommendation_reason=(
                content.recommendation_reason if content is not None else None
            ),
            provenance=provenance,
            created_at=run.completed_at or datetime.now(UTC),
        )
        try:
            return await self._analyses.add(analysis)
        except ValueError:
            concurrent = await self._analyses.get_by_identity(
                trigger_reference_id,
                trigger_revision,
                definition.id,
                definition.version,
            )
            if concurrent is None:
                raise
            return concurrent

    @staticmethod
    def _trigger_identity(run: WorkflowRun) -> tuple[uuid.UUID, int]:
        try:
            reference_id = uuid.UUID(str(run.trigger["reference_id"]))
            revision = int(str(run.trigger["revision"]))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "workflow trigger must contain reference_id and revision"
            ) from error
        if revision < 1:
            raise ValueError("workflow trigger revision must be positive")
        return reference_id, revision
