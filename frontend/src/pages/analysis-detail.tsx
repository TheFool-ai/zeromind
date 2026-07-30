import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query";
import {useState, type FormEvent} from "react";
import {Link, useParams} from "react-router-dom";

import {
  api,
  type AnalysisDecision,
  type AnalysisDetail,
  type AnalysisExecution
} from "../api/client";
import {
  AnalysisStatus,
  analysisStatusLabels,
  dimensionLabels,
  ErrorNotice,
  formatTime
} from "../components";

function Provenance({
  name,
  execution
}: {
  name: string;
  execution: AnalysisExecution;
}) {
  return (
    <article className="provenance-card">
      <span>{name === "screening" ? "初筛 Agent" : "细筛分析 Agent"}</span>
      <strong>
        {execution.provider} / {execution.model}
      </strong>
      <code>
        Agent {execution.agent_id} · 版本 {execution.agent_version}
      </code>
    </article>
  );
}

export function AnalysisDetailPage() {
  const {analysisId} = useParams<{analysisId: string}>();
  const queryClient = useQueryClient();
  const [decision, setDecision] =
    useState<AnalysisDecision>("rejected");
  const [reason, setReason] = useState("");
  const analysis = useQuery({
    queryKey: ["analysis", analysisId],
    queryFn: () => api<AnalysisDetail>(`/analyses/${analysisId}`),
    enabled: Boolean(analysisId),
    retry: false
  });
  const override = useMutation({
    mutationFn: (payload: {
      decision: AnalysisDecision;
      reason: string;
    }) =>
      api<AnalysisDetail>(`/analyses/${analysisId}/overrides`, {
        method: "POST",
        body: JSON.stringify(payload)
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["analysis", analysisId], updated);
      void queryClient.invalidateQueries({queryKey: ["analyses"]});
      setReason("");
    }
  });

  function submitOverride(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = reason.trim();
    if (normalized.length < 10) return;
    override.mutate({decision, reason: normalized});
  }

  if (analysis.isLoading) {
    return <div className="analysis-loading">正在读取结构化分析…</div>;
  }
  if (analysis.error) {
    return (
      <div className="detail-error">
        <Link to="/analyses">← 返回信息流</Link>
        <ErrorNotice error={analysis.error} />
      </div>
    );
  }
  if (!analysis.data) return null;

  const item = analysis.data;
  return (
    <article className="analysis-detail">
      <header className="analysis-detail-header">
        <Link className="back-link" to="/analyses">
          ← 返回信息流
        </Link>
        <div className="detail-status-row">
          <AnalysisStatus value={item.generated_status} />
          {item.overridden ? (
            <span className="override-badge">
              当前决定：{analysisStatusLabels[item.effective_decision]}
            </span>
          ) : null}
        </div>
        <p className="eyebrow">{item.source_name}</p>
        <h1>{item.title}</h1>
        <p className="detail-deck">
          {item.one_sentence_summary ?? item.screening.summary}
        </p>
        <div className="detail-byline">
          <span>{item.author ?? "未知作者"}</span>
          <time>{formatTime(item.published_at ?? item.observed_at)}</time>
          {item.original_url ? (
            <a
              href={item.original_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              查看原文 ↗
            </a>
          ) : null}
        </div>
      </header>

      <div className="analysis-detail-layout">
        <main className="analysis-story">
          <section className="detail-section">
            <p className="section-kicker">STRUCTURED SUMMARY</p>
            <h2>内容摘要</h2>
            <p className="long-copy">
              {item.summary ?? "该内容在初筛阶段被拒绝，没有生成深度摘要。"}
            </p>
          </section>

          <section className="detail-section">
            <p className="section-kicker">VIEWPOINTS</p>
            <h2>观点总结</h2>
            {item.viewpoints.length ? (
              <ol className="viewpoint-list">
                {item.viewpoints.map((viewpoint, index) => (
                  <li key={`${index}-${viewpoint.statement}`}>
                    <strong>{viewpoint.statement}</strong>
                    <p>{viewpoint.explanation}</p>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="muted">没有生成观点总结。</p>
            )}
          </section>

          <section className="detail-section">
            <p className="section-kicker">KEY QUOTES</p>
            <h2>金句摘录</h2>
            {item.key_quotes.length ? (
              <div className="quote-list">
                {item.key_quotes.map((quote, index) => (
                  <blockquote key={`${index}-${quote.text}`}>
                    <p>{quote.text}</p>
                    {quote.context ? <cite>{quote.context}</cite> : null}
                  </blockquote>
                ))}
              </div>
            ) : (
              <p className="muted">没有提取到金句。</p>
            )}
          </section>

          <section className="detail-section">
            <p className="section-kicker">SCORING</p>
            <div className="score-heading">
              <h2>价值评分</h2>
              <div className="total-score">
                <strong>{item.total_score ?? "—"}</strong>
                <span>/ 100</span>
              </div>
            </div>
            <div className="dimension-grid">
              {item.dimensions.map((dimension) => (
                <article className="dimension-card" key={dimension.name}>
                  <div>
                    <strong>
                      {dimensionLabels[dimension.name] ?? dimension.name}
                    </strong>
                    <span>{Math.round(dimension.weight * 100)}%</span>
                  </div>
                  <data value={dimension.value}>{dimension.value}</data>
                  <p>{dimension.reason}</p>
                </article>
              ))}
            </div>
            {item.recommendation_reason ? (
              <p className="recommendation">
                <strong>推荐理由</strong>
                {item.recommendation_reason}
              </p>
            ) : null}
          </section>
        </main>

        <aside className="analysis-inspection">
          <section className="inspection-panel screening-panel">
            <div className="inspection-heading">
              <h2>初筛结论</h2>
              <strong>{item.screening.score}</strong>
            </div>
            <p>{item.screening.reason}</p>
            {item.screening.summary ? (
              <small>{item.screening.summary}</small>
            ) : null}
          </section>

          <section className="inspection-panel">
            <h2>分类与标签</h2>
            <div className="classification-stack">
              {item.primary_category ? (
                <span className="category-chip">{item.primary_category}</span>
              ) : null}
              {item.secondary_categories.map((category) => (
                <span key={category}>{category}</span>
              ))}
            </div>
            <div className="tag-list">
              {item.tags.map((tag) => (
                <span key={tag}>#{tag}</span>
              ))}
            </div>
          </section>

          <section className="inspection-panel">
            <h2>执行溯源</h2>
            <p className="workflow-provenance">
              工作流版本 {item.workflow_definition_version}
              <code>{item.workflow_definition_id}</code>
              <code>运行 {item.workflow_run_id}</code>
              <code>
                引用 {item.reference_id} · 修订 {item.reference_revision}
              </code>
            </p>
            <div className="provenance-list">
              {Object.entries(item.provenance).map(([name, execution]) => (
                <Provenance
                  key={name}
                  name={name}
                  execution={execution}
                />
              ))}
            </div>
          </section>

          <section className="inspection-panel">
            <h2>人工决策</h2>
            <form className="override-form" onSubmit={submitOverride}>
              <label>
                人工决策
                <select
                  value={decision}
                  onChange={(event) =>
                    setDecision(event.target.value as AnalysisDecision)
                  }
                >
                  <option value="rejected">拒绝</option>
                  <option value="qualified">通过</option>
                </select>
              </label>
              <label>
                改判理由
                <textarea
                  value={reason}
                  maxLength={2000}
                  onChange={(event) => setReason(event.target.value)}
                  placeholder="至少 10 个字符，说明人工复核依据"
                />
              </label>
              <button
                type="submit"
                disabled={reason.trim().length < 10 || override.isPending}
              >
                {override.isPending ? "提交中…" : "提交改判"}
              </button>
              {override.error ? <ErrorNotice error={override.error} /> : null}
            </form>
            {item.overrides.length ? (
              <ol className="override-history">
                {item.overrides
                  .slice()
                  .reverse()
                  .map((entry) => (
                    <li key={entry.id}>
                      <div>
                        <AnalysisStatus value={entry.decision} />
                        <time>{formatTime(entry.created_at)}</time>
                      </div>
                      <p>{entry.reason}</p>
                      <small>{entry.actor_subject}</small>
                    </li>
                  ))}
              </ol>
            ) : (
              <p className="muted">还没有人工改判记录。</p>
            )}
          </section>
        </aside>
      </div>
    </article>
  );
}
