from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

import pytest

from zeromind.ingestion.domain import AnalysisStatus
from zeromind.ingestion.lifecycle import AnalysisTransition
from zeromind.ingestion.workflow_observer import ReferenceAnalysisLifecycleObserver
from zeromind.workflows.constants import MAIN_ANALYSIS_WORKFLOW_NAME
from zeromind.workflows.domain import WorkflowDefinition, WorkflowRun
from zeromind.workflows.dsl import NodeSpec, WorkflowSpec

REFERENCE_ID = UUID("11111111-1111-1111-1111-111111111111")
RUN_ID = UUID("22222222-2222-2222-2222-222222222222")
NOW = datetime(2026, 8, 4, tzinfo=UTC)


@dataclass(slots=True)
class RecordingLifecycle:
    transitions: list[AnalysisTransition] = field(default_factory=list)

    async def transition(
        self,
        reference_id: UUID,
        *,
        revision: int,
        status: AnalysisStatus,
        workflow_run_id: UUID | None,
        error_code: str | None = None,
        error_message: str | None = None,
        now: datetime | None = None,
    ) -> bool:
        self.transitions.append(
            AnalysisTransition(
                reference_id=reference_id,
                revision=revision,
                status=status,
                workflow_run_id=workflow_run_id,
                error_code=error_code,
                error_message=error_message,
            )
        )
        return True


def _definition(name: str = MAIN_ANALYSIS_WORKFLOW_NAME) -> WorkflowDefinition:
    return WorkflowDefinition.create(
        WorkflowSpec.model_validate(
            {
                "name": name,
                "trigger": {"events": ["manual"]},
                "nodes": [{"id": "noop", "type": "parallel"}],
            }
        ),
        now=NOW,
    )


def _run(*, output_status: str | None = None) -> WorkflowRun:
    output = {"status": output_status} if output_status else None
    return WorkflowRun(
        id=RUN_ID,
        definition_id=UUID("33333333-3333-3333-3333-333333333333"),
        definition_version=1,
        idempotency_key="analysis:1",
        trigger={"reference_id": str(REFERENCE_ID), "revision": 3},
        status="completed" if output else "running",
        output=output,
        error=None,
        started_at=NOW,
        completed_at=NOW if output else None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("node_id", "expected"),
    [
        ("screening", "screening"),
        ("resolve", "resolving"),
        ("core_analysis", "analyzing"),
        ("taxonomy", "classifying"),
        ("quality_scoring", "scoring"),
        ("review", "reviewing"),
        ("finalize", "finalizing"),
        ("deterministic_score", "finalizing"),
        ("fine_gate", "finalizing"),
    ],
)
async def test_main_workflow_node_maps_to_reference_status(
    node_id: str,
    expected: AnalysisStatus,
) -> None:
    lifecycle = RecordingLifecycle()
    observer = ReferenceAnalysisLifecycleObserver(lifecycle)

    await observer.step_started(
        _definition(),
        _run(),
        NodeSpec.model_validate({"id": node_id, "type": "parallel"}),
    )

    assert lifecycle.transitions[-1].status == expected


@pytest.mark.asyncio
async def test_main_workflow_maps_created_projected_and_failed_states() -> None:
    lifecycle = RecordingLifecycle()
    observer = ReferenceAnalysisLifecycleObserver(lifecycle)
    definition = _definition()

    await observer.run_created(definition, _run())
    await observer.run_projected(definition, _run(output_status="qualified"))
    failed = _run()
    failed.status = "failed"
    failed.error = "provider timeout"
    await observer.run_failed(definition, failed, RuntimeError("provider timeout"))

    assert [item.status for item in lifecycle.transitions] == [
        "queued",
        "completed",
        "failed",
    ]
    assert lifecycle.transitions[-1].error_code == "workflow_failed"


@pytest.mark.asyncio
async def test_other_workflow_does_not_mutate_reference_state() -> None:
    lifecycle = RecordingLifecycle()
    observer = ReferenceAnalysisLifecycleObserver(lifecycle)
    definition = _definition("another-workflow")
    run = _run(output_status="qualified")

    await observer.run_created(definition, run)
    await observer.step_started(
        definition,
        run,
        NodeSpec.model_validate({"id": "screening", "type": "parallel"}),
    )
    await observer.run_projected(definition, run)

    assert lifecycle.transitions == []
