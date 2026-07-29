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
- Support RSSHub locators in manual subscription creation and OPML import.
- Preserve the existing behavior for HTTP and HTTPS feeds.
- Show actionable validation and fetch errors.

User accounts, per-user subscriptions, the user/admin application split, and
an administration UI for global settings are separate follow-up work.

## Address Semantics

The locator grammar is:

```text
rsshub://<route-segment>/<remaining-route>[?<query>]
```

For example:

```text
rsshub://twitter/media/vista8
```

resolves to:

```text
https://rsshub.app/twitter/media/vista8
```

when the configured instance is `https://rsshub.app`.

The authority portion is the first RSSHub route segment, not a network host.
Fragments, credentials, ports, empty routes, and path traversal segments are
invalid. Query parameters are preserved because RSSHub uses them for route and
output options.

Normalization lowercases the `rsshub` scheme, removes fragments, normalizes
empty path separators, and applies deterministic query ordering consistent
with direct feed URL normalization. Route segment case is preserved.

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

The first implementation exposes the instance as
`ZEROMIND_RSSHUB_BASE_URL`, defaulting to `https://rsshub.app`. A later
administration-settings feature can own this value without changing the
subscription model or resolver contract.

## Fetch and Error Behavior

Subscription creation validates locator syntax but does not require the
remote feed to be available. Scheduled fetching resolves the locator and
records the same retry state used by direct feeds.

Errors distinguish:

- invalid RSSHub locator;
- invalid or blocked RSSHub instance;
- instance unreachable or timed out;
- RSSHub route unavailable or missing provider credentials;
- response is not a valid feed.

RSSHub route failures do not disable a subscription automatically. Existing
retry and scheduling behavior remains authoritative.

## OPML

OPML preview and import accept `rsshub://` in `xmlUrl`. Invalid entries remain
isolated in the preview result and do not abort the batch.

Export is outside the current scope. If added later, it should preserve the
stored locator and optionally offer resolved portable HTTP URLs.

## Frontend

The subscription form uses a text input with explicit validation rather than
the browser's HTTP-only URL input behavior. Its help text and placeholder show
both accepted forms:

```text
https://example.com/feed.xml
rsshub://twitter/media/vista8
```

Subscription rows display the stored locator. Direct feeds remain clickable.
RSSHub rows expose the resolved URL as the external-open target while keeping
the locator visible.

## Security

- Only `http`, `https`, and `rsshub` subscription schemes are accepted.
- RSSHub locators cannot select an arbitrary host; only the configured
  instance determines the network destination.
- Instance configuration is validated independently.
- Resolved requests retain redirect, DNS/IP, response-size, and timeout
  controls.
- Provider credentials remain in RSSHub configuration and are never stored in
  a subscription locator.

## Testing

Backend tests cover normalization, invalid syntax, query preservation,
deduplication, OPML preview/import, instance resolution, and feed-client
fetching through the resolved URL. Frontend tests cover manual entry and
display of both address forms.

An integration fixture uses a local HTTP feed server rather than the public
RSSHub service. Public RSSHub and provider APIs are external dependencies and
are verified through an optional operational smoke test.

## Operational Finding

On 2026-07-29, the public `https://rsshub.app` instance was unreachable from
the local development network. The current official RSSHub Docker image
recognized `/twitter/media/vista8` but returned HTTP 503 with
`Twitter API is not configured`. Its built-in `/test/1` route returned a valid
feed with five entries and parsed successfully.

The Twitter media route therefore requires an RSSHub instance configured with
Twitter credentials, such as `TWITTER_AUTH_TOKEN` or a Twitter consumer
key/secret pair. The configurable instance is required for reliable
deployment; the public default is a convenience, not an availability
guarantee.
