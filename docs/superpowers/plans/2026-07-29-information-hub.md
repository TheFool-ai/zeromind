# ZeroMind Information Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Docker-deployable RSS information collection MVP with reference-only storage, Pi-backed agents, a safe YAML DAG engine, signed webhooks, and an administration UI.

**Architecture:** Implement a Python modular monolith organized by DDD bounded contexts and run it as API, scheduler, and worker processes. PostgreSQL owns durable state, Redis/Celery carries recoverable jobs, a Node Pi runner exposes JSONL RPC, and React provides the management UI.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, PostgreSQL 16, Redis 7, Celery 5, HTTPX, feedparser, defusedxml, trafilatura, jsonschema, pytest, React 19, TypeScript, Vite, TanStack Query, React Router, Vitest, Pi SDK, Docker Compose.

## Global Constraints

- Store references, RSS metadata revisions, and structured analysis only; never persist fetched article bodies or snapshots.
- Poll every 30 minutes with a 10-minute overlap and idempotency at every boundary.
- Keep provider credentials in environment variables referenced by name.
- Disable Pi filesystem, shell, and builtin tools.
- Reject private/local network destinations before requests and after redirects.
- Treat PostgreSQL as the recoverable source of truth for all business operations.

---

### Task 1: Bootstrap the modular monolith and database

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/zeromind/bootstrap/app.py`
- Create: `backend/src/zeromind/shared/config.py`
- Create: `backend/src/zeromind/shared/database.py`
- Create: `backend/src/zeromind/shared/models.py`
- Create: `backend/tests/test_health.py`
- Create: `backend/alembic.ini`
- Create: `backend/migrations/env.py`
- Create: `backend/migrations/versions/0001_initial.py`

**Interfaces:**
- Produces: `create_app() -> FastAPI`, `Settings`, SQLAlchemy `Base`, session provider, `/health/live`, `/health/ready`.

- [ ] Write `test_live_health_does_not_require_dependencies` and `test_ready_health_reports_database_state`.
- [ ] Run `pytest tests/test_health.py -q`; verify failure because `zeromind.bootstrap.app` is absent.
- [ ] Add packaging, settings, database session management, app factory, health routes, and initial schema migration.
- [ ] Run the health tests and `alembic upgrade head`; verify both succeed.
- [ ] Commit with `chore: bootstrap backend and database`.

### Task 2: Implement subscriptions and OPML

**Files:**
- Create: `backend/src/zeromind/subscriptions/domain.py`
- Create: `backend/src/zeromind/subscriptions/repository.py`
- Create: `backend/src/zeromind/subscriptions/service.py`
- Create: `backend/src/zeromind/subscriptions/opml.py`
- Create: `backend/src/zeromind/subscriptions/api.py`
- Create: `backend/tests/subscriptions/test_domain.py`
- Create: `backend/tests/subscriptions/test_opml.py`
- Create: `backend/tests/subscriptions/test_api.py`

**Interfaces:**
- Produces: `normalize_feed_url(url: str) -> str`, `preview_opml(data: bytes) -> OpmlPreview`, `SubscriptionService.create()`, and `/api/v1/subscriptions` plus `/api/v1/subscriptions/opml/{preview,import}`.

- [ ] Test URL normalization, enabled/disabled transitions, duplicate URLs, OPML 1.0/2.0 nesting, XXE rejection, invalid outlines, and idempotent re-import.
- [ ] Run subscription tests; verify failures identify the missing domain and parser.
- [ ] Implement the aggregate, repository protocol/SQL adapter, application service, safe parser, cursor-list API, and per-entry import result.
- [ ] Run subscription tests and the full backend suite.
- [ ] Commit with `feat: add RSS subscription and OPML management`.

### Task 3: Implement feed ingestion and reference revisions

**Files:**
- Create: `backend/src/zeromind/ingestion/domain.py`
- Create: `backend/src/zeromind/ingestion/feed_client.py`
- Create: `backend/src/zeromind/ingestion/service.py`
- Create: `backend/src/zeromind/ingestion/api.py`
- Create: `backend/tests/ingestion/test_identity.py`
- Create: `backend/tests/ingestion/test_service.py`
- Create: `backend/tests/ingestion/test_feed_client.py`

**Interfaces:**
- Produces: `derive_entry_identity(subscription_id, entry)`, `metadata_fingerprint(entry)`, `IngestionService.ingest()`, conditional HTTP `FeedClient.fetch()`, `ContentReference`, `ReferenceRevision`, `FeedFetch`, and reference-list/detail endpoints.

- [ ] Test GUID/URL/hash identity precedence, canonical URL normalization, repeated payload idempotency, one-revision-per-change, old unseen entries, `304`, timeout, malformed feeds, and per-feed retry state.
- [ ] Run ingestion tests; verify missing-feature failures.
- [ ] Implement the entities, feed adapter, transactional ingestion service, unique constraints, outbox writes, and read APIs.
- [ ] Run ingestion tests and the full backend suite.
- [ ] Commit with `feat: ingest feeds as idempotent content references`.

### Task 4: Implement transient secure content resolution

**Files:**
- Create: `backend/src/zeromind/content/network_policy.py`
- Create: `backend/src/zeromind/content/resolver.py`
- Create: `backend/tests/content/test_network_policy.py`
- Create: `backend/tests/content/test_resolver.py`

**Interfaces:**
- Produces: `NetworkPolicy.validate_url(url)`, immutable `ResolvedDocument`, and `ContentResolver.resolve(reference) -> ResolvedDocument`.

- [ ] Test scheme validation, literal and DNS-resolved private IP rejection, redirect revalidation, content-type and size limits, timeouts, extraction, and absence of body logging/persistence.
- [ ] Run content tests; verify missing-feature failures.
- [ ] Implement the network policy, bounded streaming fetch, redirect loop, and trafilatura-backed extraction.
- [ ] Run content tests and the full backend suite.
- [ ] Commit with `feat: resolve referenced content without persistence`.

### Task 5: Implement Agent Registry and Pi Gateway

**Files:**
- Create: `backend/src/zeromind/agents/domain.py`
- Create: `backend/src/zeromind/agents/service.py`
- Create: `backend/src/zeromind/agents/pi_rpc.py`
- Create: `backend/src/zeromind/agents/api.py`
- Create: `pi-runner/package.json`
- Create: `pi-runner/src/main.ts`
- Create: `pi-runner/src/protocol.ts`
- Create: `backend/tests/agents/test_registry.py`
- Create: `backend/tests/agents/test_pi_rpc.py`
- Create: `pi-runner/src/main.test.ts`

**Interfaces:**
- Produces: `ProviderProfile`, `AgentDefinition`, `AgentRegistry.discover(capabilities)`, `PiGateway.execute(agent, input) -> AgentResult`, JSONL messages `execute`, `delta`, `completed`, `failed`, and `/api/v1/providers`, `/api/v1/agents`, `/api/v1/agents/discover`.

- [ ] Test unique names, capability matching, enabled filtering, version increments, environment-key lookup without persistence, JSONL correlation, timeout/cancel, malformed output, schema validation, and disabled Pi tools.
- [ ] Run Python and runner tests; verify missing-feature failures.
- [ ] Implement registry/repositories/APIs, async subprocess lifecycle, typed JSONL framing, Pi `ModelRuntime`, in-memory sessions, system prompt override, `noTools: "all"`, and output/cost events.
- [ ] Run agent, runner, and full suites.
- [ ] Commit with `feat: add Pi-backed agent registry and gateway`.

### Task 6: Implement YAML DAG workflow execution

**Files:**
- Create: `backend/src/zeromind/workflows/domain.py`
- Create: `backend/src/zeromind/workflows/dsl.py`
- Create: `backend/src/zeromind/workflows/executor.py`
- Create: `backend/src/zeromind/workflows/api.py`
- Create: `backend/tests/workflows/test_dsl.py`
- Create: `backend/tests/workflows/test_executor.py`
- Create: `backend/tests/workflows/test_api.py`

**Interfaces:**
- Produces: `parse_workflow_yaml(text) -> WorkflowSpec`, `validate_workflow(spec, agent_registry)`, `WorkflowExecutor.execute(run_id)`, `WorkflowDefinition`, `WorkflowRun`, `StepRun`, and workflow validation/activation/run APIs.

- [ ] Test valid sequential/parallel DAGs, cycle and unreachable-node rejection, dependency and agent validation, restricted mappings, retry bounds, immutable activated versions, run idempotency, condition routing, schema mismatch, and transient document disposal.
- [ ] Run workflow tests; verify missing-feature failures.
- [ ] Implement Pydantic DSL types, safe YAML loading, topological validation, version activation, deterministic run keys, node executors, structured output mapping, and run timeline API.
- [ ] Run workflow tests and the full backend suite.
- [ ] Commit with `feat: execute validated YAML DAG workflows`.

### Task 7: Implement outbox, scheduling, workers, webhooks, and authentication

**Files:**
- Create: `backend/src/zeromind/shared/outbox.py`
- Create: `backend/src/zeromind/bootstrap/celery.py`
- Create: `backend/src/zeromind/bootstrap/tasks.py`
- Create: `backend/src/zeromind/identity/api.py`
- Create: `backend/src/zeromind/delivery/service.py`
- Create: `backend/src/zeromind/delivery/api.py`
- Create: `backend/tests/integration/test_outbox_recovery.py`
- Create: `backend/tests/integration/test_schedule.py`
- Create: `backend/tests/delivery/test_webhook.py`
- Create: `backend/tests/identity/test_auth.py`

**Interfaces:**
- Produces: outbox dispatcher/repair tasks, 30-minute due-feed schedule, workflow-event handler, stale-job recovery, `/api/v1/auth/token`, webhook CRUD, HMAC delivery, and retry APIs.

- [ ] Test transactional event creation, duplicate dispatch safety, stale lease recovery, due-feed claiming, discovery/update trigger filtering, admin authentication, webhook SSRF policy, signature format, and retry exhaustion.
- [ ] Run integration, delivery, and identity tests; verify missing-feature failures.
- [ ] Implement Celery configuration/routes/Beat schedule, database leases, outbox handlers, token authentication, shared network policy, webhook delivery, and readiness checks.
- [ ] Run the full backend suite including integration tests against PostgreSQL/Redis.
- [ ] Commit with `feat: orchestrate durable jobs and webhook delivery`.

### Task 8: Build the administration UI

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/src/app.tsx`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/pages/subscriptions.tsx`
- Create: `frontend/src/pages/references.tsx`
- Create: `frontend/src/pages/agents.tsx`
- Create: `frontend/src/pages/workflows.tsx`
- Create: `frontend/src/pages/runs.tsx`
- Create: `frontend/src/pages/webhooks.tsx`
- Create: `frontend/src/app.test.tsx`

**Interfaces:**
- Consumes: `/api/v1` OpenAPI contract.
- Produces: responsive authenticated management UI with OPML preview, health/status views, agent test, YAML validation/activation, run timeline/result, and retry controls.

- [ ] Write Vitest/Testing Library tests for routing, authentication expiry, list/error states, OPML preview, workflow validation errors, and run retry.
- [ ] Run `pnpm test`; verify missing-feature failures.
- [ ] Implement the Vite app, typed API client generated from OpenAPI, routes, accessible forms/tables, and required status/error states.
- [ ] Run frontend tests, type-check, and production build.
- [ ] Commit with `feat: add information hub administration UI`.

### Task 9: Package, document, and verify the complete system

**Files:**
- Create: `compose.yaml`
- Create: `backend/Dockerfile`
- Create: `pi-runner/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `.env.example`
- Create: `README.md`
- Create: `docs/operations.md`
- Create: `tests/e2e/test_information_flow.py`

**Interfaces:**
- Produces: one-command Docker Compose deployment, migration/start commands, operator documentation, and end-to-end acceptance test.

- [ ] Write an end-to-end test that imports OPML, ingests a fixture feed twice, resolves a fixture article, executes a fake-provider Pi workflow, verifies one structured result, and verifies one signed webhook.
- [ ] Run the E2E test before fixtures/compose wiring; verify it fails at the first unavailable service.
- [ ] Add multi-stage images, health checks, non-root/read-only Pi runtime, persistent PostgreSQL/Redis configuration, environment template, fixtures, setup guide, backup/recovery instructions, and security notes.
- [ ] Run backend lint/type/tests, runner test/build, frontend test/type/build, migration upgrade/downgrade/upgrade, Docker Compose config validation, E2E tests, and a repository secret scan.
- [ ] Audit every design acceptance criterion against fresh command output.
- [ ] Commit with `chore: package and verify the information hub`.

