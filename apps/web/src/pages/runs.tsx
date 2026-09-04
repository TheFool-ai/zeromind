import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query";
import {useEffect, useMemo, useState, type MouseEvent} from "react";
import {useSearchParams} from "react-router-dom";

import {api, type Reference, type WorkflowRun} from "../api/client";
import {
  Empty,
  ErrorNotice,
  formatTime,
  PageHeader,
  ReferenceStatus,
  referenceStatusGroup,
  Status,
  type ReferenceStatusGroup
} from "../components";
import {plainText} from "../text";
import {
  AgentTracePanel,
  ReferenceAnalysisPanel,
  ReferenceOriginalReader
} from "./reference-panels";

const filters: Array<[ReferenceStatusGroup, string]> = [
  ["all", "全部"],
  ["pending", "待运行"],
  ["processing", "运行中"],
  ["completed", "已完成"],
  ["rejected", "已拒绝"],
  ["failed", "失败"]
];

const referenceTerminal = new Set(["initial_rejected", "fine_rejected", "completed", "failed"]);
const runTerminal = new Set(["completed", "failed"]);

type LedgerItem =
  | {
      key: string;
      kind: "reference";
      activityAt: string;
      reference: Reference;
      run: WorkflowRun | null;
    }
  | {
      key: string;
      kind: "run";
      activityAt: string;
      run: WorkflowRun;
    };

type LedgerTab = "original" | "analysis" | "trace";

function duration(run: WorkflowRun | null): string | null {
  if (!run) return null;
  const end = run.completed_at ? new Date(run.completed_at).getTime() : Date.now();
  const seconds = Math.max(0, Math.round((end - new Date(run.started_at).getTime()) / 1000));
  if (!Number.isFinite(seconds)) return null;
  if (seconds < 60) return `${seconds} 秒`;
  const minutes = Math.floor(seconds / 60);
  return seconds < 3600 ? `${minutes} 分 ${seconds % 60} 秒` : `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分`;
}

function ReferenceLedgerRow({
  item,
  expanded,
  onToggle,
  onRetry,
  retrying
}: {
  item: Extract<LedgerItem, {kind: "reference"}>;
  expanded: boolean;
  onToggle: () => void;
  onRetry: (event: MouseEvent<HTMLButtonElement>) => void;
  retrying: boolean;
}) {
  const [tab, setTab] = useState<LedgerTab>("original");
  const {reference, run} = item;
  const panelId = `ledger-panel-${reference.id}`;
  const summary = plainText(
    reference.analysis?.one_sentence_summary ?? reference.summary,
    "暂无摘要"
  );

  return (
    <article className={`run-ledger-row ${expanded ? "expanded" : ""}`} id={`reference-${reference.id}`}>
      <div className="run-ledger-summary">
        <button
          type="button"
          className="run-ledger-toggle"
          aria-expanded={expanded}
          aria-controls={panelId}
          onClick={onToggle}
        >
          <div className="ledger-status-line">
            <ReferenceStatus value={reference.analysis_status} />
            <span>{reference.source_name ?? "未知来源"}</span>
            <time>{formatTime(reference.published_at)}</time>
          </div>
          <div className="ledger-title-line">
            <div>
              <h2>{reference.title ?? "未命名内容"}</h2>
              <p>{summary}</p>
            </div>
            {reference.analysis?.total_score !== null && reference.analysis?.total_score !== undefined ? (
              <strong className="ledger-score" aria-label={`质量评分 ${reference.analysis.total_score}`}>
                {reference.analysis.total_score}<small>/100</small>
              </strong>
            ) : null}
          </div>
          <div className="ledger-run-line">
            {run ? (
              <>
                <code>RUN {run.id.slice(0, 8)}</code>
                <Status value={run.status} />
                <span>{formatTime(run.started_at)}</span>
                {duration(run) ? <span>耗时 {duration(run)}</span> : null}
              </>
            ) : reference.analysis_workflow_run_id ? (
              <span>运行记录暂不可用 · {reference.analysis_workflow_run_id.slice(0, 8)}</span>
            ) : (
              <span>等待创建运行</span>
            )}
            <span className="ledger-expand-label">{expanded ? "收起" : "展开详情"} ↓</span>
          </div>
        </button>
        {reference.analysis_status === "failed" ? (
          <div className="ledger-failure">
            <span>{reference.analysis_error_message ?? "分析运行失败"}</span>
            <button className="tiny secondary" disabled={retrying} onClick={onRetry}>
              {retrying ? "正在排队…" : "重新分析"}
            </button>
          </div>
        ) : null}
      </div>
      {expanded ? (
        <div className="run-ledger-expanded" id={panelId}>
          <div className="ledger-tabs" role="tablist" aria-label="运行详情">
            {([
              ["original", "原文预览"],
              ["analysis", "分析结果"],
              ["trace", "Agent 轨迹"]
            ] as const).map(([value, label]) => (
              <button
                type="button"
                role="tab"
                aria-selected={tab === value}
                className={tab === value ? "active" : ""}
                key={value}
                onClick={() => setTab(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="ledger-tab-panel" role="tabpanel">
            {tab === "original" ? <ReferenceOriginalReader reference={reference} /> : null}
            {tab === "analysis" ? <ReferenceAnalysisPanel reference={reference} /> : null}
            {tab === "trace" ? <AgentTracePanel run={run} /> : null}
          </div>
        </div>
      ) : null}
    </article>
  );
}

function UnlinkedRunRow({
  item,
  expanded,
  onToggle
}: {
  item: Extract<LedgerItem, {kind: "run"}>;
  expanded: boolean;
  onToggle: () => void;
}) {
  const panelId = `ledger-panel-run-${item.run.id}`;
  return (
    <article className={`run-ledger-row unlinked ${expanded ? "expanded" : ""}`} id={`run-${item.run.id}`}>
      <button
        type="button"
        className="run-ledger-toggle"
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={onToggle}
      >
        <div className="ledger-status-line">
          <Status value={item.run.status} />
          <span>未关联引用</span>
          <time>{formatTime(item.run.started_at)}</time>
        </div>
        <div className="ledger-title-line">
          <div>
            <h2>工作流运行 {item.run.id.slice(0, 8)}</h2>
            <p>{item.run.error ?? "该运行没有关联到当前内容引用，可继续查看节点与 Agent 会话。"}</p>
          </div>
        </div>
        <div className="ledger-run-line">
          <code>{item.run.id}</code>
          {duration(item.run) ? <span>耗时 {duration(item.run)}</span> : null}
          <span className="ledger-expand-label">{expanded ? "收起" : "展开详情"} ↓</span>
        </div>
      </button>
      {expanded ? (
        <div className="run-ledger-expanded" id={panelId}>
          <AgentTracePanel run={item.run} />
        </div>
      ) : null}
    </article>
  );
}

export function RunsPage() {
  const [filter, setFilter] = useState<ReferenceStatusGroup>("all");
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const references = useQuery({
    queryKey: ["references"],
    queryFn: () => api<{items: Reference[]}>("/references"),
    refetchInterval: (query) =>
      query.state.data?.items?.some((item) => !referenceTerminal.has(item.analysis_status)) ? 5000 : false,
    retry: false
  });
  const runs = useQuery({
    queryKey: ["workflow-runs"],
    queryFn: () => api<{items: WorkflowRun[]}>("/workflow-runs"),
    refetchInterval: (query) =>
      query.state.data?.items?.some((item) => !runTerminal.has(item.status)) ? 5000 : false,
    retry: false
  });
  const reanalyze = useMutation({
    mutationFn: (id: string) => api(`/references/${id}/reanalyze`, {method: "POST"}),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({queryKey: ["references"]}),
        queryClient.invalidateQueries({queryKey: ["workflow-runs"]}),
        queryClient.invalidateQueries({queryKey: ["analyses"]}),
        queryClient.invalidateQueries({queryKey: ["agent-sessions"]})
      ]);
    }
  });

  const items = useMemo<LedgerItem[]>(() => {
    const runById = new Map((runs.data?.items ?? []).map((run) => [run.id, run]));
    const linked = new Set<string>();
    const referenceItems: LedgerItem[] = (references.data?.items ?? []).map((reference) => {
      if (reference.analysis_workflow_run_id) linked.add(reference.analysis_workflow_run_id);
      return {
        key: `reference:${reference.id}`,
        kind: "reference",
        activityAt: reference.analysis_status_updated_at ?? reference.last_seen_at,
        reference,
        run: reference.analysis_workflow_run_id
          ? runById.get(reference.analysis_workflow_run_id) ?? null
          : null
      };
    });
    const unlinked: LedgerItem[] = (runs.data?.items ?? [])
      .filter((run) => !linked.has(run.id))
      .map((run) => ({
        key: `run:${run.id}`,
        kind: "run",
        activityAt: run.completed_at ?? run.started_at,
        run
      }));
    return [...referenceItems, ...unlinked].sort(
      (left, right) => new Date(right.activityAt).getTime() - new Date(left.activityAt).getTime()
    );
  }, [references.data, runs.data]);

  const visibleItems = items.filter((item) =>
    filter === "all" || (item.kind === "reference" && referenceStatusGroup(item.reference.analysis_status) === filter)
  );
  const selectedReference = searchParams.get("reference");
  const selectedRun = searchParams.get("run");
  const selectedKey = selectedReference
    ? `reference:${selectedReference}`
    : selectedRun
      ? `run:${selectedRun}`
      : null;
  const requestedMissing = Boolean(
    selectedKey && !references.isLoading && !runs.isLoading && !items.some((item) => item.key === selectedKey)
  );

  useEffect(() => {
    if (!selectedKey || requestedMissing) return;
    const id = selectedKey.startsWith("reference:")
      ? `reference-${selectedKey.slice("reference:".length)}`
      : `run-${selectedKey.slice("run:".length)}`;
    document.getElementById(id)?.scrollIntoView?.({block: "start"});
  }, [requestedMissing, selectedKey]);

  function toggle(item: LedgerItem) {
    if (selectedKey === item.key) {
      setSearchParams({}, {replace: true});
      return;
    }
    setSearchParams(
      item.kind === "reference" ? {reference: item.reference.id} : {run: item.run.id},
      {replace: true}
    );
  }

  return (
    <>
      <PageHeader
        eyebrow="EXECUTION LEDGER"
        title="运行记录"
        description="从 RSS 引用入库到 Agent 分析完成，在一条记录里预览原文、结果与完整执行轨迹。"
      />
      <div className="reference-toolbar run-ledger-toolbar" aria-label="运行状态筛选">
        {filters.map(([value, label]) => (
          <button
            type="button"
            className={filter === value ? "active" : ""}
            key={value}
            onClick={() => setFilter(value)}
          >
            {label}
          </button>
        ))}
      </div>
      {references.error ? <ErrorNotice error={references.error} /> : null}
      {runs.error ? <ErrorNotice error={runs.error} /> : null}
      {requestedMissing ? <div className="notice warning">未找到对应引用或运行记录。</div> : null}
      {(references.isLoading || runs.isLoading) && !items.length ? (
        <div className="analysis-loading">正在整理全链路运行记录…</div>
      ) : null}
      {!references.isLoading && !runs.isLoading && !visibleItems.length ? (
        <Empty>当前筛选条件下没有运行记录。</Empty>
      ) : null}
      {visibleItems.length ? (
        <section className="run-ledger" aria-label="全链路运行记录">
          {visibleItems.map((item) =>
            item.kind === "reference" ? (
              <ReferenceLedgerRow
                item={item}
                expanded={selectedKey === item.key}
                key={item.key}
                retrying={reanalyze.isPending && reanalyze.variables === item.reference.id}
                onToggle={() => toggle(item)}
                onRetry={(event) => {
                  event.stopPropagation();
                  reanalyze.mutate(item.reference.id);
                }}
              />
            ) : (
              <UnlinkedRunRow
                item={item}
                expanded={selectedKey === item.key}
                key={item.key}
                onToggle={() => toggle(item)}
              />
            )
          )}
        </section>
      ) : null}
    </>
  );
}
