# Multi-Agent Analysis and Session Traceability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist six BestBlogs-inspired analysis agents on the configured GLM Provider, execute them as a structured workflow, and make every invocation traceable through immutable Agent versions and one-row-per-attempt sessions without storing article bodies.

**Architecture:** Split stable Agent identity from immutable execution versions, then record each workflow Agent attempt in `agent_sessions`. The workflow executor persists a step before invoking a context-aware handler; the Agent Gateway owns session start/finish transitions and transient-input sanitization while Pi remains stateless and tool-free. Six strict JSON Agent definitions feed a deterministic score and the existing `content_analysis_v1` projector.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL 16, jsonschema Draft 2020-12, pytest, TypeScript 5.8, React 19, TanStack Query 5, Vitest, Pi TypeScript runtime, Docker Compose.

## Global Constraints

- Implementation authority is `docs/superpowers/specs/2026-08-03-multi-agent-analysis-session-traceability-design.md`.
- Persist exactly six enabled analysis Agents bound to the existing enabled Provider named `GLM`.
- Keep system prompts on immutable Agent versions; do not copy system prompts into sessions.
- Use one `agent_sessions` table; do not add `agent_session_events`.
- Never persist resolved article text, webpage snapshots, Provider credentials, or raw invalid model responses.
- A successful session may persist the complete output only after JSON parsing, transient-data sanitization, and output validation succeed.
- The screening threshold is 30 and the final deterministic threshold is 70.
- Deterministic score weights remain relevance 20%, information value 25%, depth 20%, practicality 15%, novelty 10%, and clarity 10%.
- Pi remains in-memory, tool-free, and disposed after every invocation.
- Preserve compatibility for existing Agent IDs, existing two-Agent examples, activated workflows, and `content_analysis_v1` projections.
- The current worktree changes in `backend/init-sql/env.py`, `backend/src/zeromind/shared/migration_config.py`, and `backend/tests/test_migration_config.py` are unrelated user changes; never stage or modify them in this plan.
- Use test-driven development for every task: add a failing focused test, observe the expected failure, implement the smallest complete change, run the focused suite, then commit only the listed files.

---

## File Structure

### Agent identity and versions

- `backend/src/zeromind/agents/domain.py`: stable `AgentDefinition`, immutable `AgentVersion`, Provider Profile, and version creation rules.
- `backend/src/zeromind/agents/models.py`: SQLAlchemy models for stable Agent identities, immutable versions, Provider Profiles, and sessions.
- `backend/src/zeromind/agents/registry.py`: in-memory/SQL repositories plus registry operations that resolve or append versions atomically.
- `backend/src/zeromind/agents/api.py`: Agent creation, version creation, version history, enable/disable, discovery, and Provider endpoints.
- `backend/init-sql/versions/0010_agent_versions_and_sessions.py`: data-preserving schema migration from mutable definitions to immutable versions and sessions.

### Session traceability

- `backend/src/zeromind/agents/session_domain.py`: session states, execution context, and terminal transition rules.
- `backend/src/zeromind/agents/sanitization.py`: recursive article-body redaction, hashes, bounded errors, and secret-safe snapshots.
- `backend/src/zeromind/agents/session_repository.py`: in-memory and SQL session persistence/query implementations.
- `backend/src/zeromind/agents/session_api.py`: read-only session list/detail API.
- `backend/src/zeromind/agents/gateway.py`: version pinning, semantic validators, Provider execution, schema validation, and session lifecycle.

### Runtime and workflow

- `pi-runner/src/protocol.ts`: typed response diagnostics without raw invalid response bodies.
- `pi-runner/src/pi-executor.ts`: response hash/length generation and classified parse failures.
- `pi-runner/src/handler.ts`: stable failed event codes.
- `backend/src/zeromind/agents/pi_rpc.py`: classified Pi exceptions and response diagnostics.
- `backend/src/zeromind/workflows/executor.py`: typed node execution context and incremental step persistence.
- `backend/src/zeromind/workflows/repository.py`: add/save step operations; no delete-and-rebuild save path.
- `backend/src/zeromind/bootstrap/runtime.py`: context-aware Agent handler and session-aware Gateway construction.
- `backend/src/zeromind/bootstrap/app.py`: SQL/in-memory repositories and session router wiring.
- `backend/src/zeromind/bootstrap/celery.py`: periodic stale-session recovery schedule.
- `backend/src/zeromind/bootstrap/tasks.py`: recovery task and worker-side session repository wiring.

### Six-Agent pipeline artifacts

- `docs/examples/agents/01-screening.json`: RSS metadata screening contract.
- `docs/examples/agents/02-core-analysis.json`: summary, viewpoints, and quote extraction contract.
- `docs/examples/agents/03-taxonomy.json`: category probabilities and tags contract.
- `docs/examples/agents/04-quality-scoring.json`: six-dimensional scoring contract.
- `docs/examples/agents/05-review.json`: structured review issues contract.
- `docs/examples/agents/06-finalize.json`: final projection-ready content and update reasons contract.
- `docs/examples/multi-agent-article-analysis.yaml`: six-Agent workflow template with placeholder IDs.
- `backend/scripts/register_analysis_pipeline.py`: idempotent API client that resolves the enabled `GLM` Provider, registers/reuses all six Agents, and writes a concrete workflow source.

### Operator surfaces

- `frontend/src/api/client.ts`: Agent version and session API types.
- `frontend/src/pages/agents.tsx`: current-version cards and immutable version history.
- `frontend/src/pages/runs.tsx`: per-step session trace display.
- `frontend/src/styles.css`: version and session detail styling.
- `README.md`: six-Agent registration/activation flow.
- `docs/operations.md`: trace retention, recovery, and failure diagnosis.

---

### Task 1: Data-Preserving Agent Version and Session Migration

**Files:**

- Create: `backend/init-sql/versions/0010_agent_versions_and_sessions.py`
- Modify: `backend/src/zeromind/agents/models.py`
- Test: `backend/tests/agents/test_migration.py`

**Interfaces:**

- Produces tables `agent_versions` and `agent_sessions`.
- Produces stable columns `agent_definitions.current_version`, `name`, `description`, `enabled`, `created_at`, and `updated_at`.
- Preserves every existing `agent_definitions.id` and migrates its execution configuration into Agent version 1.
- Later tasks consume `AgentVersionModel` and `AgentSessionModel`.

- [ ] **Step 1: Write a failing migration preservation test**

Create a PostgreSQL-aware migration test that inserts one Provider, one mutable Agent, one workflow definition/run/step through revision `0009_notes`, upgrades to head, and asserts:

```python
assert row.agent_id == existing_agent_id
assert row.version == 1
assert row.system_prompt == "Return JSON."
assert stable.current_version == 1
assert inspector.has_table("agent_sessions")
assert "system_prompt" not in agent_definition_columns
```

The test must also downgrade to `0009_notes` and assert the current version fields are copied back into `agent_definitions`.

- [ ] **Step 2: Run the migration test and verify the missing revision failure**

Run:

```bash
cd backend
../.venv/bin/pytest tests/agents/test_migration.py -q
```

Expected: FAIL because revision `0010_agent_versions_and_sessions` and the new tables do not exist.

- [ ] **Step 3: Implement the Alembic upgrade**

Create revision `0010_agent_versions_and_sessions`, `down_revision = "0009_notes"`, with this order:

1. Create `agent_versions` with UUID primary key, `(agent_id, version)` unique constraint, JSON capabilities/schemas, text system prompt, Provider FK `RESTRICT`, and Agent FK `RESTRICT`.
2. Add non-null `current_version` to `agent_definitions` with temporary server default `1`.
3. Insert one `agent_versions` row per existing Agent using a deterministic PostgreSQL UUID expression or Python-generated UUID values bound through `op.bulk_insert`.
4. Drop the old Provider index and execution columns from `agent_definitions`: `capabilities`, `system_prompt`, `provider_profile_id`, `input_schema`, `output_schema`, and `version`.
5. Remove the temporary server default from `current_version`.
6. Create `agent_sessions` with the exact fields and foreign keys from the design, including `(step_run_id, attempt)` unique and indexes on run, Agent, version, status, and start time.

Use `ondelete="CASCADE"` for workflow run/step references and `ondelete="RESTRICT"` for Agent/version references.

- [ ] **Step 4: Implement the downgrade**

The downgrade must add the mutable execution columns back, copy the current `agent_versions` row into each Agent, drop `agent_sessions`, drop `agent_versions`, and drop `current_version`. It must preserve the existing Agent ID, name, description, enable state, and current execution configuration.

- [ ] **Step 5: Update SQLAlchemy models**

Define:

```python
class AgentVersionModel(Base):
    __tablename__ = "agent_versions"
    __table_args__ = (UniqueConstraint("agent_id", "version"),)

class AgentSessionModel(Base):
    __tablename__ = "agent_sessions"
    __table_args__ = (UniqueConstraint("step_run_id", "attempt"),)
```

Make `AgentDefinitionModel` stable-only and keep Provider Profile unchanged. Use JSON for sanitized input, output, and usage; allow output/completion/error fields to be null while running.

- [ ] **Step 6: Run migration and model tests**

Run:

```bash
cd backend
../.venv/bin/pytest tests/agents/test_migration.py tests/agents/test_repository.py -q
../.venv/bin/ruff check src/zeromind/agents/models.py init-sql/versions/0010_agent_versions_and_sessions.py tests/agents/test_migration.py
```

Expected: PASS; upgrade/downgrade preserves the Agent and configuration.

- [ ] **Step 7: Commit the migration**

```bash
git add backend/init-sql/versions/0010_agent_versions_and_sessions.py backend/src/zeromind/agents/models.py backend/tests/agents/test_migration.py
git commit -m "feat: add agent versions and sessions schema"
```

---

### Task 2: Immutable Agent Version Domain, Repository, and Registry

**Files:**

- Modify: `backend/src/zeromind/agents/domain.py`
- Modify: `backend/src/zeromind/agents/registry.py`
- Modify: `backend/tests/agents/test_registry.py`
- Modify: `backend/tests/agents/test_repository.py`

**Interfaces:**

- Produces `AgentVersion.create(agent_id, version, ...) -> AgentVersion`; `AgentDefinition.create(...) -> AgentDefinition` constructs stable identity and version 1 together while preserving the existing caller-facing creation arguments.
- Produces `AgentDefinition.current: AgentVersion` as the resolved execution configuration.
- Produces `AgentRegistry.get_agent_version(agent_id, version)`, `list_agent_versions(agent_id)`, and version-creating `update_agent`.
- Gateway and API tasks consume these interfaces.

- [ ] **Step 1: Write failing immutable-version domain tests**

Add tests proving:

```python
first = definition.current
second = definition.next_version(
    system_prompt="Return stricter JSON.",
    capabilities=("classify-content",),
    provider_profile_id=PROFILE_ID,
    input_schema={"type": "object"},
    output_schema={"type": "object"},
)
assert first.version == 1
assert first.system_prompt == "Return JSON."
assert second.version == 2
assert definition.current_version == 2
```

Also assert enable/disable changes no version and normalized capabilities remain sorted/lowercase.

- [ ] **Step 2: Write failing repository atomicity tests**

For both in-memory and SQL repositories, assert registration writes stable identity plus version 1, `append_version` writes version 2 without altering version 1, duplicate `(agent_id, version)` fails, and a missing Provider prevents version creation.

- [ ] **Step 3: Run focused tests and observe mutable-overwrite failures**

Run:

```bash
cd backend
../.venv/bin/pytest tests/agents/test_registry.py tests/agents/test_repository.py -q
```

Expected: FAIL because `AgentDefinition.update()` mutates the prompt and the repository has no version operations.

- [ ] **Step 4: Implement versioned domain objects**

Define immutable `AgentVersion` as a frozen dataclass with `id`, `agent_id`, `version`, capabilities, prompt, Provider binding, schemas, and created time. Keep `AgentDefinition` responsible for stable identity, enable state, current version number, and a resolved `current` version. `next_version()` returns a new `AgentVersion` and advances only `current_version`/`updated_at`.

- [ ] **Step 5: Refactor repository protocols and implementations**

Replace mutable `save_agent(definition)` with explicit operations:

```python
async def add_agent(self, definition: AgentDefinition) -> None: ...
async def append_agent_version(
    self, definition: AgentDefinition, version: AgentVersion
) -> None: ...
async def save_agent_state(self, definition: AgentDefinition) -> None: ...
async def get_agent_version(
    self, agent_id: UUID, version: int
) -> AgentVersion | None: ...
async def list_agent_versions(self, agent_id: UUID) -> tuple[AgentVersion, ...]: ...
```

SQL `append_agent_version` must insert the version and update `current_version` within one transaction. Repository reads must hydrate stable Agent plus its current version.

- [ ] **Step 6: Update AgentRegistry**

`register_agent` validates the Provider referenced by version 1. `update_agent` accepts all execution fields, validates the new Provider, appends the new version atomically, and returns the hydrated Agent. Enable/disable uses `save_agent_state` and discovery reads current-version capabilities.

- [ ] **Step 7: Run Agent domain/repository suites**

Run:

```bash
cd backend
../.venv/bin/pytest tests/agents/test_registry.py tests/agents/test_repository.py -q
../.venv/bin/mypy src/zeromind/agents/domain.py src/zeromind/agents/registry.py
```

Expected: PASS with immutable version history and unchanged enable semantics.

- [ ] **Step 8: Commit versioned Agent behavior**

```bash
git add backend/src/zeromind/agents/domain.py backend/src/zeromind/agents/registry.py backend/tests/agents/test_registry.py backend/tests/agents/test_repository.py
git commit -m "feat: preserve immutable agent versions"
```

---

### Task 3: Session Domain, Sanitization, and Persistence

**Files:**

- Create: `backend/src/zeromind/agents/session_domain.py`
- Create: `backend/src/zeromind/agents/sanitization.py`
- Create: `backend/src/zeromind/agents/session_repository.py`
- Create: `backend/tests/agents/test_sessions.py`
- Create: `backend/tests/agents/test_sanitization.py`

**Interfaces:**

- Produces `AgentExecutionContext(workflow_run_id, step_run_id, attempt)`.
- Produces `AgentSession.start(...)`, `complete(...)`, and `fail(...)` with one legal running-to-terminal transition.
- Produces `sanitize_agent_input(value) -> SanitizedAgentInput` and `bounded_error(message, secrets=()) -> str`.
- Produces `AgentSessionRepository.add`, `save`, `get`, `list`, and `fail_stale` methods consumed by Gateway/API/recovery tasks.

- [ ] **Step 1: Write failing sanitizer tests**

Cover nested dictionaries and arrays. Given:

```python
value = {
    "metadata": {"title": "Safe"},
    "document": {
        "_transient_document": True,
        "content_type": "text/markdown",
        "text": "ARTICLE BODY MUST NOT BE STORED",
    },
}
```

assert the result retains metadata but replaces the document with `sha256`, `character_count`, and `content_type`; assert neither the marker nor text exists anywhere in serialized output. Assert `bounded_error` replaces configured secrets, strips Authorization/API-key-like values, removes newlines, and limits output to 1000 characters.

- [ ] **Step 2: Write failing session transition/repository tests**

Assert a session starts with `running`, completes with validated output and usage, rejects a second terminal transition, records each retry as a distinct row, and supports filters by workflow run, Agent, status, and start range. Assert `fail_stale(before, now)` changes only older running rows to `protocol_failed` with error code `stale_session_recovered`. Run the same contract against in-memory and SQL repositories.

- [ ] **Step 3: Run focused tests and verify missing-module failures**

Run:

```bash
cd backend
../.venv/bin/pytest tests/agents/test_sanitization.py tests/agents/test_sessions.py -q
```

Expected: FAIL because session and sanitizer modules do not exist.

- [ ] **Step 4: Implement sanitization**

Return a dataclass:

```python
@dataclass(frozen=True, slots=True)
class SanitizedAgentInput:
    value: dict[str, object]
    document_sha256: str | None
    document_character_count: int | None
```

Recursively recognize `_transient_document is True`; hash UTF-8 text, count Unicode characters, retain only safe document metadata, and never mutate the caller input. Fail closed if a transient marker has a non-string `text` value.

- [ ] **Step 5: Implement session domain and repositories**

Use the exact terminal status literals from the design. `complete()` requires output, usage, response hash/count, and completion time. `fail()` requires an error code/message and optionally response hash/count. SQL updates must use `WHERE status = 'running'` and require exactly one affected row so concurrent double completion is rejected. `fail_stale` performs one bounded update over `status = 'running' AND started_at < before` and returns the affected-row count.

- [ ] **Step 6: Run focused tests and static checks**

Run:

```bash
cd backend
../.venv/bin/pytest tests/agents/test_sanitization.py tests/agents/test_sessions.py -q
../.venv/bin/ruff check src/zeromind/agents/session_domain.py src/zeromind/agents/sanitization.py src/zeromind/agents/session_repository.py tests/agents/test_sanitization.py tests/agents/test_sessions.py
../.venv/bin/mypy src/zeromind/agents/session_domain.py src/zeromind/agents/sanitization.py src/zeromind/agents/session_repository.py
```

Expected: PASS.

- [ ] **Step 7: Commit session persistence**

```bash
git add backend/src/zeromind/agents/session_domain.py backend/src/zeromind/agents/sanitization.py backend/src/zeromind/agents/session_repository.py backend/tests/agents/test_sanitization.py backend/tests/agents/test_sessions.py
git commit -m "feat: persist sanitized agent sessions"
```

---

### Task 4: Pi Response Diagnostics Without Invalid Raw Text

**Files:**

- Modify: `pi-runner/src/protocol.ts`
- Modify: `pi-runner/src/pi-executor.ts`
- Modify: `pi-runner/src/handler.ts`
- Modify: `pi-runner/src/protocol.test.ts`
- Modify: `pi-runner/src/handler.test.ts`
- Modify: `backend/src/zeromind/agents/pi_rpc.py`
- Modify: `backend/tests/agents/test_pi_rpc.py`

**Interfaces:**

- Produces Pi failure codes `provider_failed`, `json_invalid`, `protocol_failed`, and `cancelled` plus response SHA-256/count diagnostics.
- Adds response SHA-256/count diagnostics to successful completed events.
- Produces Python `PiRpcResult.response_sha256`/`response_character_count` and exception `PiExecutionError(code, message, response_sha256, response_character_count)`.
- Gateway consumes these classifications and never receives invalid raw response text.

- [ ] **Step 1: Write failing TypeScript tests for invalid JSON diagnostics**

Make the executor stub throw a classified error built from `not-json ARTICLE BODY MUST NOT BE STORED`. Assert the failed event contains `code: "json_invalid"`, a 64-character hash, and character count, while serialized event output does not contain `ARTICLE BODY`. Add a successful-output test asserting the completed event carries the exact raw assistant response hash and character count.

- [ ] **Step 2: Write failing Python RPC classification tests**

Feed JSONL events for `json_invalid`, `provider_failed`, and `protocol_failed`; assert the raised `PiExecutionError.code` and diagnostics match and no response body is retained.

- [ ] **Step 3: Run Pi and RPC tests to observe failures**

Run:

```bash
cd pi-runner
pnpm test -- protocol.test.ts handler.test.ts
cd ../backend
../.venv/bin/pytest tests/agents/test_pi_rpc.py -q
```

Expected: FAIL because every runner error is currently `pi_execution_failed` and Python discards the code.

- [ ] **Step 4: Implement classified runner errors**

Add a `RunnerFailure` class carrying code/hash/count. In `executeWithPi`, calculate hash/count from the raw assistant text before parsing and return both diagnostics on success; on JSON failure throw `RunnerFailure("json_invalid", "model returned invalid JSON", hash, count)` without retaining the raw response as a public field. Classify missing model/provider runtime failures as `provider_failed`; retain `invalid_request` for malformed RPC input.

- [ ] **Step 5: Extend failed RunnerEvent and Python exception mapping**

Add `response_sha256` and `response_character_count` to completed events and optional diagnostics to failed events. `safeMessage` continues credential redaction. Python validates known codes, maps unknown runner codes to `protocol_failed`, and exposes only safe messages and diagnostics.

- [ ] **Step 6: Run Pi and backend protocol suites**

Run:

```bash
cd pi-runner
pnpm test
pnpm typecheck
cd ../backend
../.venv/bin/pytest tests/agents/test_pi_rpc.py -q
```

Expected: PASS; invalid raw model text is absent from emitted events.

- [ ] **Step 7: Commit protocol diagnostics**

```bash
git add pi-runner/src/protocol.ts pi-runner/src/pi-executor.ts pi-runner/src/handler.ts pi-runner/src/protocol.test.ts pi-runner/src/handler.test.ts backend/src/zeromind/agents/pi_rpc.py backend/tests/agents/test_pi_rpc.py
git commit -m "feat: classify safe pi execution failures"
```

---

### Task 5: Session-Aware Agent Gateway and Semantic Validation

**Files:**

- Modify: `backend/src/zeromind/agents/gateway.py`
- Create: `backend/src/zeromind/agents/validators.py`
- Modify: `backend/tests/agents/test_gateway.py`
- Create: `backend/tests/agents/test_validators.py`

**Interfaces:**

- Changes `AgentGateway.execute(agent_id, input, *, context, timeout_seconds=120) -> AgentExecutionResult`.
- Pins `AgentVersion` before session creation and uses the same version for the attempt.
- Produces `validate_agent_semantics(capabilities, output) -> None`.
- Runtime wiring consumes the new execution context.

- [ ] **Step 1: Write failing Gateway session lifecycle tests**

Use in-memory Agent/session repositories and assert:

- success creates one completed session with sanitized input and complete validated output;
- Provider error creates `provider_failed`;
- timeout creates `timed_out`;
- invalid JSON diagnostics create `json_invalid` without raw output;
- output Schema failure creates `schema_invalid` without unsafe text;
- a session repository failure prevents the Pi client from being called;
- updating the Agent after invocation starts does not change the pinned version.

- [ ] **Step 2: Write failing taxonomy semantic tests**

For capability `classify-content`, reject probabilities totaling 99, a primary category that is not maximal, unknown category keys, booleans masquerading as integers, and duplicate tags. Accept exactly five integer probabilities totaling 100 with the primary category at the maximum.

- [ ] **Step 3: Run focused tests and observe missing context/session failures**

Run:

```bash
cd backend
../.venv/bin/pytest tests/agents/test_gateway.py tests/agents/test_validators.py -q
```

Expected: FAIL because Gateway does not accept execution context, persist sessions, or run semantic validators.

- [ ] **Step 4: Implement semantic validators**

Dispatch validators by capability. Define the exact allowed taxonomy categories as `人工智能`, `软件编程`, `产品设计`, `商业科技`, and `其他`. Raise `AgentOutputError` with bounded field-specific messages; do not include full input/output serialization.

- [ ] **Step 5: Implement Gateway session lifecycle**

The method order must be:

1. Resolve enabled stable Agent and current immutable version.
2. Resolve enabled Provider and validate input Schema.
3. Sanitize input and create `running` session.
4. Invoke Pi using the pinned version.
5. Validate output JSON Schema and named semantic rules.
6. Complete the session, then return execution result.
7. On each classified exception, transition the session once and re-raise the domain-level error.

Persist successful response hash/count from `PiRpcResult`; do not recompute them from parsed JSON because that would lose fidelity to the actual model response.

- [ ] **Step 6: Run Gateway tests and Agent suite**

Run:

```bash
cd backend
../.venv/bin/pytest tests/agents -q
../.venv/bin/ruff check src/zeromind/agents tests/agents
../.venv/bin/mypy src/zeromind/agents
```

Expected: PASS.

- [ ] **Step 7: Commit Gateway integration**

```bash
git add backend/src/zeromind/agents/gateway.py backend/src/zeromind/agents/validators.py backend/tests/agents/test_gateway.py backend/tests/agents/test_validators.py
git commit -m "feat: trace agent gateway executions"
```

---

### Task 6: Incremental Workflow Steps and Execution Context

**Files:**

- Modify: `backend/src/zeromind/workflows/executor.py`
- Modify: `backend/src/zeromind/workflows/repository.py`
- Modify: `backend/src/zeromind/bootstrap/runtime.py`
- Modify: `backend/src/zeromind/bootstrap/app.py`
- Modify: `backend/src/zeromind/bootstrap/celery.py`
- Modify: `backend/src/zeromind/bootstrap/tasks.py`
- Modify: `backend/tests/workflows/test_executor.py`
- Modify: `backend/tests/workflows/test_repository.py`
- Modify: `backend/tests/e2e/test_information_flow.py`
- Modify: `backend/tests/integration/test_schedule.py`

**Interfaces:**

- Produces `NodeExecutionContext(workflow_run_id, step_run_id, attempt)`.
- Changes `NodeHandler` to `Callable[[dict[str, object], NodeExecutionContext], Awaitable[dict[str, object]]]`.
- Produces repository methods `add_step(step)` and `save_step(step)`.
- Passes `AgentExecutionContext` into Gateway without embedding tracking IDs in model input.
- Produces Celery task `zeromind.recover_agent_sessions` that marks sessions running longer than 15 minutes as `protocol_failed` every 5 minutes.

- [ ] **Step 1: Write failing incremental persistence tests**

Assert the handler can reload its own running `StepRun` from the repository before returning, attempt 1 is persisted before the first call, attempt 2 is persisted before retry, completed steps survive a later-node crash, and `save_run` does not delete/reinsert step rows.

- [ ] **Step 2: Update executor test handlers to accept typed context**

Change test handlers from `async def handler(input)` to:

```python
async def handler(
    input: dict[str, object],
    context: NodeExecutionContext,
) -> dict[str, object]:
    assert context.attempt == 1
    return input
```

Add a test that context IDs never appear in persisted step input or Agent model input.

- [ ] **Step 3: Run workflow tests and observe signature/repository failures**

Run:

```bash
cd backend
../.venv/bin/pytest tests/workflows/test_executor.py tests/workflows/test_repository.py -q
```

Expected: FAIL because steps are only persisted when the run is saved and handlers receive only input.

- [ ] **Step 4: Add incremental repository operations**

Implement `add_step` and `save_step` for memory and SQL. SQL `save_run` updates only workflow-run columns; it must not execute `delete(StepRunModel)` or recreate steps. `_run_domain` continues loading ordered steps.

- [ ] **Step 5: Refactor WorkflowExecutor**

Create and add the running step before gate/handler execution. Before each attempt, update `attempts` and save. Save terminal state immediately after completion/failure. Pass a fresh `NodeExecutionContext` per attempt. Adapt gate execution to persist through the same repository lifecycle.

- [ ] **Step 6: Adapt runtime handlers**

All non-Agent handlers accept and ignore context explicitly. The Agent handler removes only `_agent_id`, constructs `AgentExecutionContext` from node context, and calls the session-aware Gateway. `build_workflow_executor` receives the shared `AgentSessionRepository`; application and worker construction pass the SQL/in-memory instance explicitly. Do not put run/step/attempt values into the LLM input dictionary.

- [ ] **Step 7: Add periodic stale-session recovery**

Register `zeromind.recover_agent_sessions` on the `events` queue with a 300-second beat schedule. Its async implementation creates the database, calls `SqlAlchemyAgentSessionRepository.fail_stale(before=now - timedelta(minutes=15), now=now)`, returns the affected count, and always disposes the database. Add an integration test with old-running, recent-running, and completed sessions proving only the old-running row changes.

- [ ] **Step 8: Run workflow, application, and recovery suites**

Run:

```bash
cd backend
../.venv/bin/pytest tests/workflows tests/e2e/test_information_flow.py tests/integration/test_schedule.py tests/test_health.py -q
../.venv/bin/mypy src/zeromind/workflows src/zeromind/bootstrap/runtime.py
```

Expected: PASS; transient body removal remains proven.

- [ ] **Step 9: Commit incremental execution and recovery**

```bash
git add backend/src/zeromind/workflows/executor.py backend/src/zeromind/workflows/repository.py backend/src/zeromind/bootstrap/runtime.py backend/src/zeromind/bootstrap/app.py backend/src/zeromind/bootstrap/celery.py backend/src/zeromind/bootstrap/tasks.py backend/tests/workflows/test_executor.py backend/tests/workflows/test_repository.py backend/tests/e2e/test_information_flow.py backend/tests/integration/test_schedule.py
git commit -m "feat: persist workflow steps incrementally"
```

---

### Task 7: Version and Session APIs with Application Wiring

**Files:**

- Modify: `backend/src/zeromind/agents/api.py`
- Create: `backend/src/zeromind/agents/session_api.py`
- Modify: `backend/src/zeromind/bootstrap/app.py`
- Modify: `backend/tests/agents/test_api.py`
- Create: `backend/tests/agents/test_session_api.py`

**Interfaces:**

- Produces `GET /api/v1/agents/{agent_id}/versions`.
- Extends `PATCH /api/v1/agents/{agent_id}` to accept prompt, capabilities, Provider Profile ID, input Schema, and output Schema and create one version.
- Produces `GET /api/v1/agent-sessions` and `GET /api/v1/agent-sessions/{session_id}`.
- Frontend consumes stable Agent/current-version and session responses.

- [ ] **Step 1: Write failing Agent version API tests**

Assert create returns `current_version: 1`; patch returns version 2 and accepts all execution fields; version history returns `[1, 2]` with full immutable configuration; enable/disable does not add version 3; missing Agent and Provider return stable 404/422 codes.

- [ ] **Step 2: Write failing session API tests**

Assert list filtering by `workflow_run_id`, `agent_id`, `status`, `started_from`, and `started_to`; detail returns sanitized input, output, usage, timing, and version reference; unknown session returns `agent_session_not_found`; response contains neither body marker nor credential.

- [ ] **Step 3: Run API tests and observe missing endpoint failures**

Run:

```bash
cd backend
../.venv/bin/pytest tests/agents/test_api.py tests/agents/test_session_api.py -q
```

Expected: FAIL because version history/session endpoints do not exist and patch accepts only prompt/capabilities.

- [ ] **Step 4: Implement Pydantic responses and routes**

Expose stable Agent fields plus resolved current version for existing clients. `AgentVersionResponse` includes all immutable fields except Provider secret values. `AgentSessionResponse` includes the design fields but never system prompt; clients retrieve prompt through the referenced Agent version.

- [ ] **Step 5: Wire repositories and Gateway in create_app**

Reuse the session repository already constructed for Gateway wiring in Task 6 and inject that same instance into the session router. Do not create an independent in-memory repository that would split writes from reads.

- [ ] **Step 6: Run API, authentication, and application tests**

Run:

```bash
cd backend
../.venv/bin/pytest tests/agents tests/identity tests/test_health.py -q
../.venv/bin/ruff check src/zeromind/agents src/zeromind/bootstrap/app.py tests/agents
```

Expected: PASS and all new endpoints remain protected by the existing administrator middleware.

- [ ] **Step 7: Commit APIs and wiring**

```bash
git add backend/src/zeromind/agents/api.py backend/src/zeromind/agents/session_api.py backend/src/zeromind/bootstrap/app.py backend/tests/agents/test_api.py backend/tests/agents/test_session_api.py
git commit -m "feat: expose agent versions and sessions"
```

---

### Task 8: Six Strict Agent Definitions, Workflow, and Registration Script

**Files:**

- Create: `docs/examples/agents/01-screening.json`
- Create: `docs/examples/agents/02-core-analysis.json`
- Create: `docs/examples/agents/03-taxonomy.json`
- Create: `docs/examples/agents/04-quality-scoring.json`
- Create: `docs/examples/agents/05-review.json`
- Create: `docs/examples/agents/06-finalize.json`
- Create: `docs/examples/multi-agent-article-analysis.yaml`
- Create: `backend/scripts/register_analysis_pipeline.py`
- Create: `backend/tests/e2e/test_multi_agent_examples.py`

**Interfaces:**

- Produces six API-ready Agent definitions with placeholder Provider UUID `00000000-0000-0000-0000-000000000100`.
- Produces workflow placeholder Agent UUIDs ending `201` through `206` in execution order.
- Produces `register_analysis_pipeline(base_url, token, provider_name, output_path) -> RegistrationResult`.
- Live registration in Task 10 consumes the script.

- [ ] **Step 1: Write failing artifact contract tests**

Load all six JSON files and assert unique names/capabilities, strict object schemas with `additionalProperties: false`, placeholder Provider ID, exact required fields, length/count limits, and six scoring dimensions. Parse the YAML, replace placeholders with test Agent IDs, validate it, and assert topological order:

```python
(
    "reference", "screening", "initial_gate", "resolve",
    "core_analysis", "taxonomy", "quality_scoring", "review",
    "finalize", "deterministic_score", "fine_gate",
)
```

Assert the projection maps only finalizer projection fields and excludes `update_reasons`.

- [ ] **Step 2: Write failing registration idempotency tests**

Use an `httpx.MockTransport` and assert the script:

- selects exactly one enabled Provider named `GLM`;
- reuses an identical existing Agent;
- rejects a same-name/different-config Agent without patching it;
- does not print API keys or token;
- writes concrete YAML only after all six Agent IDs resolve;
- validates, creates, and activates the workflow in that order when `--activate` is supplied.

- [ ] **Step 3: Run artifact tests and observe missing-file failures**

Run:

```bash
cd backend
../.venv/bin/pytest tests/e2e/test_multi_agent_examples.py -q
```

Expected: FAIL because the six definitions, workflow, and script do not exist.

- [ ] **Step 4: Create the six exact Agent contracts**

Use these stable names and capabilities:

| File | Name | Capability |
|---|---|---|
| `01-screening.json` | `RSS 元数据初筛` | `screen-content` |
| `02-core-analysis.json` | `文章核心分析` | `extract-content-insights` |
| `03-taxonomy.json` | `领域与标签分析` | `classify-content` |
| `04-quality-scoring.json` | `文章质量评分` | `score-content-quality` |
| `05-review.json` | `分析审核反思` | `review-content-analysis` |
| `06-finalize.json` | `最终分析优化` | `finalize-content-analysis` |

Each system prompt must state its sole responsibility, source-grounding rule, dynamic audience behavior, Chinese output preference while preserving technical terms, and JSON-only requirement. Intermediate inputs explicitly include the complete prior structured objects they consume. Only document-using inputs accept the transient `document` object.

- [ ] **Step 5: Create the workflow YAML**

Use audience literal `AI 与软件开发者，关注工程实践、技术原理、开发工具、可复用方法、产品落地和重要行业变化。`, screening gate 30, deterministic weights from Global Constraints, and final gate 70. On initial rejection project reference/screening only; on fine rejection and qualification map finalizer content fields, `$.steps.finalize._execution`, and deterministic score. Do not map `update_reasons` into `content_analysis_v1`.

- [ ] **Step 6: Implement the idempotent registration script**

Use standard library `argparse`, `json`, `pathlib`, and `urllib.request` so runtime dependencies do not change. Accept `--base-url`, `--token-env` defaulting to `ZEROMIND_ADMIN_TOKEN`, `--provider-name` defaulting to `GLM`, `--output`, and `--activate`. Compare canonical JSON for existing Agent configurations and emit only names/IDs/statuses.

- [ ] **Step 7: Run artifact tests and formatting checks**

Run:

```bash
cd backend
../.venv/bin/pytest tests/e2e/test_multi_agent_examples.py -q
../.venv/bin/ruff check scripts/register_analysis_pipeline.py tests/e2e/test_multi_agent_examples.py
```

Expected: PASS; JSON and YAML parse strictly and the script is idempotent.

- [ ] **Step 8: Commit pipeline artifacts**

```bash
git add docs/examples/agents docs/examples/multi-agent-article-analysis.yaml backend/scripts/register_analysis_pipeline.py backend/tests/e2e/test_multi_agent_examples.py
git commit -m "feat: define six-agent analysis pipeline"
```

---

### Task 9: Agent Version and Session Trace UI

**Files:**

- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/agents.tsx`
- Modify: `frontend/src/pages/runs.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/app.test.tsx`

**Interfaces:**

- Consumes Agent version/session endpoints from Task 7.
- Produces an Agent version-history inspector and workflow-run session trace inspector.
- Does not expose editing for historical versions or sessions.

- [ ] **Step 1: Write failing UI tests**

Mock API results and assert:

- Agent cards show `v2` and a “查看版本” action;
- opening history renders versions newest-first with Provider/model reference, capabilities, system prompt, and schemas;
- run selection fetches `/agent-sessions?workflow_run_id=<id>`;
- each session shows Agent name/version, attempt, status, Provider/model, tokens, cost, duration, sanitized input, output, and bounded error;
- no raw document marker is rendered;
- historical rows and sessions have no save/delete actions.

- [ ] **Step 2: Run the focused frontend test and observe failures**

Run:

```bash
cd frontend
pnpm test -- app.test.tsx
```

Expected: FAIL because types and UI queries for versions/sessions do not exist.

- [ ] **Step 3: Add API types**

Define `AgentVersion` and `AgentSession` with exact backend fields. Keep `Agent.version` as a compatibility alias only if backend still returns it; prefer `current_version` in new components.

- [ ] **Step 4: Implement Agent history UI**

Use local selected-Agent state and TanStack Query keyed by `['agent-versions', agentId]`. Render immutable prompt/schema details in a disclosure panel or modal using existing `Panel`, `Status`, and form typography; do not add a new UI dependency.

- [ ] **Step 5: Implement session trace UI**

Fetch sessions only for the selected run, group by step ID, sort by attempt, and render a compact trace below the step timeline. JSON blocks must use the already-sanitized API data and wrap long content.

- [ ] **Step 6: Run frontend verification**

Run:

```bash
cd frontend
pnpm test
pnpm typecheck
pnpm build
```

Expected: PASS.

- [ ] **Step 7: Commit UI support**

```bash
git add frontend/src/api/client.ts frontend/src/pages/agents.tsx frontend/src/pages/runs.tsx frontend/src/styles.css frontend/src/app.test.tsx
git commit -m "feat: show agent versions and sessions"
```

---

### Task 10: End-to-End Verification, Documentation, and Live Registration

**Files:**

- Modify: `backend/tests/e2e/test_information_flow.py`
- Modify: `README.md`
- Modify: `docs/operations.md`

**Interfaces:**

- Verifies all spec acceptance criteria across database, Gateway, workflow, projection, API, and UI.
- Registers the six production Agent rows against the existing enabled `GLM` Provider after migration.
- Produces the concrete workflow source for administrator validation/activation.

- [ ] **Step 1: Extend the end-to-end information-flow test**

Use six deterministic Fake Pi outputs and assert:

```python
assert [session.status for session in sessions] == ["completed"] * 6
assert [session.attempt for session in sessions] == [1] * 6
assert analysis.provenance["screening"].agent_version == 1
assert analysis.provenance["analysis"].agent_version == 1
assert "ARTICLE BODY MUST NOT BE STORED" not in serialized_database_state
```

Add a screening-rejection case with exactly one session and no resolver call. Add a retry case with two sessions for the same step and attempts `[1, 2]`.

- [ ] **Step 2: Run E2E tests and fix only integration defects**

Run:

```bash
cd backend
../.venv/bin/pytest tests/e2e/test_information_flow.py tests/e2e/test_multi_agent_examples.py -q
```

Expected: PASS. If an integration defect appears, add its regression assertion to the same test before changing implementation.

- [ ] **Step 3: Update README**

Replace the two-Agent first-run instructions with the registration script command, explain the six responsibilities, identify `GLM` as the selected Provider name, show validation before activation, and retain the no-body/no-secret guarantee. Keep the original two-Agent examples documented as legacy-compatible examples rather than the recommended pipeline.

- [ ] **Step 4: Update operations guidance**

Document immutable version lookup, session status meanings, running-session crash recovery, retention/index considerations, retry interpretation, taxonomy semantic failures, and commands for confirming no body/credential leakage. State explicitly that deleting Agent versions or sessions manually is unsupported.

- [ ] **Step 5: Run the complete repository verification**

Run:

```bash
cd backend
../.venv/bin/pytest -q
../.venv/bin/ruff check src tests scripts
../.venv/bin/mypy src
cd ../pi-runner
pnpm test
pnpm typecheck
pnpm build
cd ../frontend
pnpm test
pnpm typecheck
pnpm build
cd ..
git diff --check
```

Expected: every command exits 0. Confirm `git status --short` still shows the three pre-existing migration-config files as the user's separate changes unless the user has changed them independently.

- [ ] **Step 6: Commit documentation and final E2E coverage**

```bash
git add backend/tests/e2e/test_information_flow.py README.md docs/operations.md
git commit -m "docs: operate multi-agent analysis tracing"
```

- [ ] **Step 7: Rebuild and migrate the local Compose deployment**

Run:

```bash
docker compose build api worker scheduler frontend
docker compose up -d postgres redis api worker scheduler frontend
docker compose exec api alembic upgrade head
docker compose ps
```

Expected: API is healthy, worker/scheduler are running, and migration head is `0010_agent_versions_and_sessions`.

- [ ] **Step 8: Register six Agents against GLM without exposing credentials**

Authenticate through `/api/v1/auth/token` using `.env` values in shell variables without printing them, export the access token only for the registration process, and run:

```bash
cd backend
ZEROMIND_ADMIN_TOKEN="$zm_access_token" ../.venv/bin/python scripts/register_analysis_pipeline.py \
  --base-url http://localhost:8080/api/v1 \
  --provider-name GLM \
  --output /tmp/zeromind-multi-agent-article-analysis.yaml
```

Expected: six names and UUIDs are reported as created/reused; no token or Provider credential is printed. Do not activate automatically until validation succeeds.

- [ ] **Step 9: Validate database registration and workflow source**

Call authenticated `GET /providers` and `GET /agents`; assert one enabled `GLM` Provider and exactly six enabled Agent names from Task 8 bound to its ID. POST `/tmp/zeromind-multi-agent-article-analysis.yaml` to `/workflows/validate`; assert projection `content_analysis_v1`, terminal gates `initial_gate` and `fine_gate`, and no validation errors. Then POST the same source to `/workflows`, activate the returned definition ID, and verify it is the only active workflow with that name.

- [ ] **Step 10: Perform the completion audit**

Inspect authoritative evidence for every design acceptance criterion:

- six database Agent rows and six version-1 rows;
- Agent patch creates version 2 while version 1 remains queryable, then restore desired current config by creating version 3 rather than deleting history;
- one manual successful workflow run has six completed sessions;
- one forced low-score run has one session and no resolved body;
- every session links to run, step, Agent, version, Provider, and model;
- API/UI show sanitized input, valid output, usage, duration, and errors;
- database text/JSON search finds neither the test body marker nor Provider credential;
- existing legacy Agents/workflows still load after migration.

Do not declare completion unless each item has direct current-state evidence.

---

## Execution Notes

- Execute tasks in order because migrations and immutable version interfaces are prerequisites for sessions, Gateway wiring, and live registration.
- Each task is independently reviewable and has a focused test gate before its commit.
- Task 10 is the only task authorized to mutate the live local ZeroMind database; prior tasks change code, tests, and documentation only.
- Never stage the unrelated migration-config files listed in Global Constraints.
