import {useQuery} from "@tanstack/react-query";

import {
  api,
  type AgentSession,
  type AnalysisDetail,
  type Reference,
  type ReferenceAnalysisStatus,
  type ReferenceReaderContent,
  type WorkflowRun
} from "../api/client";
import {
  dimensionLabels,
  Empty,
  ErrorNotice,
  formatTime,
  ReferenceStatus,
  referenceStatusLabels,
  Status
} from "../components";
import {plainText} from "../text";

const stages: ReferenceAnalysisStatus[] = [
  "pending",
  "queued",
  "screening",
  "resolving",
  "analyzing",
  "classifying",
  "scoring",
  "reviewing",
  "finalizing",
  "completed"
];

const terminal = new Set<ReferenceAnalysisStatus>([
  "initial_rejected",
  "fine_rejected",
  "completed",
  "failed"
]);

export function ReferenceOriginalReader({reference}: {reference: Reference}) {
  const originalContent = useQuery({
    queryKey: ["reference-reader-content", reference.id],
    queryFn: () =>
      api<ReferenceReaderContent>(`/references/${reference.id}/content`),
    enabled: Boolean(reference.original_url),
    retry: false
  });

  return (
    <section className="reference-original ledger-original">
      <div className="original-toolbar">
        <strong>原文预览</strong>
        {reference.original_url ? (
          <a href={reference.original_url} target="_blank" rel="noreferrer">
            新窗口打开原文 ↗
          </a>
        ) : null}
      </div>
      {originalContent.isLoading ? (
        <div className="original-loading" aria-live="polite">
          <span />
          <strong>正在提取原文…</strong>
          <p>正文只在本次请求中临时读取，不会写入数据库。</p>
        </div>
      ) : null}
      {originalContent.data ? (
        <article className="original-reader">
          <div className="original-reader-meta">
            <span>{originalContent.data.language ?? "原文"}</span>
            {originalContent.data.author ? (
              <strong>{originalContent.data.author}</strong>
            ) : null}
          </div>
          <h2>{originalContent.data.title ?? reference.title ?? "未命名内容"}</h2>
          <div className="original-reader-body">{originalContent.data.text}</div>
          <footer>
            <span>正文为实时提取结果，未在 ZeroMind 中持久化。</span>
            <a href={originalContent.data.final_url} target="_blank" rel="noreferrer">
              查看来源 ↗
            </a>
          </footer>
        </article>
      ) : null}
      {!reference.original_url ? (
        <Empty>该引用没有可预览的原文地址。</Empty>
      ) : null}
      {reference.original_url && !originalContent.isLoading && !originalContent.data ? (
        <div className="original-fallback" role={originalContent.error ? "alert" : undefined}>
          <strong>暂时无法生成站内原文</strong>
          <p>
            原站可能要求登录、依赖浏览器脚本或暂时不可访问。这里保留 RSS
            元数据作为回退。
          </p>
          <dl>
            <div><dt>标题</dt><dd>{reference.title ?? "—"}</dd></div>
            <div><dt>摘要</dt><dd>{plainText(reference.summary)}</dd></div>
            <div><dt>作者</dt><dd>{reference.author ?? "—"}</dd></div>
          </dl>
          <div className="original-fallback-actions">
            <button
              className="secondary"
              onClick={() => void originalContent.refetch()}
            >
              重新提取
            </button>
            <a href={reference.original_url} target="_blank" rel="noreferrer">
              新窗口打开原文 ↗
            </a>
          </div>
        </div>
      ) : null}
    </section>
  );
}

export function ReferenceAnalysisPanel({reference}: {reference: Reference}) {
  const analysis = useQuery({
    queryKey: ["analysis", reference.analysis?.id],
    queryFn: () => api<AnalysisDetail>(`/analyses/${reference.analysis?.id}`),
    enabled: Boolean(reference.analysis?.id),
    retry: false
  });
  const activeStage = stages.indexOf(reference.analysis_status);
  const processing = !terminal.has(reference.analysis_status);

  if (!reference.analysis) {
    return (
      <section className="ledger-panel-stack">
        <div className="rail-section">
          <p className="section-kicker">ANALYSIS STATE</p>
          <h2>{referenceStatusLabels[reference.analysis_status]}</h2>
          {processing ? (
            <ol className="reference-stage-list">
              {stages.slice(0, -1).map((stage, index) => (
                <li className={index <= activeStage ? "active" : ""} key={stage}>
                  <span>{index + 1}</span>{referenceStatusLabels[stage]}
                </li>
              ))}
            </ol>
          ) : (
            <p>{reference.analysis_error_message ?? "当前引用尚未生成结构化分析结果。"}</p>
          )}
        </div>
      </section>
    );
  }

  if (analysis.error) return <ErrorNotice error={analysis.error} />;
  if (!analysis.data) return <div className="analysis-loading">正在读取结构化分析…</div>;
  const value = analysis.data;

  return (
    <section className="ledger-panel-stack">
      <div className="ledger-analysis-heading">
        <div>
          <ReferenceStatus value={reference.analysis_status} />
          <h2>{value.one_sentence_summary ?? value.title}</h2>
        </div>
        <strong aria-label={`综合评分 ${value.total_score ?? "暂无"}`}>
          {value.total_score ?? "—"}<small>/100</small>
        </strong>
      </div>
      <div className="rail-section">
        <p className="section-kicker">SUMMARY</p>
        <h2>内容摘要</h2>
        <p>{value.summary ?? value.screening.summary ?? "—"}</p>
      </div>
      {value.viewpoints.length ? (
        <div className="rail-section">
          <p className="section-kicker">VIEWPOINTS</p>
          <h2>核心观点</h2>
          <ol className="viewpoint-list">
            {value.viewpoints.map((item) => (
              <li key={item.statement}>
                <strong>{item.statement}</strong><p>{item.explanation}</p>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
      {value.key_quotes.length ? (
        <div className="rail-section">
          <p className="section-kicker">KEY QUOTES</p>
          <h2>关键引文</h2>
          <div className="quote-list">
            {value.key_quotes.map((quote) => (
              <blockquote key={quote.text}>
                <p>“{quote.text}”</p>
                {quote.context ? <cite>{quote.context}</cite> : null}
              </blockquote>
            ))}
          </div>
        </div>
      ) : null}
      <div className="rail-section">
        <p className="section-kicker">QUALITY</p>
        <h2>质量评分</h2>
        <div className="dimension-grid">
          {value.dimensions.map((dimension) => (
            <div className="dimension-card" key={dimension.name}>
              <div>
                <strong>{dimensionLabels[dimension.name] ?? dimension.name}</strong>
                <span>权重 {Math.round(dimension.weight * 100)}%</span>
              </div>
              <data>{dimension.value}</data>
              <p>{dimension.reason}</p>
            </div>
          ))}
        </div>
        {value.recommendation_level ? (
          <div className="recommendation">
            <strong>{value.recommendation_level}</strong>
            <span>{value.recommendation_reason}</span>
          </div>
        ) : null}
      </div>
      <div className="rail-section">
        <p className="section-kicker">TAXONOMY</p>
        <h2>分类与标签</h2>
        <div className="classification-stack">
          {value.primary_category ? <span className="category-chip">{value.primary_category}</span> : null}
          {value.secondary_categories.map((category) => <span key={category}>{category}</span>)}
          {value.tags.map((tag) => <span key={tag}>#{tag}</span>)}
        </div>
      </div>
    </section>
  );
}

export function AgentTracePanel({run}: {run: WorkflowRun | null}) {
  const sessions = useQuery({
    queryKey: ["agent-sessions", run?.id],
    queryFn: () =>
      api<{items: AgentSession[]}>(`/agent-sessions?workflow_run_id=${run?.id}`),
    enabled: Boolean(run),
    refetchInterval: run && !["completed", "failed"].includes(run.status) ? 5000 : false,
    retry: false
  });

  if (!run) return <Empty>工作流尚未创建，当前没有 Agent 轨迹。</Empty>;

  return (
    <section className="trace-panel">
      <header className="trace-header">
        <div>
          <p className="section-kicker">WORKFLOW RUN</p>
          <code>{run.id}</code>
        </div>
        <Status value={run.status} />
      </header>
      {run.error ? <div className="notice error">{run.error}</div> : null}
      {sessions.error ? <ErrorNotice error={sessions.error} /> : null}
      <div className="trace-timeline">
        {run.steps.map((step, index) => {
          const stepSessions = sessions.data?.items
            .filter((session) => session.step_run_id === step.id)
            .sort((left, right) => left.attempt - right.attempt) ?? [];
          return (
            <div className="timeline-group" key={step.id}>
              <div className="timeline-item">
                <span className="timeline-index">{index + 1}</span>
                <div>
                  <strong>{step.node_id}</strong>
                  <small>尝试 {step.attempts} 次{step.error ? ` · ${step.error}` : ""}</small>
                </div>
                <Status value={step.status} />
              </div>
              {stepSessions.map((session) => (
                <details className="session-row" key={session.id}>
                  <summary>
                    <span>Agent · {session.provider}/{session.model} · 尝试 {session.attempt}</span>
                    <Status value={session.status} />
                  </summary>
                  <small>
                    Agent {session.agent_id} · 版本 {session.agent_version_id} · {formatTime(session.started_at)}
                  </small>
                  {session.error_message ? (
                    <p className="trace-error">{session.error_code}: {session.error_message}</p>
                  ) : null}
                  {session.usage ? <p className="trace-usage">用量 {JSON.stringify(session.usage)}</p> : null}
                  <details className="trace-json">
                    <summary>查看输入与输出</summary>
                    <pre>{JSON.stringify(session.output ?? session.sanitized_input, null, 2)}</pre>
                  </details>
                </details>
              ))}
            </div>
          );
        })}
      </div>
      {!sessions.isLoading && !sessions.error && !sessions.data?.items.length ? (
        <Empty>此运行尚无 Agent 会话记录。</Empty>
      ) : null}
      <details className="trace-json run-output">
        <summary>查看工作流结构化输出</summary>
        <pre>{JSON.stringify(run.output ?? {}, null, 2)}</pre>
      </details>
    </section>
  );
}
