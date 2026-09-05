# Internal RSSHub Compose Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bundle a private RSSHub container with ZeroMind and allow only the feed worker to fetch it through the exact Compose hostname `rsshub`.

**Architecture:** Add a no-host-port RSSHub service that reuses Redis database 1, while ZeroMind and Celery retain Redis database 0. Extend the outbound network policy with an opt-in exact-host private-address allowlist, configure only scheduled feed fetching to use it, and keep all other outbound consumers on the existing public-only default.

**Tech Stack:** Docker Compose v2, `diygod/rsshub`, Redis 7, Python 3.12, Pydantic Settings, pytest, Ruff, mypy.

## Global Constraints

- RSSHub must not publish a host port.
- The internal Base URL is exactly `http://rsshub:1200`.
- RSSHub cache uses `redis://redis:6379/1`; Celery remains on `redis://redis:6379/0`.
- The private-address exception matches exact normalized hostnames only; it never matches suffixes, arbitrary IP ranges, or IP literals.
- `NetworkPolicy()` keeps an empty allowlist by default.
- Only scheduled feed fetching consumes `ZEROMIND_RSSHUB_PRIVATE_HOSTS`.
- Do not modify or stage the pre-existing changes in `backend/init-sql/env.py`, `backend/src/zeromind/shared/migration_config.py`, or `backend/tests/test_migration_config.py`.
- Do not automatically seed PostgreSQL or configure an RSSHub `ACCESS_KEY`.

---

## File Structure

- `backend/src/zeromind/shared/config.py`: parse the comma-separated RSSHub private hostname setting into a normalized immutable set.
- `backend/src/zeromind/content/network_policy.py`: enforce the opt-in exact-host exception while preserving public-only defaults.
- `backend/src/zeromind/bootstrap/tasks.py`: pass the configured hostname set only to the scheduled feed client's policy.
- `backend/tests/content/test_network_policy.py`: prove the allowlist permits only the named host and never a private IP literal.
- `backend/tests/test_config.py`: prove deterministic configuration parsing.
- `compose.yaml`: run the private RSSHub service and inject the trusted hostname setting into backend containers.
- `.env.example`: expose the trusted-host configuration with its safe Compose default.
- `README.md`: document first-time built-in instance registration.
- `docs/operations.md`: document isolation, health checking, Redis separation, and the optional Chromium image.

---

### Task 1: Exact-Host Private Network Policy

**Files:**
- Modify: `backend/src/zeromind/shared/config.py`
- Modify: `backend/src/zeromind/content/network_policy.py`
- Modify: `backend/tests/content/test_network_policy.py`
- Create: `backend/tests/test_config.py`

**Interfaces:**
- Produces: `Settings.rsshub_private_hosts: str`.
- Produces: `Settings.rsshub_private_hostnames: frozenset[str]`.
- Produces: `NetworkPolicy(..., private_host_allowlist: Collection[str] | None = None)`.
- Consumes: the existing async `AddressResolver` and `validate_url(url) -> ValidatedTarget` contract.

- [ ] **Step 1: Write failing configuration parsing tests**

Create `backend/tests/test_config.py`:

```python
from zeromind.shared.config import Settings


def test_rsshub_private_hostnames_are_normalized() -> None:
    settings = Settings(
        _env_file=None,
        rsshub_private_hosts=" RSSHub, rsshub.,,SECONDARY ",
    )

    assert settings.rsshub_private_hostnames == frozenset({"rsshub", "secondary"})


def test_rsshub_private_hostnames_default_to_empty() -> None:
    settings = Settings(_env_file=None)

    assert settings.rsshub_private_hostnames == frozenset()
```

- [ ] **Step 2: Run the settings tests and verify RED**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_config.py -q
```

Expected: FAIL because `Settings` has no `rsshub_private_hostnames` property.

- [ ] **Step 3: Implement minimal settings parsing**

Add to `Settings`:

```python
rsshub_private_hosts: str = ""

@property
def rsshub_private_hostnames(self) -> frozenset[str]:
    return frozenset(
        normalized
        for item in self.rsshub_private_hosts.split(",")
        if (normalized := item.strip().lower().rstrip("."))
    )
```

- [ ] **Step 4: Run the settings tests and verify GREEN**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_config.py -q
```

Expected: 2 passed.

- [ ] **Step 5: Write failing network-policy tests**

Append to `backend/tests/content/test_network_policy.py`:

```python
@pytest.mark.asyncio
async def test_network_policy_accepts_private_address_for_exact_trusted_host() -> None:
    async def private_resolver(_: str) -> tuple[str, ...]:
        return ("172.20.0.8",)

    policy = NetworkPolicy(
        resolver=private_resolver,
        private_host_allowlist={"RSSHUB."},
    )

    target = await policy.validate_url("http://rsshub:1200/test/1")

    assert target.host == "rsshub"
    assert target.addresses == ("172.20.0.8",)


@pytest.mark.asyncio
async def test_network_policy_rejects_private_address_for_untrusted_host() -> None:
    async def private_resolver(_: str) -> tuple[str, ...]:
        return ("172.20.0.8",)

    policy = NetworkPolicy(
        resolver=private_resolver,
        private_host_allowlist={"rsshub"},
    )

    with pytest.raises(BlockedNetworkTarget):
        await policy.validate_url("http://postgres:5432/")


@pytest.mark.asyncio
async def test_network_policy_does_not_allow_private_ip_literals() -> None:
    policy = NetworkPolicy(private_host_allowlist={"172.20.0.8"})

    with pytest.raises(BlockedNetworkTarget):
        await policy.validate_url("http://172.20.0.8:1200/test/1")


@pytest.mark.asyncio
async def test_network_policy_requires_explicit_private_host_allowlist() -> None:
    async def private_resolver(_: str) -> tuple[str, ...]:
        return ("172.20.0.8",)

    policy = NetworkPolicy(resolver=private_resolver)

    with pytest.raises(BlockedNetworkTarget):
        await policy.validate_url("http://rsshub:1200/test/1")
```

- [ ] **Step 6: Run the network-policy tests and verify RED**

Run:

```bash
cd backend
../.venv/bin/pytest tests/content/test_network_policy.py -q
```

Expected: FAIL with `TypeError` because `NetworkPolicy.__init__` does not accept `private_host_allowlist`.

- [ ] **Step 7: Implement the exact-host exception**

Import `Collection` and normalize the constructor input:

```python
class NetworkPolicy:
    def __init__(
        self,
        *,
        resolver: AddressResolver | None = None,
        private_host_allowlist: Collection[str] | None = None,
    ) -> None:
        self._resolver = resolver or _resolve_host
        self._private_host_allowlist = frozenset(
            normalized
            for item in private_host_allowlist or ()
            if (normalized := item.strip().lower().rstrip("."))
        )
```

In `validate_url`, distinguish DNS hostnames from IP literals and permit a
non-global address only when the DNS hostname exactly matches the set:

```python
try:
    literal = ipaddress.ip_address(host)
except ValueError:
    is_hostname = True
    # retain the existing resolver and error translation
else:
    is_hostname = False
    addresses = (str(literal),)

private_host_is_allowed = (
    is_hostname and host.rstrip(".") in self._private_host_allowlist
)
```

Keep invalid resolver results rejected. Change only the non-global test to:

```python
if not parsed_address.is_global and not private_host_is_allowed:
    raise BlockedNetworkTarget(
        f"destination address {parsed_address} is not public"
    )
```

- [ ] **Step 8: Run focused and full content tests**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_config.py tests/content -q
```

Expected: all selected tests pass.

- [ ] **Step 9: Commit Task 1 without unrelated migration changes**

```bash
git add backend/src/zeromind/shared/config.py \
  backend/src/zeromind/content/network_policy.py \
  backend/tests/content/test_network_policy.py \
  backend/tests/test_config.py
git commit -m "feat: allow configured private RSSHub hosts"
```

---

### Task 2: Worker and Private RSSHub Compose Wiring

**Files:**
- Modify: `backend/src/zeromind/bootstrap/tasks.py`
- Modify: `compose.yaml`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `Settings.rsshub_private_hostnames: frozenset[str]` from Task 1.
- Consumes: `NetworkPolicy(private_host_allowlist=...)` from Task 1.
- Produces: private Compose service `rsshub` at `http://rsshub:1200`.

- [ ] **Step 1: Wire only scheduled feed fetching to the allowlist**

Change the feed client construction in `_poll_feed` to:

```python
feed_client=FeedClient(
    network_policy=NetworkPolicy(
        private_host_allowlist=settings.rsshub_private_hostnames,
    )
),
```

Do not change any other `NetworkPolicy()` construction.

- [ ] **Step 2: Add the backend Compose setting**

Add to the `x-backend.environment` mapping:

```yaml
ZEROMIND_RSSHUB_PRIVATE_HOSTS: ${ZEROMIND_RSSHUB_PRIVATE_HOSTS:-rsshub}
```

This makes the exception explicit and lets an operator override it with an
empty value when the bundled instance is disabled.

- [ ] **Step 3: Add the private RSSHub service**

Add after `redis` in `compose.yaml`:

```yaml
rsshub:
  image: diygod/rsshub:latest
  environment:
    NODE_ENV: production
    CACHE_TYPE: redis
    REDIS_URL: redis://redis:6379/1
  depends_on:
    redis:
      condition: service_healthy
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:1200/healthz"]
    interval: 10s
    timeout: 5s
    retries: 12
  restart: unless-stopped
```

Do not add `ports` or `expose`; Compose DNS and the image's declared port are
sufficient for container-to-container traffic.

- [ ] **Step 4: Document the environment setting**

Add to `.env.example`:

```dotenv
# Exact private DNS names allowed only for scheduled feed fetching.
ZEROMIND_RSSHUB_PRIVATE_HOSTS=rsshub
```

- [ ] **Step 5: Validate the rendered Compose model**

Run:

```bash
docker compose config --quiet
docker compose config | rg -n "rsshub|redis://redis:6379/1|RSSHUB_PRIVATE_HOSTS"
```

Expected: exit 0; the rendered model contains the private `rsshub` service,
Redis database 1, and the backend setting, with no published RSSHub port.

- [ ] **Step 6: Run backend static checks for the wiring**

Run:

```bash
cd backend
../.venv/bin/ruff check src/zeromind/shared/config.py \
  src/zeromind/content/network_policy.py src/zeromind/bootstrap/tasks.py \
  tests/test_config.py tests/content/test_network_policy.py
../.venv/bin/mypy src
```

Expected: both commands exit 0.

- [ ] **Step 7: Commit Task 2 without unrelated migration changes**

```bash
git add backend/src/zeromind/bootstrap/tasks.py compose.yaml .env.example
git commit -m "feat: bundle private RSSHub service"
```

---

### Task 3: Operator Documentation and Runtime Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/operations.md`

**Interfaces:**
- Consumes: Compose service `rsshub` and Base URL `http://rsshub:1200` from Task 2.
- Produces: exact administrator setup and troubleshooting instructions.

- [ ] **Step 1: Update the quick start**

In the README first-time configuration section, state that the Compose stack
includes a private RSSHub service and replace the generic first step with these
exact values:

```text
名称：Built-in RSSHub
Base URL：http://rsshub:1200
Access Key：留空
鉴权模式：key
```

Keep the instruction that the first enabled instance becomes active.

- [ ] **Step 2: Update RSSHub operations guidance**

Add an `内置 Compose 实例` subsection to `docs/operations.md` that records:

- the service has no host port and is unreachable directly from the host;
- ZeroMind containers use `http://rsshub:1200`;
- RSSHub cache uses Redis database 1 while Celery uses database 0;
- `ZEROMIND_RSSHUB_PRIVATE_HOSTS=rsshub` is an exact-host feed-worker exception;
- changing the image to `diygod/rsshub:chromium-bundled` enables routes requiring Chromium at a higher resource cost;
- provider credentials such as `TWITTER_AUTH_TOKEN` belong in the `rsshub.environment` mapping.

- [ ] **Step 3: Build and start the changed services**

Run:

```bash
docker compose up --build -d rsshub worker
docker compose ps rsshub worker
```

Expected: both services are running and `rsshub` becomes healthy.

- [ ] **Step 4: Verify policy and feed parsing from the worker**

Run:

```bash
docker compose exec -T worker python -c '
import asyncio
from zeromind.content.network_policy import NetworkPolicy
from zeromind.ingestion.feed_client import FeedClient

async def main():
    policy = NetworkPolicy(private_host_allowlist={"rsshub"})
    result = await FeedClient(network_policy=policy).fetch(
        "http://rsshub:1200/test/1"
    )
    print(type(result).__name__, len(getattr(result, "entries", ())))

asyncio.run(main())
'
```

Expected: exit 0 and output beginning with `FeedDocument` with at least one
entry.

- [ ] **Step 5: Run full verification**

Run:

```bash
cd backend
../.venv/bin/pytest -q
../.venv/bin/ruff check src tests
../.venv/bin/mypy src
cd ..
docker compose config --quiet
git diff --check
```

Expected: every command exits 0 with no test, lint, type, Compose, or whitespace
errors.

- [ ] **Step 6: Commit documentation**

```bash
git add README.md docs/operations.md
git commit -m "docs: explain built-in RSSHub setup"
```

- [ ] **Step 7: Audit the final change set**

Run:

```bash
git status --short
git log -4 --oneline
git diff HEAD~3..HEAD --stat
```

Expected: only the user's pre-existing migration-related changes remain
uncommitted; the last three commits contain the network policy, Compose wiring,
and documentation changes.
