# Monorepo Directory Restructure Design

## Goal

Restructure ZeroMind into an application-oriented monorepo. Each application owns its
source code, tests, migrations, scripts, documentation, dependencies, and container
definition. The repository root owns only cross-application orchestration and repository
metadata.

This restructure must preserve the current runtime behavior. Converting the Agent runtime
from its existing JSONL subprocess integration to an independent HTTP service is explicitly
outside this change.

## Target Layout

```text
zeromind/
├── apps/
│   ├── information/
│   │   ├── src/
│   │   ├── tests/
│   │   ├── migrations/
│   │   ├── scripts/
│   │   ├── docs/
│   │   ├── pyproject.toml
│   │   ├── alembic.ini
│   │   └── Dockerfile
│   ├── knowledge/
│   │   └── README.md
│   ├── agent-runtime/
│   │   ├── src/
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   └── Dockerfile
│   └── web/
│       ├── src/
│       ├── package.json
│       ├── tsconfig*.json
│       ├── nginx.conf
│       └── Dockerfile
├── compose.yaml
├── .env.example
├── .dockerignore
├── .gitignore
└── README.md
```

## Ownership Rules

- `apps/information` owns the AI information aggregation domain and all current Python
  backend code, database migrations, tests, scripts, examples, design history, and
  operations documentation.
- `apps/knowledge` is reserved for the knowledge-management backend. This restructure adds
  only a README defining its responsibility; it does not select or scaffold a framework.
- `apps/agent-runtime` owns the TypeScript Agent execution runtime currently named
  `pi-runner`.
- `apps/web` owns the React and TypeScript frontend.
- Database migrations, application tests, and application documentation remain inside the
  application that owns them.
- The root contains no generic `database`, `tests`, or `docs` directory.
- Cross-application artifacts are introduced at the root only when a concrete need exists.
  The root README remains the entry point for the repository as a whole.

## File Migration

```text
backend/   -> apps/information/
frontend/  -> apps/web/
pi-runner/ -> apps/agent-runtime/
docs/      -> apps/information/docs/
```

The untracked `.env.save` file is user-owned and must not be read, moved, modified, or
committed.

## Build and Deployment

The root `compose.yaml` continues to deploy the current stack together. Build contexts,
Dockerfile paths, bind paths, and commands are updated for the new application paths.

The information service continues to launch its API, worker, scheduler, and migration jobs
from the same Python project. The Agent runtime continues to be built and invoked through
the existing JSONL subprocess contract so this directory-only change does not also become a
network protocol migration.

The web and Agent runtime applications retain their own pnpm workspace files and lockfiles.
There is no root JavaScript workspace: application dependencies, scripts, and lockfiles stay
with the application that owns them, which keeps each application independently buildable.

## Application Communication

The intended future architecture uses HTTP between the information, knowledge, and Agent
runtime applications. Each application will own its database tables within the shared
PostgreSQL instance and must not write another application's tables. Cross-application ORM
models and cross-application foreign keys are prohibited so applications can later move to
separate databases.

The HTTP conversion and knowledge-service implementation are not part of this restructure.

## Documentation

Existing examples, operational guidance, plans, and specifications describe the information
application and move with it. Links in the root README and moved documentation are updated
to remain valid. Future application-specific documentation is created under that
application's `docs` directory.

## Verification

After moving files and updating paths:

1. Search the repository for stale `backend/`, `frontend/`, `pi-runner/`, and root `docs/`
   references.
2. Run the information service unit tests, Ruff checks, mypy checks, and build validation.
3. Run Agent runtime tests, type checking, and build.
4. Run web tests, type checking, and build.
5. Validate the resolved Compose configuration and verify Docker build paths.
6. Confirm `.env.save` remains untouched and untracked.

## Rollout and Risk Control

The migration is performed as a path-only refactor with no intended API, database, or
runtime behavior changes. Moves retain Git history where possible. Any behavior-changing
work discovered during verification is separated from this restructure instead of being
silently included.
