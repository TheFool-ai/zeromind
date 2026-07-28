# ZeroMind Information Hub Design

## 1. Goal and constraints

ZeroMind is a single-organization information collection platform. Its MVP must:

- manage RSS/Atom subscriptions through individual creation and OPML 1.0/2.0 imports;
- poll enabled feeds every 30 minutes with a 10-minute overlap buffer;
- keep references and RSS metadata revisions, never fetched article bodies or snapshots;
- resolve an article from its reference only while a workflow is running;
- register, discover, enable, disable, and execute logical agents backed by Pi;
- let each agent select a named provider profile and model;
- execute safe YAML DAG workflows on new references, optional reference updates, or manual/API requests;
- persist structured analysis results and deliver them through signed webhooks;
- provide a basic authenticated administration UI.

The target scale is at most 1,000 feeds and 10,000 discovered items per half-hour. The deployment target is Docker Compose on a single host or small cluster. The initial security model is one administrator account.

## 2. Architecture

The business platform is a Python 3.12+ modular monolith guided by DDD. One codebase is deployed as API, scheduler, and worker processes. PostgreSQL is the source of truth; Redis carries Celery jobs, rate limits, locks, and disposable cache entries. A transactional outbox makes Redis delivery recoverable from PostgreSQL.

Pi runs in a separate Node.js runtime. A small runner embeds `@earendil-works/pi-coding-agent`, disables Pi's filesystem and shell tools, and exposes a strict JSONL request/event protocol over standard input and output. Python owns lifecycle, timeout, cancellation, provider-profile resolution, output validation, and persistence.

The React/TypeScript administration UI is a separate build served by Nginx in production. It talks only to the Python REST API.

## 3. Bounded contexts

### Identity

Authenticates the configured administrator and issues a short-lived signed access token. No roles, organizations, invitations, or public registration exist in the MVP.

### Subscriptions

`Subscription` is the aggregate root. It owns the normalized feed URL, display metadata, enabled/health state, poll schedule, conditional-request validators, retry state, and last successful check. OPML import is an application service: it parses untrusted XML without entity expansion, previews entries, then idempotently creates subscriptions by normalized feed URL.

### Ingestion

`FeedFetch` records each polling attempt. The scheduler claims due subscriptions and enqueues one job per feed. The worker uses ETag and Last-Modified when present, parses the returned Feed, and considers the previous success time minus ten minutes when classifying entries. A never-before-seen stable identity is not discarded solely because its timestamp is old.

Feed entry identity is selected in this order:

1. `(subscription_id, guid)`;
2. `(subscription_id, normalized canonical URL)`;
3. `(subscription_id, SHA-256(title, published_at, original link))`.

`ContentReference` represents the stable external item. `ReferenceRevision` stores only RSS metadata and a deterministic metadata fingerprint. A changed fingerprint creates a revision and `reference.updated`; the first sighting creates `reference.discovered`. Workflows listen only for discoveries unless `on_item_updated` is explicitly enabled.

### Content resolution

The resolver accepts a `ContentReference`, validates its public HTTP(S) destination, performs bounded redirects and DNS/IP checks, downloads a bounded HTML response, and extracts a normalized transient document. Localhost, private, link-local, loopback, multicast, reserved, and cloud metadata destinations are rejected before connecting and after every redirect.

The transient document contains title, byline, language, canonical URL, plain text, and selected metadata. It is passed directly to workflow execution and is never committed to the database, logs, queue payloads, or object storage.

### Agent management

`ProviderProfile` stores a provider identifier, model identifier, thinking level, safe generation parameters, and an environment-variable name containing the credential. It never stores the credential value.

`AgentDefinition` stores a unique name, description, capability tags, system prompt, provider-profile reference, version, enabled state, input JSON Schema, and output JSON Schema. Discovery filters enabled agents by exact capability tags. Updating execution-affecting fields increments the definition version.

The Agent Gateway resolves the agent and provider profile, passes the transient document and workflow input to the Pi runner, streams lifecycle events, validates the final JSON result against the agent output schema, and records token/cost metadata when supplied. The runner has no builtin Pi tools in the MVP.

### Workflow

`WorkflowDefinition` is versioned immutable YAML after activation. A workflow contains:

- `trigger`: `reference.discovered`, optional `reference.updated`, or `manual`;
- `nodes`: unique IDs using `resolve`, `agent`, `condition`, `parallel`, and `webhook`;
- `depends_on`: explicit DAG dependencies;
- `input` mappings using restricted JSON-path-like references such as `$.trigger.reference_id`;
- per-node timeout and retry policy;
- a workflow-level output mapping.

The validator rejects cycles, unknown node types, missing dependencies, unknown agents, unbounded retry counts, invalid mappings, and unreachable nodes. There are no loops, arbitrary code expressions, shell commands, dynamic imports, or user-defined functions.

`WorkflowRun` and `StepRun` persist definition/agent versions, state, timing, retry count, error codes, structured node outputs, and final structured analysis. They do not persist the resolved article text. A run has one deterministic idempotency key per trigger, reference revision, and workflow version.

### Delivery

`WebhookEndpoint` holds its URL, enabled state, event filters, and an encrypted-at-rest signing secret. `DeliveryAttempt` records status, response code, retry time, and a body digest. Deliveries use an HMAC-SHA256 timestamped signature and bounded exponential retries. Private and local webhook destinations are rejected with the same network policy as content resolution.

## 4. Runtime flow

1. Celery Beat invokes the due-subscription scan every 30 minutes.
2. The scheduler atomically claims rows using a lease and creates feed-fetch jobs.
3. A worker performs a conditional request and transactionally writes fetch state, references/revisions, and outbox events.
4. The outbox dispatcher publishes events to Celery; a repair scan re-publishes stale undispatched records.
5. Matching active workflows create idempotent runs.
6. A workflow resolves the reference just in time, invokes configured agents through Pi, discards the transient document, and persists structured outputs.
7. Completed or failed runs are visible in the UI; successful matching results are delivered through signed webhooks.

## 5. API and administration UI

REST endpoints are versioned under `/api/v1`. They cover authentication, subscriptions and OPML preview/import, references and revisions, provider profiles, agents and discovery, workflow validation/activation/runs, webhook endpoints, health, and manual retry actions. List endpoints use cursor pagination.

The administration UI provides:

- sign-in;
- subscription list, health, individual creation, and OPML import preview;
- reference list and revision metadata;
- provider profile and agent management plus an agent test action;
- YAML workflow editor with validation feedback, activation, and manual run;
- workflow-run timeline, structured result, and retry action;
- webhook management and delivery status.

## 6. Failure behavior and observability

External calls have explicit connect/read/overall timeouts, bounded response sizes, domain-aware concurrency, and exponential backoff with jitter. Error codes distinguish invalid input, blocked network targets, upstream HTTP failure, parse failure, Pi unavailable, provider failure, schema mismatch, and webhook failure.

Logs are structured JSON with correlation, job, reference, workflow-run, and agent IDs. Metrics cover feed freshness/success, discovered and updated references, queue depth/latency, workflow duration/failures, provider tokens/cost, parser failures, outbox lag, and webhook outcomes. Health endpoints distinguish liveness from PostgreSQL/Redis/Pi readiness.

## 7. Acceptance criteria

- Re-importing the same OPML creates no duplicate subscriptions and reports per-entry outcomes.
- Reprocessing the same feed payload creates no duplicate references, revisions, events, workflow runs, or deliveries.
- A metadata change creates exactly one new revision; it triggers analysis only for workflows that opt into updates.
- A `304` response updates check state without parsing entries.
- Private-network and redirect-to-private URLs are rejected.
- No fetched article body appears in database rows, queue payloads, or application logs.
- Agents are discoverable by capabilities and execute with their configured provider/model through Pi.
- Invalid or cyclic YAML workflows cannot be activated.
- Worker termination and Redis task loss are recoverable from PostgreSQL state.
- The API, worker, scheduler, Pi runner, database, Redis, and UI start from Docker Compose and pass automated unit, integration, contract, and end-to-end smoke tests.

