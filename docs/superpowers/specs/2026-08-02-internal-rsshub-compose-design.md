# Internal RSSHub Compose Design

## Goal

Bundle a private RSSHub service with ZeroMind's existing Docker Compose stack so
an administrator can register `http://rsshub:1200` as an RSSHub instance without
exposing RSSHub on a host port or weakening the general outbound-network policy.

## Scope

- Add a lightweight RSSHub container to the existing Compose application.
- Reuse the existing Redis service with a separate logical database for RSSHub
  cache data.
- Permit the feed worker to reach the exact Compose hostname `rsshub` even though
  it resolves to a private address.
- Keep all other private, loopback, link-local, and non-global destinations
  blocked.
- Document startup and the one-time ZeroMind instance registration.

This change does not automatically seed an RSSHub instance in PostgreSQL, expose
RSSHub outside the Compose network, configure route-provider credentials, or add
browser automation dependencies.

## Compose Architecture

Add a service named `rsshub` using `diygod/rsshub:latest`. It has no `ports`
mapping, so it is reachable only as `http://rsshub:1200` by containers on the
`zeromind_default` network.

RSSHub uses the existing `redis` service through `redis://redis:6379/1`. ZeroMind
and Celery retain `redis://redis:6379/0`, keeping cache keys and task transport in
separate logical databases. RSSHub depends on the healthy Redis service and has a
health check against `http://localhost:1200/healthz`.

The default image intentionally excludes bundled Chromium. Routes that require a
browser are outside this change; the image can later be changed to
`diygod/rsshub:chromium-bundled` without changing ZeroMind's integration.

## Network-Security Boundary

`NetworkPolicy` gains an optional collection of trusted private hostnames. Its
default remains empty, preserving current behavior everywhere.

Validation continues to require HTTP or HTTPS, a host, no URL credentials, and a
successful DNS result. If every resolved address is global, validation succeeds
as before. A non-global result succeeds only when the normalized URL hostname is
an exact member of the trusted collection. Trust is based on an exact hostname,
not suffix matching, URL prefixes, arbitrary private address ranges, or DNS
aliases.

Only scheduled feed fetching constructs `NetworkPolicy` with `rsshub` trusted.
Content resolution, webhooks, API operations, and default `NetworkPolicy()` users
receive no private-host exception. A direct subscription pointing to the exact
`rsshub` service is therefore reachable by the feed worker, but it cannot use the
exception to reach any other Compose service.

## Configuration and Registration

The trusted hostname is explicit application configuration rather than a
hard-coded production exception. Add `ZEROMIND_RSSHUB_PRIVATE_HOSTS` with an empty
default. Compose sets it to `rsshub` for backend containers. The setting accepts
a comma-separated list, trims whitespace, lowercases hostnames, removes a trailing
dot, and ignores empty entries.

After `docker compose up --build -d`, the administrator registers this sanitized
instance through the existing UI:

```text
Name: Built-in RSSHub
Base URL: http://rsshub:1200
Access Key: empty
Authentication mode: key
Enabled: yes
```

The first enabled instance becomes active through the existing RSSHub instance
service. No RSSHub `ACCESS_KEY` is required because the service is not published
outside the private Compose network.

## Failure Behavior

- If RSSHub is starting or unavailable, feed polling fails through the existing
  retry and health tracking behavior; direct HTTP(S) feeds remain unaffected.
- If the trusted-host environment setting is absent, `rsshub` resolves to a
  private address and remains blocked.
- `localhost`, `host.docker.internal`, literal private IPs, and other Compose
  service names remain blocked.
- RSSHub route/provider errors remain ordinary upstream feed failures and do not
  broaden network access.

## Testing and Verification

Backend tests cover configuration parsing and network-policy behavior:

- an exact trusted hostname resolving only to a private address is accepted;
- the same hostname is rejected without the trusted-host setting;
- an untrusted hostname and a private IP literal remain rejected;
- hostname matching is case-insensitive and exact;
- existing public-host behavior remains unchanged.

Compose verification renders the final configuration, starts RSSHub, waits for
its health check, and fetches `/test/1` from the worker container. The full
backend test, lint, and type-check suites verify that the narrowly scoped policy
extension does not affect other outbound consumers.

## Documentation

README quick-start instructions mention that RSSHub is bundled but must be
registered once in the existing RSSHub page. The operations guide records the
internal Base URL, lack of host-port exposure, Redis database separation, and the
Chromium image upgrade option.
