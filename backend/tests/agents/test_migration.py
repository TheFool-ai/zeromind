from sqlalchemy import inspect

from zeromind.agents.models import (
    AgentDefinitionModel,
    AgentSessionModel,
    AgentVersionModel,
)


def test_agent_models_split_stable_identity_versions_and_sessions() -> None:
    stable = {column.name for column in inspect(AgentDefinitionModel).columns}
    version = {column.name for column in inspect(AgentVersionModel).columns}
    session = {column.name for column in inspect(AgentSessionModel).columns}

    assert stable == {
        "id",
        "name",
        "description",
        "enabled",
        "current_version",
        "created_at",
        "updated_at",
    }
    assert version == {
        "id",
        "agent_id",
        "version",
        "capabilities",
        "system_prompt",
        "provider_profile_id",
        "input_schema",
        "output_schema",
        "created_at",
    }
    assert session == {
        "id",
        "workflow_run_id",
        "step_run_id",
        "agent_id",
        "agent_version_id",
        "attempt",
        "provider",
        "model",
        "thinking_level",
        "sanitized_input",
        "document_sha256",
        "document_character_count",
        "output",
        "response_sha256",
        "response_character_count",
        "usage",
        "status",
        "error_code",
        "error_message",
        "started_at",
        "completed_at",
    }


def test_agent_versions_and_sessions_have_traceability_constraints() -> None:
    version_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in AgentVersionModel.__table__.constraints
        if hasattr(constraint, "columns")
    }
    session_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in AgentSessionModel.__table__.constraints
        if hasattr(constraint, "columns")
    }

    assert ("agent_id", "version") in version_constraints
    assert ("step_run_id", "attempt") in session_constraints
