from zeromind.workflows.constants import (
    LEGACY_MAIN_ANALYSIS_WORKFLOW_NAMES,
    MAIN_ANALYSIS_WORKFLOW_NAME,
)
from zeromind.workflows.domain import WorkflowDefinition
from zeromind.workflows.dsl import WorkflowSpec
from zeromind.workflows.repository import WorkflowRepository


async def upsert_main_analysis_workflow(
    workflows: WorkflowRepository,
    spec: WorkflowSpec,
) -> WorkflowDefinition:
    if spec.name != MAIN_ANALYSIS_WORKFLOW_NAME:
        raise ValueError(
            f"analysis preset must be named {MAIN_ANALYSIS_WORKFLOW_NAME!r}"
        )
    definitions = await workflows.list_definitions()
    canonical = [
        item for item in definitions if item.name == MAIN_ANALYSIS_WORKFLOW_NAME
    ]
    legacy = [
        item
        for item in definitions
        if item.name in LEGACY_MAIN_ANALYSIS_WORKFLOW_NAMES
    ]
    if canonical and legacy:
        raise ValueError(
            "conflicting canonical and legacy main analysis workflows exist"
        )
    candidates = [*canonical, *legacy]
    if len(candidates) > 1:
        raise ValueError("multiple main analysis workflow candidates exist")
    if not candidates:
        workflow = WorkflowDefinition.create(spec)
        workflow.activate()
        await workflows.add_definition(workflow)
        return workflow

    workflow = candidates[0]
    if workflow.name != MAIN_ANALYSIS_WORKFLOW_NAME or workflow.spec != spec:
        workflow.name = MAIN_ANALYSIS_WORKFLOW_NAME
        workflow.spec = spec
        workflow.version += 1
    workflow.activate()
    await workflows.save_definition(workflow)
    return workflow
