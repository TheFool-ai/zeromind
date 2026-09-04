# RSSHub Subscription Address Design

## Goal

ZeroMind accepts RSSHub route locators such as
`rsshub://twitter/media/vista8` alongside directly fetchable HTTP and HTTPS
feed URLs. RSSHub locators remain independent of a particular RSSHub instance
and are resolved only when a feed is fetched.

## Scope

- Accept, normalize, persist, display, and deduplicate `rsshub://` locators.
- Resolve RSSHub locators to an administrator-configured HTTP or HTTPS
  instance at fetch time.
- Register multiple RSSHub instances and select one active default instance.
- Store an optional instance access key encrypted at rest without returning it
  from the API.
- Support RSSHub locators in manual subscription creation and as a ZeroMind
  extension during OPML import.
- Preserve the existing behavior for HTTP and HTTPS feeds.
- Show actionable validation and fetch errors.

User accounts, per-user subscriptions, and the user/admin application split
are separate follow-up work. The existing single control plane owns RSSHub
instance management for this phase.

## Ecosystem Meaning

`rsshub://` is an RSSHub ecosystem route locator, not a directly fetchable RSS
or Atom URL and not an IANA-registered network protocol.

Folo stores locators such as `rsshub://twitter/user/DIYgod` and resolves them
through the RSSHub instance selected by the user. RSSHub Radar takes the other
common approach: it combines a discovered route with its configured RSSHub
HTTP domain before handing the resulting URL to an external reader.

ZeroMind follows the Folo model internally because it controls feed fetching.
When interoperating with a generic reader or another system, ZeroMind emits
the resolved HTTP or HTTPS URL instead.

## Address Semantics

The locator grammar is:

```text
rsshub://<route-segment>/<remaining-route>[?<query>]
```

For example:

```text
rsshub://twitter/user/vista8
```

resolves to:

```text
https://rsshub.app/twitter/user/vista8
```

when the configured instance is `https://rsshub.app`.

The related media-only route is:

```text
rsshub://twitter/media/vista8
https://rsshub.app/twitter/media/vista8
```

The `/twitter/user` route returns the user's timeline according to its route
parameters. The `/twitter/media` route filters for posts containing media.

The authority portion is the first RSSHub route segment, not a network host.
Fragments, credentials, ports, empty routes, and path traversal segments are
invalid. Query parameters are preserved because RSSHub uses them for route and
output options.

Normalization lowercases only the `rsshub` scheme. Everything after
`rsshub://` is treated as an opaque, percent-encoded RSSHub route. The
implementation must not decode path segments, change case, remove trailing
slashes, collapse internal slashes, or reorder parameters: RSSHub routes use
encoded delimiters and sometimes place query-string-shaped route parameters
inside the path.

## Persistence and Deduplication

The existing `feed_url` field stores the normalized locator. No schema
migration is required.

- Direct feeds store their normalized HTTP or HTTPS URL.
- RSSHub feeds store their normalized `rsshub://` locator.
- Duplicate detection operates on the persisted normalized value.

The resolved HTTP URL is not persisted. Changing the configured RSSHub
instance therefore changes future fetches without rewriting subscriptions.

## Runtime Resolution

A dedicated RSSHub resolver receives a normalized subscription locator and
the configured instance base URL.

- HTTP and HTTPS locators pass through unchanged.
- RSSHub locators become `<instance-base>/<route-and-query>`.
- The instance base must itself be a valid HTTP or HTTPS URL with a host.
- The resolved URL is passed through the same outbound network safety policy
  used for other remote requests.

The first implementation persists an RSSHub instance registry. Each instance
has a unique name, an HTTP or HTTPS base URL, an optional encrypted access key,
an enabled flag, and an active-default flag. Exactly zero or one instance is
active. Creating the first enabled instance makes it active; activating
another instance atomically replaces the previous active instance.

ZeroMind does not create a hidden public default. A direct HTTP or HTTPS feed
continues to work without an RSSHub instance, while fetching an `rsshub://`
subscription without an active instance fails with an actionable
`rsshub_instance_not_configured` error.

Instance selection is global in this phase. Subscriptions do not bind to an
instance, and automatic failover is deferred because different RSSHub
instances can expose different route versions, caches, and credentials.

An instance may be protected by RSSHub access control. ZeroMind accepts an
optional access key when an instance is created or updated, encrypts it before
persistence using the application credential secret, and never returns its
value through the API. The response exposes only `has_access_key`.

The active instance configures one of two authentication modes:

- appends `key=<access-key>` to the resolved URL; or
- appends `code=md5(<route><access-key>)`.

The default mode is `key`. Updating an instance without an `access_key` field
keeps the current secret; explicitly clearing it removes the secret.

The access key is instance authentication. It is distinct from route-provider
credentials such as `TWITTER_AUTH_TOKEN`, which remain configured on the
RSSHub server.

## Instance Management API

The control-plane API provides:

- `GET /api/v1/rsshub/instances` to list sanitized instances;
- `POST /api/v1/rsshub/instances` to register an instance;
- `PUT /api/v1/rsshub/instances/{id}` to update its metadata or access key;
- `POST /api/v1/rsshub/instances/{id}/activate` to select the active instance;
- `DELETE /api/v1/rsshub/instances/{id}` to remove a non-active instance.

Deleting the active instance is rejected until another instance is activated.
This prevents a silent loss of RSSHub fetching. Instance base URLs are
normalized and deduplicated independently of subscription locators.

## Fetch and Error Behavior

Subscription creation validates locator syntax but does not require the
remote feed to be available. Scheduled fetching resolves the locator and
records the same retry state used by direct feeds.

Errors distinguish:

- invalid RSSHub locator;
- no active RSSHub instance;
- invalid, disabled, or blocked RSSHub instance;
- instance unreachable or timed out;
- RSSHub route unavailable or missing provider credentials;
- response is not a valid feed.

RSSHub route failures do not disable a subscription automatically. Existing
retry and scheduling behavior remains authoritative.

## OPML

The OPML 2.0 specification defines `xmlUrl` as the HTTP address of a feed.
ZeroMind preview and import may nevertheless accept `rsshub://` in `xmlUrl` as
an application extension. Invalid entries remain isolated in the preview
result and do not abort the batch.

Export is outside the current scope. If added later, its default portable mode
must put the resolved HTTP URL in `xmlUrl`. A ZeroMind-specific extension may
add the logical RSSHub locator in a namespaced attribute, but must not replace
the portable `xmlUrl` with it.

## Frontend

The subscription form uses a text input with explicit validation rather than
the browser's HTTP-only URL input behavior. Its help text and placeholder show
both accepted forms:

```text
https://example.com/feed.xml
rsshub://twitter/media/vista8
```

Subscription rows display the stored locator. Direct feeds remain clickable.
RSSHub rows display the locator as code instead of exposing a resolved URL:
the resolved URL may contain an instance access key and is therefore a
server-side fetch detail.

A dedicated RSSHub instances page lists the registered base URLs, enabled and
active state, and whether an access key exists. It supports adding instances,
activating one, editing the authentication mode or secret, and deleting only
inactive instances. Secrets are write-only fields.

## Security

- Only `http`, `https`, and `rsshub` subscription schemes are accepted.
- RSSHub locators cannot select an arbitrary host; only the configured
  instance determines the network destination.
- Instance configuration is validated independently.
- Instance access keys are encrypted before database persistence, never stored
  in subscription records, and never returned to the UI.
- `ZEROMIND_CREDENTIAL_SECRET` is required to be a high-entropy secret in
  production and must remain stable across deployments so stored credentials
  remain decryptable.
- Resolved requests retain redirect, DNS/IP, response-size, and timeout
  controls.
- Provider credentials remain in RSSHub configuration and are never stored in
  a subscription locator.

## Testing

Backend tests cover normalization, invalid syntax, query preservation,
deduplication, OPML preview/import, instance lifecycle and active-selection
invariants, secret encryption and sanitization, instance resolution,
authentication query construction, and feed-client fetching through the
resolved URL. Frontend tests cover manual entry and display of both address
forms plus instance registration and activation.

An integration fixture uses a local HTTP feed server rather than the public
RSSHub service. Public RSSHub and provider APIs are external dependencies and
are verified through an optional operational smoke test.

## Research Sources

- [RSSHub Getting Started](https://docs.rsshub.app/guide/) describes combining
  an instance domain with a route before adding it to a general RSS reader.
- [RSSHub Public Instances](https://docs.rsshub.app/guide/instances) explains
  that Folo-managed instances are not general-purpose endpoints for external
  readers.
- [Folo onboarding feeds](https://github.com/RSSNext/Folo/blob/dev/apps/mobile/src/modules/onboarding/feeds.json)
  use `rsshub://` locators as first-class feed identifiers.
- [Folo RSSHub instance management](https://github.com/RSSNext/Folo/blob/dev/apps/desktop/layer/renderer/src/pages/%28main%29/%28layer%29/%28subview%29/rsshub/index.tsx)
  lets a user select the instance used for those locators.
- [RSSHub Radar configuration](https://github.com/DIYgod/RSSHub-Radar/blob/dev/src/lib/config.ts)
  and [subscription URL construction](https://github.com/DIYgod/RSSHub-Radar/blob/dev/src/popup/RSSItem.tsx)
  show the alternative of resolving a route to HTTP before handing it to a
  reader.
- [IANA URI Schemes](https://www.iana.org/assignments/uri-schemes/uri-schemes.xhtml)
  has no registered `rsshub` scheme.
- [OPML 2.0](https://2005.opml.org/spec2.html) defines a subscription
  `xmlUrl` as the HTTP address of the feed.

## Operational Finding

On 2026-07-29, the public `https://rsshub.app` instance was unreachable from
the local development network. The current official RSSHub Docker image
recognized `/twitter/media/vista8` but returned HTTP 503 with
`Twitter API is not configured`. Its built-in `/test/1` route returned a valid
feed with five entries and parsed successfully.

On 2026-07-30, the same checks against `/twitter/user/vista8` produced the same
result: the public instance timed out from the local network, while the current
official Docker image recognized the route but returned HTTP 503 because
Twitter was not configured. Adding the `forceWebApi=1` route parameter did not
remove the credential requirement.

These Twitter routes therefore require an RSSHub instance configured with
Twitter credentials. Current RSSHub documentation recommends
`TWITTER_AUTH_TOKEN`, containing one or more comma-separated Twitter
`auth_token` cookie values. A `TWITTER_CONSUMER_KEY` and
`TWITTER_CONSUMER_SECRET` pair can instead use Twitter's pay-per-use developer
API. These secrets belong to the RSSHub deployment, not ZeroMind subscription
data.

The configurable instance is required for reliable deployment; the public
default is a convenience, not an availability guarantee. Folo's built-in and
community-shared instances are resolved by Folo's backend and are not
available as general-purpose HTTP instances for external readers such as
ZeroMind.
