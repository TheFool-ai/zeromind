# Monorepo Directory Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the existing backend, frontend, Agent runtime, and information-service documentation under `apps/` without changing runtime behavior.

**Architecture:** Each runnable application owns its code, tests, migrations, documentation, dependency metadata, and Dockerfile. The repository root retains only Git metadata, environment examples, the system README, and the Compose file that deploys the applications together.

**Tech Stack:** Python 3.12, FastAPI, Celery, Alembic, React 19, TypeScript, Vite, Node.js 22, pnpm 11.9, Docker Compose.

**Spec:** `apps/information/docs/superpowers/specs/2026-09-04-monorepo-directory-restructure-design.md`

## Global Constraints

- Preserve existing API, database, task-processing, and JSONL subprocess behavior.
- Keep database migrations, tests, scripts, documentation, and dependency metadata with their owning application.
- Keep the web and Agent runtime pnpm lockfiles and workspace files application-local.
- Do not create a root `database`, `tests`, `docs`, JavaScript workspace, or shared-code package.
- Add only a responsibility README for the unimplemented knowledge application.
- Do not read, move, modify, stage, or commit the untracked `.env.save` file.
- Do not convert the Agent runtime to HTTP in this change.

---

### Task 1: Capture the pre-migration verification baseline

**Files:**
- Inspect: `compose.yaml`
- Inspect: `backend/pyproject.toml`
- Inspect: `frontend/package.json`
- Inspect: `pi-runner/package.json`

**Interfaces:**
- Consumes: the current repository layout and existing application commands.
- Produces: a recorded pass/fail baseline used to distinguish migration regressions from pre-existing failures.

- [ ] **Step 1: Confirm the worktree contains no unexpected edits**

Run:

```bash
git status --short
```

Expected: the design amendment and this plan are the only task-owned changes; `.env.save` is the only unrelated untracked file.

- [ ] **Step 2: Validate the existing Compose model**

Run:

```bash
docker compose config --quiet
```

Expected: exit status 0.

- [ ] **Step 3: Run the available Python checks**

Run:

```bash
cd backend
../.venv/bin/pytest -q
../.venv/bin/ruff check src tests
../.venv/bin/mypy src
```

Expected: all commands pass. If `.venv` is absent, record that the local Python suite is unavailable and use the Docker build in Task 4 as the executable verification.

### Task 2: Move every application and its owned documentation

**Files:**
- Move: `backend/` to `apps/information/`
- Move: `frontend/` to `apps/web/`
- Move: `pi-runner/` to `apps/agent-runtime/`
- Move: `docs/` to `apps/information/docs/`
- Create: `apps/knowledge/README.md`

**Interfaces:**
- Consumes: the four current top-level project directories.
- Produces: the application-oriented `apps/information`, `apps/knowledge`, `apps/agent-runtime`, and `apps/web` boundaries.

- [ ] **Step 1: Create the application container and move tracked directories**

Run:

```bash
mkdir apps
git mv backend apps/information
git mv frontend apps/web
git mv pi-runner apps/agent-runtime
git mv docs apps/information/docs
mkdir apps/knowledge
```

Expected: the old four top-level directories no longer exist and Git reports renames beneath `apps/`.

- [ ] **Step 2: Document the knowledge application boundary**

Create `apps/knowledge/README.md` with:

```markdown
# ZeroMind Knowledge Service

This directory owns the knowledge-base management backend.

The service will be implemented as an independently buildable Python application. It will
own its source code, tests, migrations, scripts, documentation, dependencies, container
definition, and database tables. Other applications will access it through HTTP rather than
reading or writing its tables directly.

Framework scaffolding and API design are intentionally deferred until the knowledge-service
requirements are defined.
```

- [ ] **Step 3: Confirm application-owned artifacts moved together**

Run:

```bash
test -f apps/information/pyproject.toml
test -f apps/information/migrations/env.py
test -d apps/information/tests
test -f apps/information/docs/operations.md
test -f apps/web/package.json
test -f apps/agent-runtime/package.json
test -f apps/knowledge/README.md
```

Expected: every command exits with status 0.

### Task 3: Repair build, deployment, documentation, and ignore paths

**Files:**
- Modify: `apps/information/Dockerfile`
- Modify: `compose.yaml`
- Modify: `README.md`
- Modify: `.gitignore`
- Modify: `apps/information/docs/operations.md`
- Modify: `apps/information/docs/superpowers/specs/2026-09-04-monorepo-directory-restructure-design.md`
- Modify: `apps/information/docs/superpowers/plans/2026-09-04-monorepo-directory-restructure.md`

**Interfaces:**
- Consumes: the moved paths from Task 2.
- Produces: valid Docker build contexts, runtime paths, developer commands, and current documentation links for the new layout.

- [ ] **Step 1: Update the information Dockerfile build inputs**

Apply these exact path mappings while preserving image stages and runtime destinations:

```text
pi-runner/*       -> apps/agent-runtime/*
backend/*         -> apps/information/*
docs/examples     -> apps/information/docs/examples
```

Keep `/app/pi-runner/dist`, `/app/pi-runner/node_modules`, and the `ZEROMIND_PI_COMMAND`
runtime value unchanged because those are container-internal paths, not repository paths.

- [ ] **Step 2: Update Compose build paths**

Set the shared Python Dockerfile to:

```yaml
build:
  context: .
  dockerfile: apps/information/Dockerfile
```

Set the web image build to:

```yaml
build:
  context: apps/web
  dockerfile: Dockerfile
```

Do not add a separate Agent runtime service in this migration.

- [ ] **Step 3: Update active repository instructions and links**

Use these path replacements in `README.md`:

```text
docs/examples/       -> apps/information/docs/examples/
docs/operations.md   -> apps/information/docs/operations.md
cd backend           -> cd apps/information
cd ../pi-runner      -> cd ../agent-runtime
cd ../frontend       -> cd ../web
```

Update current operational documentation references from `docs/examples/` to
`apps/information/docs/examples/`. Do not rewrite paths inside historical plans and specs;
those files describe the repository state at the time they were authored.

- [ ] **Step 4: Update generated-artifact ignore paths**

Replace the old application paths in `.gitignore`:

```gitignore
apps/web/dist/
apps/information/data/
apps/web/vite.config.js
apps/web/vite.config.d.ts
```

- [ ] **Step 5: Update the current spec and plan locations**

Change the implementation plan's `Spec:` link to:

```text
apps/information/docs/superpowers/specs/2026-09-04-monorepo-directory-restructure-design.md
```

In both current documents, describe their saved locations using `apps/information/docs/`.
Retain the old-to-new path mapping because it documents the migration itself.

- [ ] **Step 6: Check formatting and inspect the migration diff**

Run:

```bash
git diff --check
git status --short
git diff --stat
```

Expected: no whitespace errors; `.env.save` remains untracked and unstaged.

- [ ] **Step 7: Commit the structural migration**

Run:

```bash
git add .dockerignore .gitignore README.md compose.yaml apps
git status --short
git commit -m "refactor: organize applications under apps"
```

Expected: the commit contains the directory moves, path repairs, and knowledge boundary README, but not `.env.save`.

### Task 4: Verify the restructured monorepo

**Files:**
- Verify: `apps/information/`
- Verify: `apps/agent-runtime/`
- Verify: `apps/web/`
- Verify: `apps/knowledge/`
- Verify: `compose.yaml`

**Interfaces:**
- Consumes: the completed path migration.
- Produces: evidence that all applications still build and test through their application-local toolchains and joint Compose deployment.

- [ ] **Step 1: Run the information-service suite**

Run:

```bash
cd apps/information
../../.venv/bin/pytest -q
../../.venv/bin/ruff check src tests
../../.venv/bin/mypy src
```

Expected: all commands pass. If the local virtual environment is absent, run the Docker image build in Step 4 and report the omitted local checks explicitly.

- [ ] **Step 2: Run Agent runtime checks with its application-local lockfile**

Run in an environment with pnpm 11.9 available:

```bash
cd apps/agent-runtime
pnpm install --frozen-lockfile
pnpm test
pnpm typecheck
pnpm build
```

Expected: install, tests, type checking, and build pass.

- [ ] **Step 3: Run web checks with its application-local lockfile**

Run in an environment with pnpm 11.9 available:

```bash
cd apps/web
pnpm install --frozen-lockfile
pnpm test
pnpm typecheck
pnpm build
```

Expected: install, tests, type checking, and build pass.

- [ ] **Step 4: Validate the joint deployment definition and images**

Run:

```bash
docker compose config --quiet
docker compose build api frontend
```

Expected: Compose validation and both image builds succeed. The API image build also builds and embeds the Agent runtime.

- [ ] **Step 5: Search active files for stale paths**

Run:

```bash
rg -n --glob '!apps/information/docs/superpowers/**' \
  '(backend/|frontend/|pi-runner/|docs/examples|docs/operations|cd backend|cd frontend|cd pi-runner)' \
  README.md compose.yaml .dockerignore .gitignore apps
```

Expected: no stale repository paths. Container-internal `/app/pi-runner` references are allowed.

- [ ] **Step 6: Confirm the final repository shape and user file safety**

Run:

```bash
find . -maxdepth 3 -not -path './.git*' -not -path './node_modules*' | sort
git status --short
git ls-files --error-unmatch .env.save
```

Expected: application code is under `apps/`; `git status --short` shows only `?? .env.save`; the final command fails, confirming `.env.save` is not tracked.

- [ ] **Step 7: Commit any verification-only corrections**

If verification required path-only corrections, stage their exact files and commit:

```bash
git commit -m "fix: complete monorepo path migration"
```

Expected: no commit is created when no correction was necessary.
