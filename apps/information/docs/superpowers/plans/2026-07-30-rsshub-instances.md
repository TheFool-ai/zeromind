# RSSHub Instances Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept `rsshub://` subscriptions and fetch them through a registered,
active RSSHub instance whose optional access key is encrypted at rest.

**Architecture:** Keep the subscription aggregate instance-independent and add
an `rsshub` bounded context for instance lifecycle, credential protection, and
runtime locator resolution. The control-plane API owns one global active
instance, while the worker resolves logical locators immediately before the
existing network-policy-protected feed fetch.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, cryptography
Fernet, pytest, React 19, TypeScript, TanStack Query, Vitest.

## Global Constraints

- Preserve direct HTTP and HTTPS subscription behavior.
- Persist logical `rsshub://` locators; never persist their resolved URLs.
- Allow zero or one active RSSHub instance and reject disabling or deleting it.
- Encrypt access keys before persistence and never return them from the API.
- Keep Twitter/provider credentials inside RSSHub, not ZeroMind.
- Do not expose resolved URLs because they may contain an instance access key.
- Do not include the pre-existing migration startup fix in feature commits.

---

### Task 1: RSSHub Locator Domain

**Files:**
- Modify: `backend/src/zeromind/subscriptions/domain.py`
- Modify: `backend/tests/subscriptions/test_domain.py`
- Modify: `backend/tests/subscriptions/test_opml.py`
- Modify: `backend/tests/subscriptions/test_api.py`
- Modify: `frontend/src/pages/subscriptions.tsx`
- Modify: `frontend/src/app.test.tsx`

**Interfaces:**
- Produces: `normalize_feed_url(value: str) -> str`, accepting normalized HTTP,
  HTTPS, and opaque `rsshub://` locators.
- Consumes: existing subscription creation and OPML preview paths.

- [ ] **Step 1: Write failing locator normalization tests**

Add literal expectations:

```python
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "RSSHUB://twitter/user/vista8?mode=full&lang=zh",
            "rsshub://twitter/user/vista8?mode=full&lang=zh",
        ),
        (
            "rsshub://Twitter/User/Vista8/%2Fencoded",
            "rsshub://Twitter/User/Vista8/%2Fencoded",
        ),
    ],
)
def test_normalize_feed_url_preserves_rsshub_route(
    raw: str,
    expected: str,
) -> None:
    assert normalize_feed_url(raw) == expected
```

Add rejection cases for an empty route, credentials, port, fragment, and `..`
path segments. Add OPML preview and API creation tests using
`rsshub://twitter/user/vista8`.

- [ ] **Step 2: Run tests and verify the missing behavior**

Run:

```bash
cd backend
../.venv/bin/pytest tests/subscriptions/test_domain.py \
  tests/subscriptions/test_opml.py tests/subscriptions/test_api.py -q
```

Expected: the new cases fail because the current normalizer accepts only HTTP
and HTTPS.

- [ ] **Step 3: Implement minimal RSSHub locator normalization**

Split `normalize_feed_url` into private HTTP and RSSHub branches. The RSSHub
branch must:

```python
if raw[:9].lower() != "rsshub://":
    raise ValueError(...)
parsed = urlsplit(raw)
```

Validate an authority plus a non-empty path, reject credentials, ports,
fragments and decoded `.`/`..` segments, then return
`"rsshub://" + raw[9:]` without decoding, case-changing, query sorting, or
slash collapsing.

- [ ] **Step 4: Run backend tests and verify green**

Run the command from Step 2. Expected: all selected tests pass.

- [ ] **Step 5: Write and verify the frontend acceptance test**

Add an application test that enters `rsshub://twitter/user/vista8` in the
subscription form and observes the same literal value in the POST body. Run:

```bash
cd frontend
pnpm test -- --run src/app.test.tsx
```

Expected before the UI change: the HTTP-only input rejects submission.

- [ ] **Step 6: Change the subscription form and display**

Change the feed input from `type="url"` to `type="text"`, add both accepted
forms to its help text, and render RSSHub locators as `<code>` rather than an
external link.

- [ ] **Step 7: Verify and commit**

Run:

```bash
cd backend
../.venv/bin/pytest tests/subscriptions -q
cd ../frontend
pnpm test -- --run src/app.test.tsx
```

Commit only Task 1 files:

```bash
git commit -m "feat: accept RSSHub subscription locators"
```

---

### Task 2: RSSHub Instance Aggregate, Encryption, and Persistence

**Files:**
- Create: `backend/src/zeromind/rsshub/__init__.py`
- Create: `backend/src/zeromind/rsshub/domain.py`
- Create: `backend/src/zeromind/rsshub/credentials.py`
- Create: `backend/src/zeromind/rsshub/models.py`
- Create: `backend/src/zeromind/rsshub/repository.py`
- Create: `backend/src/zeromind/rsshub/service.py`
- Create: `backend/tests/rsshub/__init__.py`
- Create: `backend/tests/rsshub/test_domain.py`
- Create: `backend/tests/rsshub/test_credentials.py`
- Create: `backend/tests/rsshub/test_repository.py`
- Create: `backend/tests/rsshub/test_service.py`
- Create: `backend/init-sql/versions/0007_rsshub_instances.py`
- Modify: `backend/init-sql/env.py`
- Modify: `backend/src/zeromind/shared/config.py`
- Modify: `backend/pyproject.toml`
- Modify: `compose.yaml`
- Modify: `.env.example`

**Interfaces:**
- Produces: `RSSHubInstance`, `RSSHubAuthenticationMode`, and
  `normalize_instance_base_url`.
- Produces: `CredentialCipher.encrypt(str) -> str` and
  `CredentialCipher.decrypt(str) -> str`.
- Produces: async `RSSHubInstanceService.create`, `update`, `list`, `activate`,
  `delete`, and `get_active`.
- Produces: in-memory and SQLAlchemy repository implementations with atomic
  active-instance replacement.

- [ ] **Step 1: Write failing domain and credential tests**

Cover normalization and access-key secrecy with literal assertions:

```python
def test_instance_base_url_is_normalized() -> None:
    assert normalize_instance_base_url(
        "HTTPS://RSS.EXAMPLE.COM:443/prefix/"
    ) == "https://rss.example.com/prefix"


def test_credential_cipher_round_trips_without_storing_plaintext() -> None:
    cipher = CredentialCipher("test-credential-secret")
    encrypted = cipher.encrypt("rsshub-secret")
    assert encrypted != "rsshub-secret"
    assert "rsshub-secret" not in encrypted
    assert cipher.decrypt(encrypted) == "rsshub-secret"
```

Reject non-HTTP schemes, credentials, query strings, fragments and empty
names.

- [ ] **Step 2: Verify the tests fail for missing types**

Run:

```bash
cd backend
../.venv/bin/pytest tests/rsshub/test_domain.py \
  tests/rsshub/test_credentials.py -q
```

Expected: import failures because the RSSHub context does not exist.

- [ ] **Step 3: Add minimal domain and credential implementation**

Add `cryptography>=45,<47`. Derive a Fernet key using SHA-256 of
`ZEROMIND_CREDENTIAL_SECRET`, and expose only encrypted strings outside the
cipher. Model authentication modes as `key` and `code`.

- [ ] **Step 4: Verify domain and credential tests pass**

Install the editable development package if required:

```bash
cd backend
../.venv/bin/pip install -e '.[dev]'
../.venv/bin/pytest tests/rsshub/test_domain.py \
  tests/rsshub/test_credentials.py -q
```

- [ ] **Step 5: Write failing repository and service tests**

Use the real in-memory repository to prove:

```python
first = await service.create(
    name="Primary",
    base_url="https://rsshub.example.com",
    access_key="secret",
)
second = await service.create(
    name="Backup",
    base_url="https://backup.example.com",
)
assert first.active is True
assert second.active is False

activated = await service.activate(second.id)
assert activated.active is True
assert (await service.get(first.id)).active is False
```

Also prove duplicate names/base URLs are rejected, disabled instances cannot
activate, the active instance cannot be disabled/deleted, update-without-key
preserves its encrypted secret, explicit clearing removes it, and the SQL
repository rehydrates an instance without plaintext leakage.

- [ ] **Step 6: Verify repository and service tests fail**

Run:

```bash
cd backend
../.venv/bin/pytest tests/rsshub/test_repository.py \
  tests/rsshub/test_service.py -q
```

Expected: failures because persistence and lifecycle services are absent.

- [ ] **Step 7: Implement persistence and lifecycle rules**

Persist:

```text
id, name, base_url, encrypted_access_key, authentication_mode,
enabled, active, created_at, updated_at
```

Create unique constraints for name and base URL plus a partial unique index on
`active = true`. Implement repository activation in one transaction by
clearing the old active row before setting the selected row. Translate
integrity errors to domain duplicate errors.

- [ ] **Step 8: Add settings, migration registration, and Compose secret**

Add `credential_secret` to `Settings`, expose
`ZEROMIND_CREDENTIAL_SECRET` in Compose, document a non-development value in
`.env.example`, import `RSSHubInstanceModel` from Alembic metadata, and add
migration `0007_rsshub_instances`.

- [ ] **Step 9: Verify and commit**

Run:

```bash
cd backend
../.venv/bin/pytest tests/rsshub -q
../.venv/bin/alembic upgrade head
```

Commit only Task 2 files, explicitly excluding the pre-existing migration
configuration changes:

```bash
git commit -m "feat: manage RSSHub instances securely"
```

---

### Task 3: RSSHub Instance API

**Files:**
- Create: `backend/src/zeromind/rsshub/api.py`
- Create: `backend/tests/rsshub/test_api.py`
- Modify: `backend/src/zeromind/bootstrap/app.py`

**Interfaces:**
- Consumes: `RSSHubInstanceService`.
- Produces: sanitized `/api/v1/rsshub/instances` endpoints.
- Produces: optional `rsshub_service` dependency injection in `create_app`.

- [ ] **Step 1: Write failing API lifecycle test**

Create an app with a real in-memory repository and cipher, then prove create,
list and activate:

```python
created = client.post(
    "/api/v1/rsshub/instances",
    json={
        "name": "Primary",
        "base_url": "https://rsshub.example.com",
        "access_key": "never-return-this",
        "authentication_mode": "key",
    },
)
assert created.status_code == 201
assert created.json()["has_access_key"] is True
assert "access_key" not in created.json()
```

Add tests for duplicate conflict, invalid input, disabled activation, active
delete rejection, secret preservation on omitted update, and explicit secret
clearing with `"access_key": null`.

- [ ] **Step 2: Verify the API tests fail**

Run:

```bash
cd backend
../.venv/bin/pytest tests/rsshub/test_api.py -q
```

Expected: 404 because the router is not registered.

- [ ] **Step 3: Implement sanitized request and response models**

Use a Pydantic update request whose `model_fields_set` distinguishes an omitted
`access_key` from explicit `null`. Map domain errors to stable codes:

```text
rsshub_instance_already_exists
rsshub_instance_not_found
rsshub_instance_in_use
invalid_rsshub_instance
```

Construct the production service from the SQL repository and
`CredentialCipher(get_settings().credential_secret)`.

- [ ] **Step 4: Verify and commit**

Run:

```bash
cd backend
../.venv/bin/pytest tests/rsshub/test_api.py tests/test_health.py -q
```

Commit:

```bash
git commit -m "feat: expose RSSHub instance management API"
```

---

### Task 4: Runtime Locator Resolution and Feed Polling

**Files:**
- Create: `backend/src/zeromind/rsshub/resolver.py`
- Create: `backend/tests/rsshub/test_resolver.py`
- Modify: `backend/src/zeromind/bootstrap/tasks.py`
- Modify: `backend/tests/integration/test_schedule.py`

**Interfaces:**
- Produces: `RSSHubResolver.resolve(locator: str) -> Awaitable[str]`.
- Consumes: active instance lookup and `CredentialCipher`.
- Preserves: HTTP and HTTPS locators unchanged.

- [ ] **Step 1: Write failing resolver tests**

Prove exact query behavior:

```python
assert await resolver.resolve(
    "rsshub://twitter/user/vista8?mode=full"
) == (
    "https://rsshub.example.com/twitter/user/vista8"
    "?mode=full&key=instance-secret"
)
```

Add a code-mode literal calculated independently with a known digest, a direct
URL pass-through case, an active-instance-missing error, a configured prefix
path case, and stripping locator-supplied `key`/`code` parameters.

- [ ] **Step 2: Verify resolver tests fail**

Run:

```bash
cd backend
../.venv/bin/pytest tests/rsshub/test_resolver.py -q
```

Expected: import failure because the resolver is absent.

- [ ] **Step 3: Implement minimal resolver**

For RSSHub locators, load the active instance, decrypt its access key, join its
base path with the opaque route, remove subscription-provided `key` and `code`
parameters, and append the configured `key` or MD5 `code`. Never log or return
the secret separately.

- [ ] **Step 4: Verify resolver tests pass**

Run the command from Step 2. Expected: all resolver tests pass.

- [ ] **Step 5: Write a failing worker integration test**

Exercise the polling boundary with a logical locator and a mock HTTP transport,
asserting that the request reaches the resolved instance URL and produces the
normal ingestion counts. The assertion targets the observed request URL, not
the mock's call count.

- [ ] **Step 6: Wire resolution into polling**

Construct a SQL RSSHub repository and credential cipher in `_poll_feed`, call
the resolver immediately before `FeedClient.fetch`, and retain the existing
network policy, conditional request headers, retry state, and subscription
failure bookkeeping.

- [ ] **Step 7: Verify and commit**

Run:

```bash
cd backend
../.venv/bin/pytest tests/rsshub/test_resolver.py \
  tests/integration/test_schedule.py tests/ingestion/test_feed_client.py -q
```

Commit:

```bash
git commit -m "feat: resolve RSSHub locators during polling"
```

---

### Task 5: RSSHub Instance Control-Plane UI

**Files:**
- Create: `frontend/src/pages/rsshub.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/app.tsx`
- Modify: `frontend/src/app.test.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: sanitized RSSHub instance API.
- Produces: `/rsshub` page with register, update, activate, and inactive-delete
  operations.

- [ ] **Step 1: Write failing UI test**

Mock complete API responses and prove the user can register an instance:

```typescript
await userEvent.type(screen.getByLabelText("实例名称"), "Primary");
await userEvent.type(
  screen.getByLabelText("Base URL"),
  "https://rsshub.example.com"
);
await userEvent.type(screen.getByLabelText("Access Key（可选）"), "secret");
await userEvent.click(screen.getByRole("button", {name: "添加实例"}));
```

Inspect the observed POST body for these literal values and verify the rendered
response says a key is configured without rendering `secret`. Add an activation
test that observes the selected row becoming active from the API response.

- [ ] **Step 2: Verify the UI test fails**

Run:

```bash
cd frontend
pnpm test -- --run src/app.test.tsx
```

Expected: the RSSHub navigation/page does not exist.

- [ ] **Step 3: Implement the page**

Add API types, navigation, route, query and mutations. The form supports name,
base URL, authentication mode, enabled state, and a write-only access key.
Rows show active/enabled/key-present states; activation is disabled for the
current or disabled instance, and deletion is disabled for the active
instance. Editing pre-fills only non-secret values.

- [ ] **Step 4: Verify and commit**

Run:

```bash
cd frontend
pnpm test -- --run src/app.test.tsx
pnpm build
```

Commit:

```bash
git commit -m "feat: add RSSHub instance configuration UI"
```

---

### Task 6: Full Verification and Operational Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/operations.md`
- Modify: `.env.example`

**Interfaces:**
- Documents: credential-secret rotation constraint, RSSHub instance setup, and
  provider credential boundary.

- [ ] **Step 1: Document the operator flow**

Describe setting a stable `ZEROMIND_CREDENTIAL_SECRET`, registering an RSSHub
instance in `/rsshub`, activating it, and configuring
`TWITTER_AUTH_TOKEN` on the RSSHub deployment rather than ZeroMind.

- [ ] **Step 2: Run all static and automated checks**

Run:

```bash
cd backend
../.venv/bin/ruff check .
../.venv/bin/mypy src
../.venv/bin/pytest -q
cd ../frontend
pnpm test -- --run
pnpm build
cd ../pi-runner
pnpm test -- --run
pnpm build
```

- [ ] **Step 3: Verify Docker migration and runtime**

Build and start the changed services, verify `migrate` exits successfully,
`api` and `frontend` become healthy, and query both:

```text
GET http://localhost:8080/
GET http://localhost:8080/api/v1/rsshub/instances
```

Do not add a real access key during the smoke test.

- [ ] **Step 4: Commit documentation-only changes**

Commit:

```bash
git commit -m "docs: explain RSSHub instance operations"
```

- [ ] **Step 5: Inspect history and worktree**

Confirm the feature is split across the planned commits and that the existing
migration startup fix remains uncommitted and unchanged.
