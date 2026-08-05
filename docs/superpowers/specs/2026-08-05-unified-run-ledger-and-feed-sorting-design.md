# Unified Run Ledger and Information Feed Sorting

## Context

ZeroMind currently exposes the same content lifecycle through two separate operational pages. “内容引用” lists RSS references and their analysis lifecycle, while “运行记录” lists workflow runs and Agent sessions without enough business context. The reference detail page can render transient original content, but that reader is not discoverable from the run ledger. The information feed is already a single-column reading surface, but its API always orders by score and gives users no explicit sorting choice.

This change makes the run ledger the single operational view of a reference from discovery through analysis, keeps the information feed focused on consuming structured results, and makes feed ordering explicit.

## Goals

- Replace the separate content-reference list and workflow-run list with one single-column run ledger.
- Keep every discovered reference visible, including references that are still waiting for a workflow run.
- Preserve workflow runs that are not associated with a current content reference.
- Let users preview transiently resolved original content without leaving the run ledger.
- Expose analysis output and full Agent execution trace next to the same reference.
- Preserve retry and failure-diagnosis workflows.
- Add stable server-side “评分优先” and “时间优先” sorting to the information feed.
- Preserve old reference URLs through redirects.

## Non-goals

- Persisting original article bodies.
- Changing the reference lifecycle state machine.
- Changing workflow DSL semantics or Agent configuration.
- Adding a new event log table.
- Redesigning the analysis detail page or changing manual decision overrides.
- Providing arbitrary user-defined sort expressions.

## Product Structure

### Navigation

The sidebar removes the standalone “内容引用” entry. “运行记录” remains and becomes the operational home for both references and executions. Navigation numbering is compacted so later entries do not retain an unexplained gap.

Compatibility behavior:

- `/references` redirects to `/runs`.
- `/references/:referenceId` redirects to `/runs?reference=:referenceId`.
- A `reference` query parameter causes the matching row to be brought into view and expanded after data loads.
- `/analyses` and `/analyses/:analysisId` remain unchanged except for the new list sort control.

### Unified Run Ledger

The run ledger is a single-column chronological list. Its primary unit is a content reference, not a bare workflow UUID. Each collapsed row shows:

- lifecycle status and current processing stage;
- source, author, publication time, and title;
- RSS or generated one-sentence summary;
- current score and generated decision when available;
- workflow run short ID, start time, completion time, and duration when available;
- a concise error plus a retry action for failed references.

Rows are ordered by the reference's latest lifecycle update, newest first. A reference with no `analysis_workflow_run_id` remains visible and reads “等待创建运行”. A workflow run not linked by any current reference is appended as an “未关联引用” operational row so the existing run ledger does not lose manual or historical executions.

Only one row is expanded at a time. Expansion is addressable through the `reference` query parameter and contains three tabs:

1. **原文预览** — transient same-origin text reader.
2. **分析结果** — current structured analysis or a lifecycle-aware empty state.
3. **Agent 轨迹** — workflow nodes, retries, Agent sessions, errors, usage, sanitized input, and output.

Desktop and mobile use the same stacked single-column model. Tabs scroll horizontally if necessary on narrow screens. Expanded content never introduces a second permanent master/detail column.

## Original Content Preview

The ledger reuses `GET /api/v1/references/{reference_id}/content`. The request is lazy: it starts only after a row is expanded and the user opens “原文预览”. This avoids resolving every article while loading the ledger.

The reader displays the resolved title, author, language, and extracted plain text. It also provides an external link to the final source URL. The body remains transient and is not written to the database, workflow output, or Agent session records.

If extraction is unavailable or fails, the tab displays RSS metadata as a fallback together with “重新提取” and “新窗口打开原文”. A missing source URL produces a clear non-retryable empty state. HTML is never injected into the page.

The existing reference-detail reader markup is extracted into focused reusable components instead of copying fetch and fallback behavior into the ledger.

## Analysis and Execution Details

### Analysis tab

The tab uses the analysis already attached to the reference read model for its summary card. When the user expands the tab, full detail is loaded only if a completed/rejected analysis exists. It displays decision, one-sentence summary, summary, categories, tags, score dimensions, recommendation, viewpoints, and key quotes. Pending and processing references show their current lifecycle stage; failures show the recorded error and retry action.

### Agent trace tab

Workflow run steps are already included in `GET /api/v1/workflow-runs`. Agent sessions remain lazy-loaded from `GET /api/v1/agent-sessions?workflow_run_id=...` when the trace tab is opened. Sessions are grouped under their `step_run_id` and ordered by attempt. Each entry shows Agent identity/version, provider/model, status, timing, usage, error, sanitized input, and output.

References without a run show “工作流尚未创建”. Runs without Agent sessions show the node timeline and a separate “尚无 Agent 会话” state rather than appearing broken.

The first implementation joins the existing reference and workflow-run responses in the frontend. This preserves all references and all unlinked runs without introducing a duplicate persistence model. If dataset size later requires server pagination, the same view model can move behind a dedicated endpoint without changing the page contract.

## Information Feed Sorting

The information feed adds a two-option segmented control:

- `score` / “评分优先” (default): total score descending, then content time descending, then analysis ID descending.
- `time` / “时间优先”: content time descending, then total score descending, then analysis ID descending.

Content time remains `published_at` when present and otherwise `observed_at`. Null scores sort as `-1`, so they remain deterministic and last within an equal time grouping where applicable.

`GET /api/v1/analyses` accepts `sort=score|time`, defaulting to `score` for compatibility. The repository applies the selected ordering in both SQL and in-memory implementations. Cursor predicates use the exact tuple for the selected mode:

- score: `(score, content_time, id)`;
- time: `(content_time, score, id)`.

The cursor payload includes a version and sort mode. A cursor created for one mode is rejected with `422 invalid_cursor` when supplied with another mode. Switching the UI control creates a new query key, discards prior pages, and loads from the first page. Sorting is never performed only on the currently loaded client page.

## Data Flow

### Ledger load

1. Fetch `/references` and `/workflow-runs` in parallel.
2. Index runs by ID.
3. Build one ledger item for every reference by joining `analysis_workflow_run_id`.
4. Add remaining unlinked runs as operational-only items.
5. Sort the combined list by lifecycle/run activity time descending.
6. Poll while any visible reference or run is non-terminal; otherwise stop automatic polling.

### Expanded row

1. The row owns the selected tab and writes its reference ID to the URL.
2. “原文预览” lazily fetches transient content.
3. “分析结果” uses the attached preview and fetches full analysis detail only when required.
4. “Agent 轨迹” lazily fetches sessions for the linked run.
5. Collapsing the row removes the `reference` query parameter but retains React Query cache data.

### Retry

Retry continues to call `POST /references/{id}/reanalyze`. Success invalidates references, workflow runs, analysis data, and the selected row's sessions. The row returns to `pending` immediately after the accepted response and remains visible throughout the next run.

## Component Boundaries

- `RunsPage`: orchestration, filters, polling, URL-selected row, and merge of references/runs.
- `RunLedgerRow`: collapsed summary, lifecycle state, retry, expansion shell.
- `ReferenceOriginalReader`: transient content query, reader, fallback, and external-link behavior.
- `ReferenceAnalysisPanel`: lifecycle-aware structured analysis display.
- `AgentTracePanel`: workflow node/session grouping and execution diagnostics.
- analysis repository/service/API: sort mode, tuple ordering, cursor validation, and pagination.
- `AnalysesPage`: sort selector and query parameter wiring only.

The components depend on typed API responses, not on each other's internal state. Reader and analysis panels can continue to serve any retained deep-link surface during migration.

## Error Handling

- Either top-level ledger request can fail independently. References remain visible if runs fail, and unlinked runs remain visible if references fail; the unavailable context is identified inline.
- Original extraction errors never hide RSS metadata or the external source link.
- Agent session errors leave the workflow node timeline visible and provide a retry control.
- Invalid or missing `reference` query parameters do not crash the page; the page shows a small “未找到对应引用” notice and the rest of the ledger.
- A reanalysis conflict reports that processing is already active and refreshes the row.
- The feed preserves current results while a sort switch is fetching and exposes an accessible loading state.

## Accessibility and Responsive Behavior

- Rows use buttons for expansion and preserve visible keyboard focus.
- Expansion state is communicated with `aria-expanded` and a controlled panel ID.
- Tabs use `tablist`, `tab`, and `tabpanel` roles with selected state.
- Status is conveyed by text as well as color.
- Long titles, URLs, provider names, JSON, and errors wrap without horizontal page overflow.
- On small screens, score and metadata stack under the title; controls remain at least 44 CSS pixels high.

## Testing and Verification

Backend tests cover:

- score and time ordering in both repository implementations;
- deterministic tie-breaking and null-score behavior;
- pagination across both modes without duplicates or omissions;
- cursor mode mismatch and malformed cursor rejection;
- default score ordering for existing API clients.

Frontend tests cover:

- references with and without linked runs appear in the ledger;
- unlinked workflow runs remain visible;
- old reference routes redirect and auto-expand the target;
- only one row expands at a time;
- original content loads lazily and fallback/retry behavior works;
- analysis and Agent trace tabs render their lifecycle-specific states;
- failed references can be requeued;
- switching feed sorting changes the API query and resets pagination.

Final verification includes backend unit/integration tests, Ruff, mypy, frontend tests, TypeScript checking, production build, and browser inspection at desktop and mobile widths. Browser inspection must prove single-column layout, no horizontal overflow, direct original preview, visible execution trace, old-route compatibility, and both feed ordering modes.

## Migration and Compatibility

No database migration is required. Existing reference, workflow run, step, Agent session, and content-analysis records remain authoritative. Existing API clients keep score-first ordering because `sort` defaults to `score`. Old reference URLs redirect instead of returning a missing page.

