# Reference Analysis Lifecycle and Reading Detail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every content reference a revision-safe analysis lifecycle driven by the six-Agent main workflow, backfill all historical references, and deliver a BestBlogs-inspired reading detail with embedded original content and structured analysis.

**Architecture:** `ContentReference` owns a single current lifecycle projection guarded by `current_revision`. A generic workflow observer emits run and step lifecycle callbacks; a reference-specific observer maps the main workflow nodes to reference states and writes terminal states only after analysis projection succeeds. Read APIs aggregate the current revision with the current main-workflow analysis, while the frontend renders an enriched reference list and a two-column reader without persisting or proxying article bodies.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Alembic, PostgreSQL 16, Celery/Redis, React 19, TypeScript, TanStack Query, Vitest, pytest.

## Global Constraints

- The only status-writing workflow is the active `content_analysis_v1` workflow named `信息分析工作流`.
- Rename the existing `bestblogs-six-agent-analysis` definition in place and retain its UUID.
- Store only the current reference status; do not add a status-event table or per-revision status history.
- Every status mutation must compare the workflow revision with `content_references.current_revision`.
- RSS discovery defaults to `pending`; every new RSS revision resets the reference to `pending` and clears prior run/error timing fields.
- Persisted statuses are exactly `pending`, `queued`, `screening`, `resolving`, `analyzing`, `classifying`, `scoring`, `reviewing`, `finalizing`, `initial_rejected`, `fine_rejected`, `completed`, and `failed`.
- `initial_rejected` and `fine_rejected` are normal business outcomes and must not carry technical errors.
- A reference becomes `completed` or rejected only after `content_analysis_v1` projection succeeds.
- Do not persist, proxy, rewrite, or cache article bodies or source HTML.
- The iframe must use the normalized HTTP(S) current-revision URL and a sandbox without top-navigation permission.
- Existing workflow runs and agent sessions remain the execution audit source.
- Use TDD, keep unrelated user changes intact, and commit each task independently.

---

### Task 1: Reference lifecycle domain and database migration

**Files:**
- Create: `backend/init-sql/versions/0011_reference_analysis_lifecycle.py`
- Modify: `backend/src/zeromind/ingestion/domain.py`
- Modify: `backend/src/zeromind/ingestion/models.py`
- Modify: `backend/src/zeromind/ingestion/service.py`
- Modify: `backend/src/zeromind/ingestion/repository.py`
- Modify: `backend/init-sql/env.py`
- Test: `backend/tests/ingestion/test_domain.py`
- Test: `backend/tests/ingestion/test_service.py`
- Test: `backend/tests/ingestion/test_repository.py`
- Test: `backend/tests/ingestion/test_migration.py`

**Interfaces:**
- Produces: `AnalysisStatus`, `PROCESSING_ANALYSIS_STATUSES`, `TERMINAL_ANALYSIS_STATUSES`.
- Produces: `ContentReference.reset_analysis(revision: int, now: datetime) -> None`.
- Produces: lifecycle fields on `ContentReference` and `ContentReferenceModel`.
- Later tasks consume the exact field and status names defined here.

- [ ] **Step 1: Write failing domain tests for defaults, reset, and status validation**

```python
def test_new_reference_starts_pending_for_current_revision() -> None:
    reference = ContentReference.create(
        subscription_id=SUBSCRIPTION_ID,
        identity_key="guid:one",
        original_url="https://example.com/one",
        now=NOW,
    )
    assert reference.analysis_status == "pending"
    assert reference.analysis_status_revision == 1
    assert reference.analysis_workflow_run_id is None


def test_new_revision_resets_analysis_projection() -> None:
    reference = analyzed_reference(status="completed", revision=1)
    reference.current_revision = 2
    reference.reset_analysis(revision=2, now=LATER)
    assert reference.analysis_status == "pending"
    assert reference.analysis_status_revision == 2
    assert reference.analysis_workflow_run_id is None
    assert reference.analysis_error_code is None
    assert reference.analysis_started_at is None
    assert reference.analysis_completed_at is None
```

- [ ] **Step 2: Run the focused tests and confirm missing lifecycle fields fail**

Run: `cd backend && ../.venv/bin/pytest tests/ingestion/test_domain.py tests/ingestion/test_service.py -q`

Expected: FAIL because `ContentReference` has no analysis lifecycle fields or reset method.

- [ ] **Step 3: Add lifecycle types, fields, creation helper, and reset behavior**

```python
AnalysisStatus = Literal[
    "pending", "queued", "screening", "resolving", "analyzing",
    "classifying", "scoring", "reviewing", "finalizing",
    "initial_rejected", "fine_rejected", "completed", "failed",
]
PROCESSING_ANALYSIS_STATUSES = frozenset({
    "queued", "screening", "resolving", "analyzing", "classifying",
    "scoring", "reviewing", "finalizing",
})
TERMINAL_ANALYSIS_STATUSES = frozenset({
    "initial_rejected", "fine_rejected", "completed", "failed",
})
```

Add the eight fields from the design to `ContentReference`. Replace direct construction in `IngestionService` with `ContentReference.create(...)`. In `add_revision`, call `reset_analysis(revision=reference.current_revision, now=fetched_at)` before saving.

- [ ] **Step 4: Write a failing migration/model test for exact columns, defaults, indexes, and check constraint**

```python
def test_content_reference_has_analysis_lifecycle_columns() -> None:
    columns = {column.name for column in inspect(ContentReferenceModel).columns}
    assert {
        "analysis_status", "analysis_status_revision",
        "analysis_workflow_run_id", "analysis_error_code",
        "analysis_error_message", "analysis_status_updated_at",
        "analysis_started_at", "analysis_completed_at",
    }.issubset(columns)
```

Assert a status index, updated-at index, workflow-run `SET NULL` foreign key, and a named status check constraint.

- [ ] **Step 5: Implement model mappings and migration `0011`**

The migration must add nullable columns first, backfill every existing row with:

```sql
analysis_status = 'pending',
analysis_status_revision = current_revision,
analysis_status_updated_at = CURRENT_TIMESTAMP
```

Then make status, status revision, and status timestamp non-null. Add `ck_content_reference_analysis_status`, indexes on status and status-updated-at, and the workflow run foreign key with `ON DELETE SET NULL`. Import `ContentReferenceModel`, `WorkflowRunModel`, and all newly referenced models from `init-sql/env.py`.

- [ ] **Step 6: Round-trip all fields through in-memory and SQL repositories**

Update `_reference_to_domain`, `_reference_model`, `add_revision`, and in-memory copies. Verify a new revision clears old lifecycle data in both implementations.

- [ ] **Step 7: Run ingestion, migration, Ruff, and mypy checks**

Run:

```bash
cd backend
../.venv/bin/pytest tests/ingestion tests/agents/test_migration.py tests/test_migration_config.py -q
../.venv/bin/ruff check init-sql src/zeromind/ingestion tests/ingestion
../.venv/bin/mypy src/zeromind/ingestion
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/init-sql backend/src/zeromind/ingestion backend/tests/ingestion
git commit -m "feat: add reference analysis lifecycle"
```

---

### Task 2: Revision-safe lifecycle repository

**Files:**
- Create: `backend/src/zeromind/ingestion/lifecycle.py`
- Modify: `backend/src/zeromind/ingestion/repository.py`
- Test: `backend/tests/ingestion/test_lifecycle.py`
- Test: `backend/tests/ingestion/test_repository.py`

**Interfaces:**
- Produces: `AnalysisTransition` dataclass.
- Produces: `ReferenceAnalysisLifecycleRepository.transition(...) -> bool`.
- Task 5 composes this transition interface with the outbox queue; no enqueue behavior belongs in this repository.
- The boolean result is `False` only for a stale revision; missing references raise `KeyError`.

- [ ] **Step 1: Write failing transition tests**

```python
@pytest.mark.asyncio
async def test_transition_updates_matching_revision() -> None:
    changed = await lifecycle.transition(
        reference.id,
        revision=2,
        status="screening",
        workflow_run_id=RUN_ID,
        now=NOW,
    )
    assert changed is True
    assert (await references.get_reference(reference.id)).analysis_status == "screening"


@pytest.mark.asyncio
async def test_transition_ignores_stale_revision() -> None:
    changed = await lifecycle.transition(
        reference.id,
        revision=1,
        status="completed",
        workflow_run_id=OLD_RUN_ID,
        now=NOW,
    )
    assert changed is False
    assert (await references.get_reference(reference.id)).analysis_status == "pending"
```

Add tests that rejected/completed clear errors, failed requires error code/message, queued sets `analysis_started_at`, and terminal states set `analysis_completed_at`.

- [ ] **Step 2: Run tests and verify the lifecycle repository is missing**

Run: `cd backend && ../.venv/bin/pytest tests/ingestion/test_lifecycle.py -q`

Expected: collection FAIL for missing `zeromind.ingestion.lifecycle`.

- [ ] **Step 3: Implement transition validation and in-memory repository**

```python
@dataclass(frozen=True, slots=True)
class AnalysisTransition:
    reference_id: uuid.UUID
    revision: int
    status: AnalysisStatus
    workflow_run_id: uuid.UUID | None
    error_code: str | None = None
    error_message: str | None = None


class ReferenceAnalysisLifecycleRepository(Protocol):
    async def transition(
        self,
        reference_id: uuid.UUID,
        *,
        revision: int,
        status: AnalysisStatus,
        workflow_run_id: uuid.UUID | None,
        error_code: str | None = None,
        error_message: str | None = None,
        now: datetime | None = None,
    ) -> bool: ...
```

Validate status-specific fields before repository mutation. Apply bounded error sanitization for `failed`.

- [ ] **Step 4: Implement one-statement SQL compare-and-set**

Use SQLAlchemy `update(ContentReferenceModel).where(id == ..., current_revision == revision, analysis_status_revision == revision).values(...)` and inspect `rowcount`. If `rowcount == 0`, perform a lookup: raise `KeyError` if absent, otherwise return `False`.

- [ ] **Step 5: Run focused tests, static checks, and concurrency integration test**

Run:

```bash
cd backend
../.venv/bin/pytest tests/ingestion/test_lifecycle.py tests/ingestion/test_repository.py -q
../.venv/bin/ruff check src/zeromind/ingestion/lifecycle.py tests/ingestion/test_lifecycle.py
../.venv/bin/mypy src/zeromind/ingestion/lifecycle.py
```

Expected: all pass; the stale update test proves revision safety.

- [ ] **Step 6: Commit**

```bash
git add backend/src/zeromind/ingestion backend/tests/ingestion
git commit -m "feat: enforce revision-safe analysis transitions"
```

---

### Task 3: Generic workflow lifecycle observer and main-flow mapping

**Files:**
- Create: `backend/src/zeromind/workflows/observer.py`
- Create: `backend/src/zeromind/ingestion/workflow_observer.py`
- Modify: `backend/src/zeromind/workflows/executor.py`
- Modify: `backend/src/zeromind/workflows/service.py`
- Modify: `backend/src/zeromind/bootstrap/runtime.py`
- Modify: `backend/src/zeromind/bootstrap/app.py`
- Modify: `backend/src/zeromind/bootstrap/tasks.py`
- Test: `backend/tests/workflows/test_observer.py`
- Test: `backend/tests/workflows/test_executor.py`
- Test: `backend/tests/workflows/test_service.py`
- Test: `backend/tests/ingestion/test_workflow_observer.py`

**Interfaces:**
- Produces: `WorkflowLifecycleObserver` protocol with `run_created`, `step_started`, `run_projected`, and `run_failed`.
- Produces: `NullWorkflowLifecycleObserver`.
- Produces: `ReferenceAnalysisLifecycleObserver` mapping the exact main-workflow nodes.
- Consumes: `ReferenceAnalysisLifecycleRepository.transition` from Task 2.

- [ ] **Step 1: Write failing observer contract tests**

```python
class WorkflowLifecycleObserver(Protocol):
    async def run_created(self, definition: WorkflowDefinition, run: WorkflowRun) -> None: ...
    async def step_started(self, definition: WorkflowDefinition, run: WorkflowRun, node: NodeSpec) -> None: ...
    async def run_projected(self, definition: WorkflowDefinition, run: WorkflowRun) -> None: ...
    async def run_failed(self, definition: WorkflowDefinition, run: WorkflowRun, error: Exception) -> None: ...
```

Assert `step_started` fires after `StepRun` persistence and before handler execution. Assert `run_projected` fires after projector success, not when executor merely returns completed output.

- [ ] **Step 2: Run workflow tests and confirm observer support is absent**

Run: `cd backend && ../.venv/bin/pytest tests/workflows/test_observer.py tests/workflows/test_executor.py -q`

Expected: FAIL for missing observer module/constructor argument.

- [ ] **Step 3: Add no-op observer and lifecycle callbacks**

Give `WorkflowExecutor` an optional observer defaulting to null. Call `run_created` immediately after `add_run`; call `step_started` after `add_step`. In `WorkflowRunService`, call `run_projected` after successful projection, and `run_failed` for executor or projector exceptions. Observer errors must fail the run because untracked Provider execution is not allowed.

- [ ] **Step 4: Write failing node-to-state mapping tests**

```python
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
async def test_main_workflow_node_maps_to_reference_status(node_id: str, expected: str) -> None:
    await observer.step_started(definition, run, node(node_id))
    assert lifecycle.transitions[-1].status == expected
```

Also assert another workflow name or projection produces no transition.

- [ ] **Step 5: Implement `ReferenceAnalysisLifecycleObserver`**

Extract `reference_id` and positive `revision` from `run.trigger`. On `run_created`, transition to `queued`. On `step_started`, use the table above. On `run_projected`, read `run.output["status"]` and map `initial_rejected`, `fine_rejected`, or `qualified` to the matching reference terminal status. On `run_failed`, transition to `failed` with `workflow_failed` or `analysis_projection_invalid` and a bounded message.

- [ ] **Step 6: Wire one shared observer into API and Celery runtime**

Construct SQL or in-memory lifecycle repositories alongside the existing reference repository. Pass the observer to the executor/service used by both manual API execution and outbox workers.

- [ ] **Step 7: Run observer, workflow, and e2e tests**

Run:

```bash
cd backend
../.venv/bin/pytest tests/workflows tests/ingestion/test_workflow_observer.py tests/e2e/test_information_flow.py -q
../.venv/bin/ruff check src/zeromind/workflows src/zeromind/ingestion/workflow_observer.py
../.venv/bin/mypy src/zeromind/workflows src/zeromind/ingestion/workflow_observer.py
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/src/zeromind/workflows backend/src/zeromind/ingestion backend/src/zeromind/bootstrap backend/tests
git commit -m "feat: drive reference status from workflow lifecycle"
```

---

### Task 4: Main workflow rename and idempotent preset migration

**Files:**
- Modify: `docs/examples/article-analysis.yaml`
- Modify: `backend/scripts/register_analysis_agents.py`
- Modify: `README.md`
- Test: `backend/tests/agents/test_presets.py`
- Test: `backend/tests/workflows/test_dsl.py`

**Interfaces:**
- Produces: canonical `MAIN_ANALYSIS_WORKFLOW_NAME = "信息分析工作流"` in `backend/src/zeromind/workflows/constants.py`.
- Task 3 observer and Task 5 dispatch import this constant; no duplicated name literals.

- [ ] **Step 1: Write a failing preset migration test**

Test a repository containing a workflow with name and spec name `bestblogs-six-agent-analysis`. After preset registration, assert the same ID has name/spec name `信息分析工作流`, remains active, increments version exactly once, and no second definition exists.

- [ ] **Step 2: Run preset tests and confirm old naming remains**

Run: `cd backend && ../.venv/bin/pytest tests/agents/test_presets.py -q`

Expected: FAIL because YAML and registration script still use the legacy name.

- [ ] **Step 3: Add canonical constant and rename YAML**

Create:

```python
MAIN_ANALYSIS_WORKFLOW_NAME = "信息分析工作流"
LEGACY_MAIN_ANALYSIS_WORKFLOW_NAMES = frozenset({"bestblogs-six-agent-analysis"})
```

Set the YAML `name` to `信息分析工作流`.

- [ ] **Step 4: Update registration script to migrate in place**

Look up canonical name first, then legacy names. If a legacy definition exists, mutate both `workflow.name` and `workflow.spec.name`, increment version once if spec changed, preserve UUID, activate, and save. If canonical and legacy definitions both exist, fail with an explicit conflict rather than choosing one.

- [ ] **Step 5: Run tests and static checks**

Run:

```bash
cd backend
../.venv/bin/pytest tests/agents/test_presets.py tests/workflows/test_dsl.py -q
../.venv/bin/ruff check scripts/register_analysis_agents.py src/zeromind/workflows/constants.py
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add docs/examples/article-analysis.yaml backend/scripts/register_analysis_agents.py backend/src/zeromind/workflows/constants.py backend/tests README.md
git commit -m "feat: rename the main analysis workflow"
```

---

### Task 5: Analysis request queue, manual reanalysis, and stale recovery

**Files:**
- Create: `backend/src/zeromind/ingestion/analysis_queue.py`
- Modify: `backend/src/zeromind/ingestion/api.py`
- Modify: `backend/src/zeromind/bootstrap/tasks.py`
- Modify: `backend/src/zeromind/bootstrap/celery.py`
- Modify: `backend/src/zeromind/shared/outbox.py`
- Test: `backend/tests/ingestion/test_analysis_queue.py`
- Test: `backend/tests/ingestion/test_api.py`
- Test: `backend/tests/integration/test_schedule.py`

**Interfaces:**
- Produces: `ReferenceAnalysisQueue.request(reference_id, revision, request_id, reason) -> OutboxEvent`.
- Produces: `POST /api/v1/references/{reference_id}/reanalyze` response with reference ID, revision, and `pending` status.
- Produces: Celery task `zeromind.recover_stale_reference_analyses`.

- [ ] **Step 1: Write failing queue and manual retry tests**

```python
@pytest.mark.asyncio
async def test_manual_reanalysis_resets_and_enqueues_current_revision() -> None:
    response = client.post(f"/api/v1/references/{reference.id}/reanalyze")
    assert response.status_code == 202
    assert response.json()["analysis_status"] == "pending"
    events = await outbox.pending()
    assert events[0].event_type == "reference.analysis.requested"
    assert events[0].payload["revision"] == reference.current_revision
```

Add a 409 test for a processing status and a test that two distinct retry requests create distinct workflow idempotency keys.

- [ ] **Step 2: Run focused tests and verify endpoints/services are absent**

Run: `cd backend && ../.venv/bin/pytest tests/ingestion/test_analysis_queue.py tests/ingestion/test_api.py -q`

Expected: FAIL for missing queue and route.

- [ ] **Step 3: Implement atomic reset plus outbox enqueue**

Use one SQL transaction for SQL-backed repositories. The event payload is:

```python
{
    "reference_id": str(reference.id),
    "revision": reference.current_revision,
    "request_id": str(request_id),
    "reason": reason,
}
```

Use idempotency key `reference.analysis.requested:{reference_id}:{revision}:{request_id}`.

- [ ] **Step 4: Dispatch explicit analysis requests through only the main workflow**

Register `reference.analysis.requested` in `OutboxDispatcher`. Its handler resolves the one active canonical main workflow and invokes `WorkflowRunService` with key `analysis:{reference_id}:{revision}:{request_id}:{definition.version}`. Existing `reference.discovered` and `reference.updated` dispatch the main workflow using deterministic request IDs derived from their event key.

- [ ] **Step 5: Write and implement stale recovery tests**

Cover: failed run to failed reference; completed projected analysis to repaired terminal status; running older than 30 minutes to `stale_workflow`; processing reference without run to pending and a recovery analysis request. Add the Celery beat entry every 300 seconds and route it to `events`.

- [ ] **Step 6: Run queue, API, schedule, and worker checks**

Run:

```bash
cd backend
../.venv/bin/pytest tests/ingestion/test_analysis_queue.py tests/ingestion/test_api.py tests/integration/test_schedule.py -q
../.venv/bin/ruff check src/zeromind/ingestion/analysis_queue.py src/zeromind/bootstrap
../.venv/bin/mypy src/zeromind/ingestion/analysis_queue.py src/zeromind/bootstrap
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/src/zeromind/ingestion backend/src/zeromind/bootstrap backend/src/zeromind/shared backend/tests
git commit -m "feat: queue and recover reference analyses"
```

---

### Task 6: Historical backfill command

**Files:**
- Create: `backend/scripts/backfill_reference_analysis.py`
- Create: `backend/src/zeromind/ingestion/backfill.py`
- Modify: `backend/Dockerfile`
- Modify: `README.md`
- Modify: `docs/operations.md`
- Test: `backend/tests/ingestion/test_backfill.py`

**Interfaces:**
- Produces: `BackfillResult(scanned, enqueued, skipped, status_counts)`.
- Produces: `backfill_reference_analysis(queue, references, *, all_references, batch_size, limit, generation, dry_run)`.
- CLI flags: `--all`, `--batch-size`, `--limit`, `--generation`, `--dry-run`.

- [ ] **Step 1: Write failing backfill tests**

Test dry-run makes no changes; default skips current completed main-flow analyses; `--all` resets terminal references and queues all; repeated generation is idempotent; a new generation can intentionally requeue; limit and batch size are respected.

- [ ] **Step 2: Run test and confirm backfill module is missing**

Run: `cd backend && ../.venv/bin/pytest tests/ingestion/test_backfill.py -q`

Expected: collection FAIL for missing backfill module.

- [ ] **Step 3: Implement batch selection and idempotent generation keys**

For each selected current revision, use a stable UUID5 request ID derived from `reference_id`, revision, main workflow version, and generation. Return counts grouped into pending, queued, processing, completed, rejected, and failed. Do not invoke `WorkflowRunService` from the command.

- [ ] **Step 4: Implement CLI output without secrets**

The CLI prints JSON containing only counts, generation, dry-run, and elapsed time. It creates the database, repositories, and queue with the same settings path as the application and disposes the database in `finally`.

- [ ] **Step 5: Document staged production commands**

Document:

```bash
docker compose run --rm api python scripts/backfill_reference_analysis.py --all --dry-run
docker compose run --rm api python scripts/backfill_reference_analysis.py --all --limit 5 --generation lifecycle-v1-smoke
docker compose run --rm api python scripts/backfill_reference_analysis.py --all --generation lifecycle-v1
```

- [ ] **Step 6: Run tests and static checks**

Run:

```bash
cd backend
../.venv/bin/pytest tests/ingestion/test_backfill.py -q
../.venv/bin/ruff check scripts/backfill_reference_analysis.py src/zeromind/ingestion/backfill.py
../.venv/bin/mypy src/zeromind/ingestion/backfill.py
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/scripts backend/src/zeromind/ingestion/backfill.py backend/tests/ingestion/test_backfill.py backend/Dockerfile README.md docs/operations.md
git commit -m "feat: backfill historical reference analyses"
```

---

### Task 7: Aggregated reference list and reading-detail API

**Files:**
- Create: `backend/src/zeromind/ingestion/read_models.py`
- Modify: `backend/src/zeromind/ingestion/repository.py`
- Modify: `backend/src/zeromind/ingestion/api.py`
- Modify: `backend/src/zeromind/bootstrap/app.py`
- Test: `backend/tests/ingestion/test_read_models.py`
- Test: `backend/tests/ingestion/test_api.py`

**Interfaces:**
- Produces: `ReferenceListQuery(status, category, minimum_score, subscription_id, published_from, published_to)`.
- Produces: `ReferenceListItem` with metadata, lifecycle, and analysis preview.
- Produces: `ReferenceReadingDetail` with current revision, lifecycle, analysis, and normalized `iframe_url`.
- Produces: `GET /api/v1/references/{id}/reading-detail`.

- [ ] **Step 1: Write failing list aggregation tests**

Create references covering pending, processing, completed, rejected, and failed. Assert all are returned by default; status, category, score, subscription, and date filters work; pending fields are null; completed preview matches the current revision analysis only.

- [ ] **Step 2: Run read-model tests and confirm query types are absent**

Run: `cd backend && ../.venv/bin/pytest tests/ingestion/test_read_models.py -q`

Expected: collection FAIL for missing read-model module.

- [ ] **Step 3: Implement in-memory and SQL aggregate queries**

SQL joins current `ReferenceRevisionModel`, subscription, and current main-workflow `ContentAnalysisModel` using reference ID and `reference_revision == current_revision`. Use outer joins so unanalysed references remain visible. Select the current workflow definition by canonical name/version and do not return analyses from auxiliary workflows.

- [ ] **Step 4: Write failing reading-detail API tests**

Assert the response includes title, RSS summary, author, source, lifecycle fields, full structured analysis, provenance, and normalized HTTP(S) `iframe_url`. Assert invalid/non-HTTP URLs return `iframe_url: null`; no analysis returns `analysis: null`; unknown reference returns 404.

- [ ] **Step 5: Implement Pydantic responses and aggregate endpoint**

Reuse analysis response field shapes instead of duplicating incompatible names. Keep `key_quotes`, `viewpoints`, and dimensions ordered as persisted. Never resolve or fetch the URL in this endpoint.

- [ ] **Step 6: Run API, repository, and security tests**

Run:

```bash
cd backend
../.venv/bin/pytest tests/ingestion/test_read_models.py tests/ingestion/test_api.py tests/content -q
../.venv/bin/ruff check src/zeromind/ingestion tests/ingestion
../.venv/bin/mypy src/zeromind/ingestion
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/src/zeromind/ingestion backend/src/zeromind/bootstrap/app.py backend/tests/ingestion
git commit -m "feat: expose reference analysis read models"
```

---

### Task 8: Enriched content-reference list

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/references.tsx`
- Modify: `frontend/src/components.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/app.test.tsx`

**Interfaces:**
- Consumes: Task 7 `GET /references` response and filters.
- Produces: clickable cards to `/references/:id`.
- Produces: status grouping helpers and Chinese status labels.

- [ ] **Step 1: Write a failing UI test for all lifecycle groups**

Mock pending, analyzing, completed, fine-rejected, and failed list items. Assert titles remain visible, Chinese status labels render, completed cards show summary/category/tags/score, failed cards show error and reanalysis control, and clicking a card navigates to its detail route.

- [ ] **Step 2: Run the focused frontend test and confirm current URL-only cards fail**

Run: `cd frontend && pnpm test -- --run src/app.test.tsx`

Expected: FAIL because metadata, lifecycle controls, and navigation are absent.

- [ ] **Step 3: Add exact client types and status helpers**

```typescript
export type ReferenceAnalysisStatus =
  | "pending" | "queued" | "screening" | "resolving" | "analyzing"
  | "classifying" | "scoring" | "reviewing" | "finalizing"
  | "initial_rejected" | "fine_rejected" | "completed" | "failed";
```

Define Chinese labels and grouped filters `all`, `pending`, `processing`, `completed`, `rejected`, `failed`.

- [ ] **Step 4: Replace list cards and add filter toolbar**

Use semantic buttons/links, title-first hierarchy, source/author/time metadata, summary clamp, score badge, category/tags, and stage label. Reanalysis uses `POST /references/{id}/reanalyze`, invalidates `references`, and stops card navigation propagation.

- [ ] **Step 5: Implement responsive styling and accessible states**

Use existing design tokens. Cards must have visible focus, score/status cannot rely only on color, loading/empty/error states remain, and narrow screens use one column.

- [ ] **Step 6: Run typecheck and frontend tests**

Run:

```bash
cd frontend
pnpm typecheck
pnpm test
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "feat: enrich the content reference list"
```

---

### Task 9: BestBlogs-inspired reading detail

**Files:**
- Create: `frontend/src/pages/reference-detail.tsx`
- Modify: `frontend/src/app.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/app.test.tsx`

**Interfaces:**
- Consumes: Task 7 `GET /references/{id}/reading-detail`.
- Produces: route `/references/:referenceId`.
- Produces: desktop original/analysis split and mobile analysis/original tabs.

- [ ] **Step 1: Write failing detail rendering tests**

Mock a completed detail and assert title, status, total score, one-sentence summary, full summary, viewpoints, key quotes, six score dimensions, recommendation, categories/tags, provenance, iframe, and external-original link render. Add pending, failed, rejected, missing-analysis, and `iframe_url: null` cases.

- [ ] **Step 2: Run focused tests and confirm the route/page is absent**

Run: `cd frontend && pnpm test -- --run src/app.test.tsx`

Expected: FAIL because `/references/:referenceId` has no route.

- [ ] **Step 3: Add reading-detail client types and query**

Reuse `AnalysisDetail` types where field-compatible. Query key is `["reference-reading-detail", referenceId]`; refetch every 5 seconds only while status is pending or processing, and stop for terminal states.

- [ ] **Step 4: Build the header and analysis rail**

Render title, source, author/time, status, score, and external link. The analysis rail order is: one-sentence summary, summary, viewpoints, key quotes, six dimensions, recommendation, categories/tags, provenance. Pending/processing shows a stage timeline; failed shows safe error and reanalysis; rejected explains the business gate outcome.

- [ ] **Step 5: Add the sandboxed iframe and fallback**

```tsx
<iframe
  title={`原文：${detail.title}`}
  src={detail.iframe_url}
  sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
  referrerPolicy="no-referrer-when-downgrade"
/>
```

Do not add `allow-top-navigation`. Always show “新窗口打开原文” and an RSS metadata fallback card because browsers cannot reliably expose cross-origin frame refusal.

- [ ] **Step 6: Implement 65/35 desktop layout and mobile tabs**

At desktop width, make the frame panel min-height `calc(100vh - 9rem)` and the 35% analysis rail sticky with independent scroll. Under the existing mobile breakpoint, default to AI analysis and offer explicit “AI 分析 / 原文” tabs.

- [ ] **Step 7: Run frontend tests, typecheck, and production build**

Run:

```bash
cd frontend
pnpm test
pnpm typecheck
pnpm build
```

Expected: all pass and build succeeds.

- [ ] **Step 8: Commit**

```bash
git add frontend/src
git commit -m "feat: add the reference reading detail"
```

---

### Task 10: End-to-end verification, migration, and historical processing

**Files:**
- Modify: `backend/tests/e2e/test_information_flow.py`
- Modify: `README.md`
- Modify: `docs/operations.md`

**Interfaces:**
- Validates all prior task interfaces against PostgreSQL/Compose and the local 73-reference dataset.

- [ ] **Step 1: Extend the end-to-end flow test**

Cover discovery pending, queue/run node states, qualified completed, both business rejection terminals, technical failed, RSS update reset, stale old-run suppression, aggregate list, and reading detail without persisted body text.

- [ ] **Step 2: Run the full local test matrix**

Run:

```bash
cd backend
../.venv/bin/ruff check init-sql src tests scripts
../.venv/bin/mypy src
../.venv/bin/pytest -q
cd ../pi-runner
pnpm typecheck
pnpm test
pnpm build
cd ../frontend
pnpm typecheck
pnpm test
pnpm build
```

Expected: all pass.

- [ ] **Step 3: Build images and migrate PostgreSQL**

Run:

```bash
docker compose build migrate api worker scheduler frontend
docker compose run --rm migrate
docker compose up -d api worker scheduler frontend
docker compose ps
```

Expected: migration reaches `0011_reference_analysis_lifecycle`; API is healthy; worker and scheduler are running.

- [ ] **Step 4: Rename/register the main workflow and verify identity**

Run the existing preset registration against the configured GLM Provider. Query PostgreSQL and assert the old UUID now has name `信息分析工作流`, status active, projection `content_analysis_v1`, and there is no active legacy-name workflow.

- [ ] **Step 5: Smoke-backfill five references**

Run dry-run then `--limit 5 --generation lifecycle-v1-smoke`. Observe database transitions and Worker logs until all five reach a terminal state. Inspect agent sessions and confirm no article body appears in reference, workflow-step, session, outbox, or analysis tables.

- [ ] **Step 6: Backfill all 73 historical references**

Run `--all --generation lifecycle-v1`. Monitor grouped status counts. Retry only technical failures with a new generation after identifying the cause. Completion evidence is a database query showing zero pending/processing references and exactly 73 terminal references, unless RSS discovery increases the total during the run; in that case compare against the captured start set of IDs.

- [ ] **Step 7: Browser-verify list and detail**

At `http://localhost:8080/references`, verify every status group, title-first cards, filters, score/category/tag previews, and reanalysis. Open completed, rejected, failed, and processing details. Verify desktop split, mobile tabs, iframe sandbox, external fallback, summaries, viewpoints, quotes, dimensions, and provenance.

- [ ] **Step 8: Document final operational evidence and commit**

Record migration version, workflow UUID/name/version, starting reference count, terminal counts, test totals, and known iframe-blocked source examples in `docs/operations.md` without credentials.

```bash
git add backend/tests/e2e/test_information_flow.py README.md docs/operations.md
git commit -m "docs: verify reference analysis rollout"
```
