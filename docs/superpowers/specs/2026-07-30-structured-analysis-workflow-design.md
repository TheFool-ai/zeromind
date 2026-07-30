# Structured Analysis Workflow Design

## 1. Goal

ZeroMind turns newly discovered RSS references into a queryable information
flow that helps a reader decide what is worth their time. A safe YAML DSL
coordinates:

1. low-cost metadata screening;
2. transient original-content resolution;
3. full-content classification and analysis;
4. deterministic, explainable scoring;
5. a second quality gate;
6. projection into a canonical structured result.

The structured result includes categories, tags, summaries, viewpoints,
dimension scores, a total score, recommendation rationale, and bounded key
quotes. Users can add their own notes to a reference or analysis.

The first release uses automated Agent screening at both stages. An
administrator may correct the final decision, but the correction is appended
as an audited override rather than replacing the Agent result.

Reading-comparison reports are explicitly outside this scope. The user
confirmed that "比较阅读" was not a required capability.

## 2. Product principles

### 2.1 Less content, with reasons

ZeroMind is not trying to maximize the number of items shown. The default
information flow contains qualified items and explains why each item passed.
Rejected items remain queryable for auditing and threshold tuning.

### 2.2 Separate public quality from personal judgment

The analysis is a reproducible quality assessment of a reference revision.
A user note is a personal reading asset. Notes never become Agent output, and
editing a note never changes a quality score.

### 2.3 Keep judgment explainable

An Agent supplies evidence and a score for each configured dimension. A
built-in DSL node calculates the weighted total deterministically. Thresholds,
weights, Agent versions, provider/model identifiers, reasons, and overrides
remain inspectable.

### 2.4 Preserve the reference-first content policy

ZeroMind continues to store references rather than article copies. Original
content is fetched only while a workflow is running and is removed before
workflow state is persisted. The system may persist at most five short key
quotes per analysis, each no longer than 300 Unicode characters, plus at most
200 characters of surrounding context. This bounded derivative output cannot
be used to reconstruct the article.

## 3. Research influence

BestBlogs demonstrates a closely related product pattern:

- inexpensive AI screening before deeper processing;
- full-content structured analysis;
- quality dimensions, summaries, viewpoints, tags, and key quotes;
- a quality pool separated from personal reading assets;
- human correction after automated screening;
- explicit recommendation reasons.

ZeroMind adopts those product mechanisms, not BestBlogs source code or
prompts. Its public repository primarily exposes documentation, Dify
workflows, OpenAPI material, and a separately licensed CLI. ZeroMind's
implementation remains native to its Pi Agent Gateway, Python domain model,
and safe workflow DSL.

## 4. Bounded contexts

### 4.1 Ingestion

The existing `ingestion` context remains authoritative for
`ContentReference` and `ReferenceRevision`. It does not gain analysis fields,
scores, notes, or article bodies.

### 4.2 Workflow

The `workflows` context remains a generic orchestration engine. It gains:

- literal values in safe mappings;
- a `reference` node that reads RSS metadata without fetching the original
  article;
- a deterministic `score` node;
- a terminal `gate` node;
- a named result projection on a workflow definition;
- successful early termination when a gate rejects an item.

It does not persist or query information cards directly.

### 4.3 Analysis

The new `analysis` context owns the canonical structured assessment of one
reference revision. `ContentAnalysis` is its aggregate root.

An `AnalysisProjector` validates a completed workflow result and creates the
aggregate idempotently. `AnalysisDecisionOverride` records manual corrections
without modifying the generated assessment.

### 4.4 Notes

The new `notes` context owns user-authored Markdown notes. `Note` is its
aggregate root and references a `ContentReference`; it may also reference a
specific `ContentAnalysis`.

The initial application has one configured administrator rather than a full
user aggregate. A note stores the authenticated token subject as
`owner_subject`. This preserves ownership semantics and allows a later
multi-user identity implementation without rewriting notes.

### 4.5 Agents

The existing Agent Gateway remains responsible for Agent lookup, Provider
selection, Pi execution, JSON Schema validation, usage metadata, and
timeouts. Screening and deep analysis are ordinary registered Agents with
different prompts, models, and schemas. No analysis-specific model client is
introduced.

## 5. Runtime data flow

```text
reference.discovered / reference.updated / manual
  |
  v
reference metadata node
  |
  v
screening Agent --------------------+
  |                                 |
  v                                 |
initial gate -- reject ------------>+--> completed run
  |
  v
transient content resolver
  |
  v
deep-analysis Agent
  |
  v
deterministic score node
  |
  v
fine gate -- reject ----------------+--> completed run
  |
  v
qualified completed run
  |
  v
canonical AnalysisProjector
  |
  v
ContentAnalysis information card
```

Gate rejection is a successful business result, not a workflow failure. A
provider error, schema mismatch, blocked URL, timeout, invalid mapping, or
projection validation error remains a workflow failure.

A `WorkflowRunService` coordinates execution and projection for both manual
API runs and worker-triggered runs. This avoids placing analysis persistence
inside the generic executor and ensures manual and scheduled runs behave
identically.

## 6. DSL evolution

### 6.1 Safe mappings and literals

Existing strings matching the restricted `$.path` grammar continue to resolve
from the runtime context.

Other scalar YAML values become literals. A string beginning with `$` that is
not a valid restricted path is rejected to catch mapping typos. Dictionaries
and lists may combine paths and literals recursively. There is still no
expression evaluation, interpolation, template execution, arbitrary code, or
dynamic node construction.

Examples:

```yaml
input:
  document: $.steps.resolve
  audience: software-builders
  include_evidence: true
  maximum_quotes: 5
```

### 6.2 `reference` node

The node loads a reference and a selected revision without fetching the
original URL:

```yaml
- id: metadata
  type: reference
  input:
    reference_id: $.trigger.reference_id
    revision: $.trigger.revision
```

Its output contains the reference ID, revision number, subscription ID, URL,
title, RSS summary, author, publication/update times, and observed time.

If `revision` is absent, it reads the current revision. An event-triggered run
must provide a revision so replaying an older event remains deterministic.

### 6.3 `score` node

The score node receives named dimensions. Every dimension contains a
0-to-100 value, a positive weight, and a non-empty Agent-generated reason.

```yaml
- id: quality_score
  type: score
  depends_on: [analyze]
  input:
    dimensions:
      relevance:
        value: $.steps.analyze.scores.relevance.value
        reason: $.steps.analyze.scores.relevance.reason
        weight: 0.20
      information_value:
        value: $.steps.analyze.scores.information_value.value
        reason: $.steps.analyze.scores.information_value.reason
        weight: 0.25
      depth:
        value: $.steps.analyze.scores.depth.value
        reason: $.steps.analyze.scores.depth.reason
        weight: 0.20
      practicality:
        value: $.steps.analyze.scores.practicality.value
        reason: $.steps.analyze.scores.practicality.reason
        weight: 0.15
      novelty:
        value: $.steps.analyze.scores.novelty.value
        reason: $.steps.analyze.scores.novelty.reason
        weight: 0.10
      clarity:
        value: $.steps.analyze.scores.clarity.value
        reason: $.steps.analyze.scores.clarity.reason
        weight: 0.10
```

Weights must sum to `1.0` within a small decimal tolerance. The node calculates
the total as the weighted mean rounded to the nearest integer. It returns the
total and normalized dimension objects. It never calls a model.

The six dimensions above are the default workflow, not hard-coded application
fields. Another activated workflow may use different dimension names and
weights. The canonical projection persists the resulting dimension map.

### 6.4 `gate` node

A gate compares a resolved left operand to a literal or resolved right
operand. Supported operators are:

- numeric `gt`, `gte`, `lt`, and `lte`;
- equality `eq` and `ne`;
- collection membership `in` and `not_in`.

```yaml
- id: fine_gate
  type: gate
  depends_on: [quality_score]
  predicate:
    left: $.steps.quality_score.total
    operator: gte
    right: 70
  reject:
    output:
      schema_version: 1
      status: fine_rejected
      reference: $.steps.metadata
      screening: $.steps.screen
      content: $.steps.analyze
      score: $.steps.quality_score
```

When the predicate is true, execution continues. When false, the workflow
completes immediately with the resolved `reject.output`. Nodes after the gate
are not started and therefore do not create misleading failed or skipped
step records. The gate step records the operands, operator, outcome, and
terminal status.

Gate operands must have compatible types. Type mismatch is a workflow error,
not a rejection.

### 6.5 Projection declaration

A workflow may declare one canonical projection:

```yaml
projection: content_analysis_v1
```

When present, every successful terminal output, including gate rejection,
must validate as `ContentAnalysisDraftV1`. A workflow without a projection
continues to support arbitrary JSON output.

The activation validator checks that the projection name is known. Runtime
projection validation remains authoritative because output paths and Agent
values are dynamic.

### 6.6 Complete example

```yaml
name: valuable-article-analysis
trigger:
  events: [reference.discovered, reference.updated, manual]
projection: content_analysis_v1
nodes:
  - id: metadata
    type: reference
    input:
      reference_id: $.trigger.reference_id
      revision: $.trigger.revision

  - id: screen
    type: agent
    agent_id: 00000000-0000-0000-0000-000000000001
    depends_on: [metadata]
    input:
      metadata: $.steps.metadata
      audience: software-builders

  - id: initial_gate
    type: gate
    depends_on: [screen]
    predicate:
      left: $.steps.screen.score
      operator: gte
      right: 30
    reject:
      output:
        schema_version: 1
        status: initial_rejected
        reference: $.steps.metadata
        screening: $.steps.screen

  - id: resolve
    type: resolve
    depends_on: [initial_gate]
    input:
      reference_id: $.trigger.reference_id

  - id: analyze
    type: agent
    agent_id: 00000000-0000-0000-0000-000000000002
    depends_on: [resolve]
    input:
      metadata: $.steps.metadata
      document: $.steps.resolve
      audience: software-builders
      maximum_quotes: 5

  - id: quality_score
    type: score
    depends_on: [analyze]
    input:
      dimensions:
        relevance:
          value: $.steps.analyze.scores.relevance.value
          reason: $.steps.analyze.scores.relevance.reason
          weight: 0.20
        information_value:
          value: $.steps.analyze.scores.information_value.value
          reason: $.steps.analyze.scores.information_value.reason
          weight: 0.25
        depth:
          value: $.steps.analyze.scores.depth.value
          reason: $.steps.analyze.scores.depth.reason
          weight: 0.20
        practicality:
          value: $.steps.analyze.scores.practicality.value
          reason: $.steps.analyze.scores.practicality.reason
          weight: 0.15
        novelty:
          value: $.steps.analyze.scores.novelty.value
          reason: $.steps.analyze.scores.novelty.reason
          weight: 0.10
        clarity:
          value: $.steps.analyze.scores.clarity.value
          reason: $.steps.analyze.scores.clarity.reason
          weight: 0.10

  - id: fine_gate
    type: gate
    depends_on: [quality_score]
    predicate:
      left: $.steps.quality_score.total
      operator: gte
      right: 70
    reject:
      output:
        schema_version: 1
        status: fine_rejected
        reference: $.steps.metadata
        screening: $.steps.screen
        content: $.steps.analyze
        score: $.steps.quality_score

output:
  schema_version: 1
  status: qualified
  reference: $.steps.metadata
  screening: $.steps.screen
  content: $.steps.analyze
  score: $.steps.quality_score
```

The example Agent IDs are placeholders and cannot be activated until matching
Agents are registered.

## 7. Canonical analysis model

`ContentAnalysis` contains:

- `id`;
- `reference_id` and `reference_revision`;
- `workflow_definition_id`, `workflow_definition_version`, and
  `workflow_run_id`;
- generated `status`: `initial_rejected`, `fine_rejected`, or `qualified`;
- `screening_score`, `screening_reason`, and optional screening summary;
- optional primary category, secondary categories, and tags;
- optional one-sentence summary and full summary;
- zero to ten viewpoints, each containing a statement and explanation;
- zero to five key quotes, each containing bounded text and optional context;
- optional deterministic total score;
- a map of dimension scores, weights, and reasons;
- optional recommendation level and recommendation reason;
- Agent execution provenance copied from workflow steps;
- `created_at`.

The aggregate is immutable after creation. New analysis of a changed reference
or workflow version creates a new aggregate.

The unique projection identity is:

```text
(reference_id, reference_revision,
 workflow_definition_id, workflow_definition_version)
```

Replaying the same run therefore returns the existing analysis. A run ID is
also unique and links directly to its projected result.

### 7.1 Projection validation

`ContentAnalysisDraftV1` enforces:

- the reference in the output matches the workflow trigger;
- the revision exists and belongs to the reference;
- scores are integers from 0 through 100;
- dimension weights are positive and total approximately `1.0`;
- the supplied total matches the deterministic calculation;
- rejected-at-initial results contain no fabricated full analysis;
- fine-rejected and qualified results contain classification, summary,
  viewpoints, dimension score, and recommendation data;
- collection counts and text lengths are bounded;
- no transient-document marker or document body exists anywhere in the
  projected value.

Projection failure fails the run and creates no partial analysis row.

### 7.2 Manual decision overrides

`AnalysisDecisionOverride` contains:

- `id` and `analysis_id`;
- `decision`: `qualified` or `rejected`;
- a required reason from 10 to 2,000 characters;
- `actor_subject`;
- `created_at`.

Overrides are append-only. The effective decision is the newest override, or
the generated status when no override exists. The original score, status,
Agent output, and earlier overrides remain unchanged.

An override changes visibility in the default information flow but does not
change the numeric score. Threshold tuning therefore remains based on
unaltered evidence.

## 8. Notes model

`Note` contains:

- `id`;
- `reference_id`;
- optional `analysis_id`;
- `owner_subject`;
- Markdown `body`, from 1 to 64 KiB;
- `created_at` and `updated_at`.

A note cannot point to an analysis for a different reference. Owners may
create multiple notes for one reference. Deletion is a hard delete in the
initial single-user release; note deletion does not affect references or
analyses.

Notes do not store a resolved article body. A user may quote text in their own
note, but the product does not automatically copy the full article into it.

Bookmarks, highlights, folders, collaborative notes, full-text note search,
and reading history are separate follow-up capabilities.

## 9. API

### 9.1 Analyses

- `GET /api/v1/analyses`
  - filters: effective status, generated status, minimum score, category,
    tag, subscription, reference, and observed date range;
  - defaults to effective `qualified`;
  - sorts by score descending and then publication/observation time
    descending;
  - returns cursor-paginated information cards.
- `GET /api/v1/analyses/{analysis_id}`
  - returns all structured fields, provenance, generated decision, effective
    decision, overrides, and related notes;
- `POST /api/v1/analyses/{analysis_id}/overrides`
  - requires a decision and reason;
  - records the authenticated administrator subject.

The API never returns a resolved article body. It includes the original URL
from the reference so the user can open the source.

### 9.2 Notes

- `GET /api/v1/notes` supports filtering by reference and analysis;
- `POST /api/v1/notes` creates an owned note;
- `PUT /api/v1/notes/{note_id}` replaces its body and optional analysis link;
- `DELETE /api/v1/notes/{note_id}` deletes it.

All operations derive `owner_subject` from the authenticated token. A caller
cannot submit or change it in the request body.

### 9.3 Workflow validation

The existing workflow validation response adds:

- the projection name;
- terminal gate IDs;
- warnings for thresholds outside the usual 0-to-100 score range;
- the topological order.

Unknown projection versions, invalid predicate operators, unsafe mappings,
invalid score weights, or a gate without a rejection output fail validation.

## 10. User interface

The current single application gains an `信息流` entry without reintroducing a
separate user/admin application split.

### 10.1 Information flow

Cards display:

- title, source, publication time, and original link;
- category and tags;
- total score and recommendation level;
- one-sentence summary;
- concise pass rationale;
- whether an administrator overrode the generated decision.

Controls filter by status, minimum score, category, source, and date. A
secondary rejected view supports calibration and audit without flooding the
default feed.

### 10.2 Analysis detail

The detail view shows:

- summary;
- main viewpoints and explanations;
- dimension scores with weights and reasons;
- bounded key quotes;
- screening and fine-gate decisions;
- workflow/Agent provenance;
- override history and an administrator correction form;
- notes for the reference and a Markdown note editor.

The original source opens in a new browser tab. ZeroMind does not render or
cache the full original article in this release.

### 10.3 Workflow editor

The editor example becomes the complete analysis workflow. Validation results
show terminal gates and the selected projection. Existing workflows remain
valid and continue to run without projections.

## 11. Failure and recovery behavior

- Missing reference or revision: fail with `reference_not_found` or
  `reference_revision_not_found`.
- Blocked or invalid original URL: fail the resolve step; do not create an
  analysis.
- Agent timeout/provider failure: use the existing bounded retry policy, then
  fail the run.
- Agent JSON Schema mismatch: fail the Agent step.
- Incompatible gate operands: fail the gate rather than treating it as a
  rejection.
- Invalid score values or weights: fail the score step.
- Canonical projection mismatch: fail with
  `analysis_projection_invalid`; persist no partial result.
- Duplicate projection: return the existing aggregate.
- Invalid override: reject without changing effective status.
- Note ownership mismatch: return not found rather than exposing another
  owner's note.

Early gate rejection completes normally, projects a rejected analysis, and
does not invoke later Agents. This is the main cost-control mechanism.

## 12. Security and privacy

- DSL values remain data; there is no executable expression language.
- Original bodies continue to be removed from persisted workflow inputs,
  outputs, step records, logs, and events.
- Quote and summary bounds prevent an Agent from using the projection as an
  article-copy channel.
- Agent output is validated first against its registered JSON Schema and then
  against the canonical projection schema.
- Provider credentials stay in environment variables referenced by Provider
  profiles.
- Override and note ownership derive from verified authentication, never
  client-submitted identity fields.
- API errors and logs include identifiers, not original article text or note
  bodies.

## 13. Testing

### 13.1 DSL and executor

- parse literals while preserving restricted path behavior;
- reject malformed `$` paths and executable-looking mappings;
- validate `reference`, `score`, and `gate` node contracts;
- calculate weighted scores deterministically;
- cover every predicate operator and type mismatch;
- prove false gates terminate successfully without invoking downstream
  handlers;
- preserve idempotent workflow runs;
- prove transient bodies are absent from persistence on success and failure;
- prove existing workflow DSL remains backward compatible.

### 13.2 Analysis domain and persistence

- validate each terminal canonical result shape;
- reject inconsistent reference/revision or calculated totals;
- enforce quote, viewpoint, tag, summary, and reason bounds;
- project the same result idempotently;
- create distinct results for a new reference or workflow version;
- append overrides and calculate the effective decision;
- cover list filters and stable cursor ordering;
- run repository tests against PostgreSQL-compatible SQLAlchemy models.

### 13.3 Notes

- create, update, list, and delete owned notes;
- reject empty, oversized, cross-reference, and cross-owner operations;
- prove note operations do not modify analyses.

### 13.4 End to end

One fixture flow:

1. ingests three reference fixtures;
2. rejects one at metadata screening;
3. resolves and fine-rejects one;
4. resolves and qualifies one;
5. verifies only two full-content Agent calls occurred;
6. verifies all three structured results and no article body were persisted;
7. manually overrides the fine-rejected result;
8. verifies it enters the default information flow;
9. creates and edits a note;
10. verifies API and frontend rendering.

The fixture uses deterministic fake Pi results and a local public-address HTTP
server. Public RSSHub and model providers are not required for automated
tests.

## 14. Delivery sequence and commit boundaries

Implementation is split into reviewable commits:

1. `docs: design structured analysis workflows`
2. `feat: add safe workflow scoring and gates`
3. `feat: persist canonical content analyses`
4. `feat: project workflow results into analyses`
5. `feat: expose analysis feed and decision overrides`
6. `feat: add owned reading notes`
7. `feat: add structured information flow UI`
8. `docs: document and verify the analysis workflow`

Each commit includes its related tests. Existing unrelated migration-startup
changes remain outside these commits.

## 15. Research sources

- [BestBlogs repository](https://github.com/ginobefun/BestBlogs) exposes its
  product documentation, Dify workflow material, OpenAPI, CLI, and Agent
  skills.
- [BestBlogs working
  model](https://www.bestblogs.dev/docs/how-it-works) describes metadata
  collection, AI screening, structured quality assessment, expert correction,
  and explainable recommendation.
- [BestBlogs article filter
  flow](https://github.com/ginobefun/BestBlogs/blob/main/flows/Dify/ArticleFIlterFlow.md)
  documents its inexpensive first-stage result and threshold.
- [BestBlogs article analysis
  flow](https://github.com/ginobefun/BestBlogs/blob/main/flows/Dify/ArticleAnalysisFlow.md)
  documents full-content analysis, classification, scoring, reflection, and
  structured output.
- [BestBlogs Capture
  API](https://github.com/ginobefun/BestBlogs/blob/main/openapi/05-capture.md)
  separates personal bookmarks and notes from generated content analysis.

## 16. Deferred work

- reading-comparison reports;
- full multi-user registration and authorization;
- personalized ranking learned from behavior;
- bookmarks, highlights, folders, and reading history;
- human review queues beyond direct administrator overrides;
- prompt calibration from override history;
- long-document map/reduce nodes;
- translation and cross-language result variants;
- semantic search or embeddings;
- duplicate-story clustering and topic synthesis.

These can build on the canonical analysis and note identities without changing
the first release's reference-first storage policy.
