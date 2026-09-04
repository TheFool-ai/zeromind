# Docker Secrets Implementation Plan

> Execute this plan sequentially with test-driven development. Each task ends
> with focused verification and a commit containing only the listed files.

**Goal:** Move ZeroMind production credentials from plaintext Compose
environment variables to least-privilege Docker Compose secret files while
preserving development compatibility and failing closed in production.

**Architecture:** Add one shared `NAME`/`NAME_FILE` resolver, make application
settings and dynamic Provider/webhook lookups consume it, construct the
PostgreSQL URL from a file-backed password, and grant each Compose service only
the secret mounts it needs. Compose file secrets use a dedicated supplemental
group because file sources are bind mounts and Docker Compose cannot remap
their ownership.

**Tech Stack:** Python 3.12, Pydantic Settings 2, SQLAlchemy 2, FastAPI,
Celery, pytest, Docker Compose v2, PostgreSQL 16, POSIX shell.

## Global Constraints

- Implement against
  `docs/superpowers/specs/2026-08-03-docker-secrets-design.md`.
- Never print, log, commit, copy into an image, or expose through `docker
  inspect` any secret value.
- An explicitly configured `*_FILE` source is authoritative; an invalid file
  never falls back to a plaintext environment value.
- Keep plaintext `NAME` environment variables working for development and
  tests, but production Compose uses only `*_FILE` references.
- Preserve Provider Profile `api_key_env` and webhook `secret_env` database/API
  fields as logical secret names; no migration is required.
- Keep backend and Pi runner containers non-root.
- Do not expose PostgreSQL, Redis, or secret source paths through public ports.
- Preserve the existing uncommitted work in
  `backend/migrations/env.py`,
  `backend/src/zeromind/shared/migration_config.py`, and
  `backend/tests/test_migration_config.py`. Extend it additively where this
  plan requires database secret support; never discard or overwrite its
  current behavior.
- Use a dedicated numeric group, default GID `20000`, for host secret files and
  consuming containers. Do not rely on Compose `uid`, `gid`, or `mode` fields
  for file-backed secrets because Docker documents that they are ignored.
- Every behavior change follows red-green-refactor: add a failing test, run it,
  implement the smallest change, then rerun the focused test.

## Target File Structure

- Create `backend/src/zeromind/shared/secrets.py`: shared sanitized secret
  resolution.
- Create `backend/tests/test_secrets.py`: precedence, parsing, and failure
  behavior.
- Modify `backend/src/zeromind/shared/config.py`: file references, database URL
  construction, and process-specific production validation.
- Modify `backend/src/zeromind/shared/migration_config.py`: reuse the same
  database URL resolution for Alembic.
- Modify `backend/src/zeromind/agents/domain.py`: resolve Provider credentials
  through the shared resolver.
- Modify `backend/src/zeromind/delivery/service.py`: resolve webhook secrets
  through the shared resolver.
- Modify `backend/src/zeromind/identity/tokens.py`: consume resolved API
  credentials and reject insecure production defaults.
- Modify `backend/src/zeromind/bootstrap/celery.py`: validate secrets according
  to the declared `api`, `worker`, `scheduler`, or `migrate` process role.
- Modify `backend/src/zeromind/bootstrap/app.py` and
  `backend/src/zeromind/bootstrap/tasks.py`: validate only the secrets required
  by each process path.
- Modify `compose.yaml`: declare secrets and per-service mounts.
- Create `deploy/rsshub-entrypoint.sh`: adapt RSSHub's environment-only token
  interface to a mounted secret file.
- Create `scripts/prepare-secrets.sh`: create/check the external directory and
  empty optional files without ever accepting secret values as command-line
  arguments.
- Create `backend/tests/test_compose_secrets.py`: verify rendered Compose
  structure and absence of sentinel secret values.
- Modify `.env.example`, `.gitignore`, `README.md`, and
  `docs/operations.md`: deployment, migration, rotation, and recovery guidance.

---

### Task 1: Shared Secret Resolver

**Files:**

- Create: `backend/src/zeromind/shared/secrets.py`
- Create: `backend/tests/test_secrets.py`

**Public interface:** `SecretResolutionError`, plus typed `resolve_secret` and
`require_secret` functions accepting a logical name, optional plaintext
fallback, optional explicit file path, and injectable environment mapping.
`resolve_secret` returns `str | None`; `require_secret` returns `str` or raises
the sanitized error.

- [ ] Write tests proving:
  - `NAME_FILE` wins over `NAME` and the supplied fallback;
  - an explicit `file_path` wins over all plaintext sources;
  - a single trailing LF or CRLF is removed while other whitespace is kept;
  - missing, unreadable, non-UTF-8, empty, and newline-only files raise
    `SecretResolutionError` without including content;
  - a broken configured file never falls back to `NAME`;
  - `resolve_secret` returns `None` only when no source is configured;
  - `require_secret` reports only the logical secret name.
- [ ] Run `cd backend && ../.venv/bin/pytest tests/test_secrets.py -q` and
  verify RED because the module does not exist.
- [ ] Implement the resolver with an injectable environment mapping and direct
  `Path.read_text(encoding="utf-8")`; do not catch errors in a way that leaks
  paths containing secret material or file contents.
- [ ] Rerun the focused tests and verify GREEN.
- [ ] Run Ruff and mypy on the new module.
- [ ] Commit only these two files with `feat: add file-backed secret resolver`.

---

### Task 2: Settings, Production Validation, and Database URL

**Files:**

- Modify: `backend/src/zeromind/shared/config.py`
- Modify: `backend/src/zeromind/shared/database.py`
- Modify: `backend/src/zeromind/shared/migration_config.py`
- Modify: `backend/tests/test_config.py`
- Modify: `backend/tests/test_migration_config.py`

**Interfaces:**

- Add file-reference settings for administrator password, token secret,
  credential encryption secret, and PostgreSQL password.
- Add non-secret database component settings with production defaults:
  driver `postgresql+psycopg`, host `postgres`, port `5432`, user/database
  `zeromind`.
- Preserve explicit `ZEROMIND_DATABASE_URL` for development and tests.
- Produce one sanitized `Settings.resolved_database_url` used by runtime and
  Alembic.
- Provide process-scoped validation methods such as `validate_api_secrets()`
  and `validate_worker_secrets()` instead of forcing scheduler/migrate to mount
  unrelated credentials.

- [ ] Extend `backend/tests/test_config.py` with failing tests for:
  - file-backed known settings overriding plaintext values;
  - URL-encoding special characters in the database password;
  - an explicit development `database_url` remaining authoritative when no
    password file is configured;
  - production API validation rejecting `change-me`, development token
    defaults, missing credential secrets, and empty database credentials;
  - worker validation requiring database and credential encryption secrets but
    not administrator credentials;
  - all validation errors remaining sanitized.
- [ ] Extend the existing migration configuration test so Alembic receives the
  exact same file-backed URL as `Settings`, while retaining its current
  environment-URL override test.
- [ ] Run the two test files and verify RED.
- [ ] Implement resolved secret properties and process-scoped validators.
  Require token and credential encryption secrets to contain at least 32 bytes
  and reject all shipped development/default values; do not claim to estimate
  entropy from character composition.
  Build database URLs with SQLAlchemy's URL helper or correctly quoted
  components; never concatenate an unescaped password.
- [ ] Change `create_database` to consume `resolved_database_url`.
- [ ] Refactor `apply_database_url` to call the shared resolution path without
  importing application bootstrap code.
- [ ] Run focused tests, then `ruff check` and `mypy` for the changed modules.
- [ ] Commit only the additive settings/database changes with
  `feat: load application secrets from files`. If the pre-existing migration
  hunks cannot be separated safely, stop and obtain explicit staging guidance
  rather than silently absorbing them.

---

### Task 3: Provider, Webhook, Identity, and Credential Cipher Wiring

**Files:**

- Modify: `backend/src/zeromind/agents/domain.py`
- Modify: `backend/src/zeromind/delivery/service.py`
- Modify: `backend/src/zeromind/identity/tokens.py`
- Modify: `backend/src/zeromind/bootstrap/app.py`
- Modify: `backend/src/zeromind/bootstrap/celery.py`
- Modify: `backend/src/zeromind/bootstrap/tasks.py`
- Modify: `backend/tests/agents/test_registry.py`
- Modify: `backend/tests/agents/test_gateway.py`
- Modify: `backend/tests/delivery/test_webhook.py`
- Modify: `backend/tests/identity/test_auth.py`
- Modify: `backend/tests/rsshub/test_credentials.py`

- [ ] Add failing Provider tests that set `OPENAI_API_KEY_FILE` or
  `GLM_API_KEY_FILE`, prove the file value reaches the Pi request, and prove the
  Profile/database/API still expose only the logical name.
- [ ] Add failing webhook tests proving `SECRET_FILE` signs with the file value
  and a broken file yields a sanitized missing-credential error.
- [ ] Add identity tests proving file-backed administrator/token secrets work
  and insecure production defaults prevent API startup.
- [ ] Add credential cipher tests proving a file-backed credential secret can
  decrypt existing ciphertext produced with the same plaintext value.
- [ ] Run the focused suites and verify RED.
- [ ] Replace direct `os.getenv` calls in Provider and webhook code with the
  shared resolver. Preserve lazy resolution so unused optional integrations do
  not prevent startup.
- [ ] Resolve and validate API secrets before registering routes or accepting
  requests; validate worker secrets at the beginning of worker-owned task
  paths. Add an explicit non-secret `ZEROMIND_PROCESS_ROLE` per Compose service
  so Celery worker startup validates worker requirements while Celery Beat does
  not require Provider or administrator secrets.
- [ ] Keep errors at the current logical-name level; never include paths or
  values returned by the resolver.
- [ ] Run all agent, delivery, identity, and RSSHub credential tests.
- [ ] Run Ruff and mypy for the backend.
- [ ] Commit with `feat: use secret files across credential consumers`.

---

### Task 4: Compose Secret Definitions and Least-Privilege Mounts

**Files:**

- Modify: `compose.yaml`
- Create: `deploy/rsshub-entrypoint.sh`
- Modify: `.dockerignore`
- Modify: `.gitignore`

**Secret inventory:**

- Required: `postgres_password`, `admin_password`, `token_secret`,
  `credential_secret`.
- Optional but predeclared: `glm_api_key`, `openai_api_key`,
  `anthropic_api_key`, `webhook_secret`, `twitter_auth_token`.

**Mount matrix:**

| Service | Secrets |
| --- | --- |
| `postgres` | `postgres_password` |
| `migrate` | `postgres_password` |
| `api` | PostgreSQL, admin, token, credential, Provider keys |
| `worker` | PostgreSQL, credential, Provider keys, webhook |
| `scheduler` | none |
| `rsshub` | Twitter token |
| `frontend`, `redis` | none |

- [ ] Split the broad backend anchor so services do not inherit unrelated
  secrets or plaintext credential defaults. Remove `env_file: .env`; Compose
  may still use `.env` for interpolation, but its entire contents must not be
  injected into backend processes.
- [ ] Add top-level file-backed secrets sourced from
  `${ZEROMIND_SECRETS_DIR:-./secrets}` with filenames exactly matching the
  secret inventory above.
- [ ] Set only path references such as
  `ZEROMIND_ADMIN_PASSWORD_FILE=/run/secrets/admin_password` and
  `GLM_API_KEY_FILE=/run/secrets/glm_api_key`.
- [ ] Configure PostgreSQL with `POSTGRES_PASSWORD_FILE`; remove
  `POSTGRES_PASSWORD` and the password-bearing `ZEROMIND_DATABASE_URL`.
- [ ] Add `group_add: ["${ZEROMIND_SECRET_GID:-20000}"]` only to consumers.
  Do not specify ineffective secret `uid/gid/mode` fields.
- [ ] Add a minimal RSSHub entrypoint that reads
  `/run/secrets/twitter_auth_token`, exports it only for the upstream process,
  and `exec`s `npm run start` under `dumb-init`. Empty optional token files
  produce an unset/empty token without logging it. Bind-mount the repository
  script read-only at a fixed container path and replace the service entrypoint
  with `dumb-init -- /usr/local/bin/zeromind-rsshub-entrypoint`; make the host
  script executable and do not embed shell source in the Compose command.
- [ ] Ignore `/secrets/` and the deployment secret directory from build and
  Git contexts.
- [ ] Render the configuration with sentinel source files and verify:
  - no sentinel appears in rendered YAML/JSON;
  - no service environment contains plaintext credential values;
  - each service has exactly the mount matrix above;
  - database/Redis ports remain private;
  - `docker compose config --quiet` succeeds.
- [ ] Build the backend and RSSHub configuration and verify every non-root
  consumer can read only its mounted files using the supplemental GID.
- [ ] Commit with `feat: mount production credentials as Docker secrets`.

---

### Task 5: Automated Compose Contract Tests

**Files:**

- Create: `backend/tests/test_compose_secrets.py`

- [ ] Write a test fixture that creates a temporary secret directory with
  unique sentinel values and all required/optional source files.
- [ ] Invoke `docker compose config --format json` with
  `ZEROMIND_SECRETS_DIR` pointing at that fixture. Skip only when the Docker
  Compose CLI is genuinely unavailable; malformed configuration must fail.
- [ ] Assert rendered service environments contain only `*_FILE` paths and no
  sentinel values.
- [ ] Assert the exact per-service secret mount matrix, top-level source files,
  `POSTGRES_PASSWORD_FILE`, and supplemental group configuration.
- [ ] Assert optional empty files are accepted by Compose while application
  resolution rejects them only if the corresponding integration is used.
- [ ] Run `cd backend && ../.venv/bin/pytest tests/test_compose_secrets.py -q`.
- [ ] Commit with `test: verify Docker secret isolation`.

---

### Task 6: Provisioning, Migration, Rotation, and Recovery Documentation

**Files:**

- Create: `scripts/prepare-secrets.sh`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/operations.md`

- [ ] Write `prepare-secrets.sh` to:
  - require root or a caller-selected target directory and GID;
  - create the directory as `0750 root:20000` by default;
  - create missing secret files as `0640 root:20000` by default;
  - never accept secret values as CLI arguments and never echo file contents;
  - leave existing files and values unchanged;
  - fail if permissions/ownership are broader than the contract.
- [ ] Replace secret values in `.env.example` with only non-secret deployment
  settings: `ZEROMIND_SECRETS_DIR`, `ZEROMIND_SECRET_GID`, port, admin username,
  and RSSHub private hostname.
- [ ] Update quick start instructions to prepare and populate secret files via
  `sudoedit`, then run Compose. Explicitly list required versus optional files.
- [ ] Document one-time migration from the current `.env` without commands that
  place values in shell history.
- [ ] Document rotation order for Provider/webhook keys, administrator/token
  secrets, PostgreSQL password, and the credential encryption secret.
- [ ] Document encrypted off-host backup and restore validation. State clearly
  that Docker secrets do not protect a compromised root/Docker daemon.
- [ ] Run `shellcheck` if installed and at minimum `sh -n` on the script.
- [ ] Run a disposable-directory provisioning test twice to prove idempotence
  and preservation of existing secret values.
- [ ] Commit with `docs: document Docker secret operations`.

---

### Task 7: Full Verification and Operational Smoke Test

**Files:** No required source changes; fix only failures attributable to this
plan and keep fixes in the task that owns the behavior.

- [ ] Run backend unit/integration tests:

```bash
(cd backend && ../.venv/bin/pytest -q)
(cd backend && ../.venv/bin/ruff check .)
(cd backend && ../.venv/bin/mypy src)
```

- [ ] Run frontend and Pi runner regression suites:

```bash
(cd frontend && npm test && npm run typecheck && npm run build)
(cd pi-runner && pnpm test && pnpm typecheck && pnpm build)
```

- [ ] Create a disposable secret directory, render Compose, and build all
  changed images:

```bash
secret_test_dir="$(mktemp -d)"
for secret_name in postgres_password admin_password token_secret credential_secret \
  glm_api_key openai_api_key anthropic_api_key webhook_secret twitter_auth_token; do
  : > "$secret_test_dir/$secret_name"
done
ZEROMIND_SECRETS_DIR="$secret_test_dir" docker compose config --quiet
ZEROMIND_SECRETS_DIR="$secret_test_dir" docker compose build
```

- [ ] On the deployment host, back up the current `.env`, populate the external
  secret directory, and recreate `postgres`, `migrate`, `api`, `worker`,
  `scheduler`, and `rsshub` in the documented order. Do not rotate actual
  credentials during this migration.
- [ ] Verify health and authentication, then register/use the GLM Provider with
  `provider=zai`, `model=glm-5.2`, and `api_key_env=GLM_API_KEY`.
- [ ] Confirm `docker inspect` for every container contains no Provider,
  administrator, database, token, credential, webhook, or Twitter secret
  value.
- [ ] Confirm each container can read only the secrets in the mount matrix and
  that no secret source directory is present in an image layer.
- [ ] Trigger one feed fetch, one Agent workflow, and one test webhook delivery;
  verify sanitized failures for any intentionally empty optional secret.
- [ ] Review `git diff`, ensure the three pre-existing migration changes were
  preserved, and ensure no secret file or value is tracked.
- [ ] Record the verification commands and outcomes in the final handoff.

## Rollback Gate

Rollback is allowed only before rotating upstream credentials. Restore the
protected legacy environment file and prior Compose revision, recreate
services, and verify readiness. If any credential was rotated, use its
credential-specific rollback procedure instead of blindly restoring old
configuration. Never replace `ZEROMIND_CREDENTIAL_SECRET` while encrypted
RSSHub Access Keys still depend on it.
