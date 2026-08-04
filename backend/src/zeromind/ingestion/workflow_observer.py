import uuid

from zeromind.ingestion.domain import AnalysisStatus
from zeromind.ingestion.lifecycle import ReferenceAnalysisLifecycleRepository
from zeromind.workflows.constants import MAIN_ANALYSIS_WORKFLOW_NAME
from zeromind.workflows.domain import WorkflowDefinition, WorkflowRun
from zeromind.workflows.dsl import NodeSpec

NODE_STATUSES: dict[str, AnalysisStatus] = {
    "screening": "screening",
    "resolve": "resolving",
    "core_analysis": "analyzing",
    "taxonomy": "classifying",
    "quality_scoring": "scoring",
    "review": "reviewing",
    "finalize": "finalizing",
    "deterministic_score": "finalizing",
    "fine_gate": "finalizing",
}
TERMINAL_OUTPUT_STATUSES: dict[str, AnalysisStatus] = {
    "initial_rejected": "initial_rejected",
    "fine_rejected": "fine_rejected",
    "qualified": "completed",
}


class ReferenceAnalysisLifecycleObserver:
    def __init__(
        self,
        lifecycle: ReferenceAnalysisLifecycleRepository,
    ) -> None:
        self._lifecycle = lifecycle

    @staticmethod
    def _identity(
        definition: WorkflowDefinition,
        run: WorkflowRun,
    ) -> tuple[uuid.UUID, int] | None:
        if definition.name != MAIN_ANALYSIS_WORKFLOW_NAME:
            return None
        try:
            reference_id = uuid.UUID(str(run.trigger["reference_id"]))
            revision = int(str(run.trigger["revision"]))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("main analysis trigger requires reference_id and revision") from error
        if revision < 1:
            raise ValueError("main analysis trigger revision must be positive")
        return reference_id, revision

    async def run_created(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
    ) -> None:
        identity = self._identity(definition, run)
        if identity is None:
            return
        reference_id, revision = identity
        changed = await self._lifecycle.transition(
            reference_id,
            revision=revision,
            status="queued",
            workflow_run_id=run.id,
        )
        if not changed:
            raise ValueError(f"stale reference analysis revision: {revision}")

    async def step_started(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
        node: NodeSpec,
    ) -> None:
        identity = self._identity(definition, run)
        status = NODE_STATUSES.get(node.id)
        if identity is None or status is None:
            return
        reference_id, revision = identity
        changed = await self._lifecycle.transition(
            reference_id,
            revision=revision,
            status=status,
            workflow_run_id=run.id,
        )
        if not changed:
            raise ValueError(f"stale reference analysis revision: {revision}")

    async def run_projected(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
    ) -> None:
        identity = self._identity(definition, run)
        if identity is None:
            return
        raw_status = run.output.get("status") if run.output else None
        status = TERMINAL_OUTPUT_STATUSES.get(str(raw_status))
        if status is None:
            raise ValueError(f"unsupported main analysis output status: {raw_status}")
        reference_id, revision = identity
        changed = await self._lifecycle.transition(
            reference_id,
            revision=revision,
            status=status,
            workflow_run_id=run.id,
        )
        if not changed:
            raise ValueError(f"stale reference analysis revision: {revision}")

    async def run_failed(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
        error: Exception,
    ) -> None:
        identity = self._identity(definition, run)
        if identity is None:
            return
        reference_id, revision = identity
        projection_invalid = bool(
            run.error and run.error.startswith("analysis_projection_invalid:")
        )
        changed = await self._lifecycle.transition(
            reference_id,
            revision=revision,
            status="failed",
            workflow_run_id=run.id,
            error_code=(
                "analysis_projection_invalid"
                if projection_invalid
                else "workflow_failed"
            ),
            error_message=run.error or str(error) or type(error).__name__,
        )
        if not changed:
            raise ValueError(f"stale reference analysis revision: {revision}")
