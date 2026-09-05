# Subscription DDD Refactoring Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for the isolated domain/persistence task and review; the coordinator implements application and integrations with the agreed interfaces. Track completion below.

**Goal:** Implement the subscription domain design, preserving HTTP/database behavior and using one file per aggregate/entity/value object.

**Architecture:** Domain objects and repository interfaces live inside domain; infrastructure implements persistence and OPML parsing; application services return immutable DTOs and own state changes; HTTP/tasks and other contexts consume explicit application contracts. Existing uncommitted migrations rename and identity removal remain intact.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, pytest; existing React frontend unchanged.

**Spec:** ../../domains/subscriptions.md

## Global Constraints

- One aggregate/entity/value object per file, no domain framework dependencies.
- Preserve HTTP paths, string feed_url fields, database columns and migration revisions.
- Keep InMemorySubscriptionRepository as a runtime-capable infrastructure adapter.
- Preserve normalization, polling, failure backoff and OPML partial-import behavior.
- Do not commit unrelated existing work or add migrations for this package refactor.

## Task 1: Domain and persistence

- [x] Add FeedAddress normalization/value-equality/immutability tests, aggregate identity tests and persistence round-trip tests; run before implementation.
- [x] Split Subscription, SubscriptionHealth and DuplicateSubscriptionError into the documented individual files.
- [x] Define immutable FeedAddress(value: str), parse(raw: str) -> FeedAddress and is_rsshub: bool. Constructor normalization prevents bypassing validation.
- [x] Subscription.feed_url uses FeedAddress; create accepts str | FeedAddress; equality uses ID. Preserve existing domain methods.
- [x] Split SubscriptionRepository protocol, mapper, SQL model, SQL and memory repositories. find_by_url accepts FeedAddress. Memory implementation copies on reads/writes to match persistence semantics.
- [x] Move tests into domain/ and infrastructure/, verify both persistence implementations preserve full state and due-claim behavior.

## Task 2: Application, OPML and HTTP

- [x] Move OPML DTOs and import results into individual application/dto files; define an OpmlParser port and implement XmlOpmlParser.preview(data: bytes) -> OpmlPreview.
- [x] Add immutable SubscriptionView with scalar/tuple fields matching aggregate state and string feed_url/health at boundaries.
- [x] SubscriptionService(repository, opml_parser=None) returns SubscriptionView from create, get, list, set_enabled and claim_due; missing get returns None. Parser is injected by bootstrap and by OPML tests.
- [x] Add record_success(subscription_id, *, now, etag, last_modified, poll_interval=30min) and record_failure(subscription_id, *, now), each loading aggregate, invoking method and saving.
- [x] Add preview_opml(data) and import_opml(data) application use cases; import_opml returns (preview, import_result) for the existing HTTP contract.
- [x] Expose FeedAddress, SubscriptionService and SubscriptionView via public.py. Split routes.py/schemas.py without changing endpoint responses.
- [x] Test immutable detached views, persistence of updates, missing IDs and OPML behavior.

## Task 3: Consumers and verification

- [x] Migrate ReferenceReadService and AnalysisProjector to SubscriptionService and SubscriptionView; migrate normalization consumers to public FeedAddress.parse(...).value.
- [x] Bootstrap builds repositories/parser/services; tasks accept/read DTOs and record results through application services. Retain scheduling and ingestion orchestration.
- [x] Update all test fixtures, ORM metadata registration imports and Alembic env.py imports; retain migration revision files byte-for-byte.
- [x] Remove old flat modules, move old subscription tests, update domain document from target to actual implementation.
- [x] Run all backend tests, ruff, targeted type checks, Alembic offline upgrade, frontend tests and build as needed for contract validation.
- [x] Request independent code review; resolve substantive issues and report evidence. Leave changes uncommitted.

## Verification commands

Run from apps/information using the existing uv environment:

```bash
uv run --no-project --with '.[dev]' python -m pytest -p no:cacheprovider -q tests
uv run --no-project --with '.[dev]' ruff check --no-cache src tests init-sql
uv run --no-project --with '.[dev]' alembic upgrade head --sql
```

Frontend contract tests from apps/web:

```bash
npm test -- --configLoader runner --reporter=dot
```

## Completion evidence

- All backend tests: 347 passed (one dependency deprecation warning).
- Frontend contract tests: 20 passed; frontend source did not change in this refactor.
- Ruff: all source, test and init-sql checks passed.
- Mypy: all 43 targeted subscription and integration source files passed, including the final IPv6 correction.
- Alembic: single 0011_reference_lifecycle head; full offline PostgreSQL upgrade generated successfully. All version files are byte-for-byte unchanged.
- One object per domain file and inward dependency checks passed; old flat subscription modules are removed.
- Independent review identified IPv6 brackets being lost during normalization. Five regression cases reproduced the failure; preserving brackets resolved it, and review found no remaining substantive issues.
- Domain documentation and README now describe the implemented structure. Changes remain uncommitted in codex/monorepo-restructure.
