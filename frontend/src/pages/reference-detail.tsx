import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query";
import {useState} from "react";
import {Link, useParams} from "react-router-dom";

import {api, type ReferenceAnalysisStatus, type ReferenceReadingDetail} from "../api/client";
import {
  dimensionLabels,
  Empty,
  ErrorNotice,
  formatTime,
  ReferenceStatus,
  referenceStatusLabels
} from "../components";

const stages: ReferenceAnalysisStatus[] = [
  "pending", "queued", "screening", "resolving", "analyzing",
  "classifying", "scoring", "reviewing", "finalizing", "completed"
];
const terminal = new Set<ReferenceAnalysisStatus>([
  "initial_rejected", "fine_rejected", "completed", "failed"
]);

export function ReferenceDetailPage() {
  const {referenceId = ""} = useParams();
  const [mobileView, setMobileView] = useState<"analysis" | "original">("analysis");
  const queryClient = useQueryClient();
  const detail = useQuery({
    queryKey: ["reference-reading-detail", referenceId],
    queryFn: () => api<ReferenceReadingDetail>(`/references/${referenceId}/reading-detail`),
    refetchInterval: (query) => {
      const value = query.state.data;
      return value && !terminal.has(value.analysis_status) ? 5000 : false;
    },
    retry: false
  });
  const reanalyze = useMutation({
    mutationFn: () => api(`/references/${referenceId}/reanalyze`, {method: "POST"}),
    onSuccess: () => {
      queryClient.invalidateQueries({queryKey: ["reference-reading-detail", referenceId]});
      queryClient.invalidateQueries({queryKey: ["references"]});
    }
  });

  if (detail.error) return <ErrorNotice error={detail.error} />;
  if (!detail.data) return <Empty>正在读取引用与分析结果…</Empty>;
  const value = detail.data;
  const analysis = value.analysis;
  const originalUrl = value.revision.url ?? value.original_url;
  const processing = !terminal.has(value.analysis_status);
  const activeStage = stages.indexOf(value.analysis_status);

  return (
    <article className="reference-detail">
      <header className="reference-detail-header">
        <Link className="back-link" to="/references">← 返回内容引用</Link>
        <div className="reference-detail-title-row">
          <div>
            <div className="detail-status-row">
              <ReferenceStatus value={value.analysis_status} />
              <span>REV {value.current_revision}</span>
            </div>
            <h1>{value.revision.title}</h1>
            <p className="detail-deck">
              {analysis?.one_sentence_summary ?? value.revision.summary ?? "暂无内容摘要。"}
            </p>
          </div>
          {analysis?.total_score !== null && analysis?.total_score !== undefined ? (
            <div className="reference-total-score" aria-label={`总评分 ${analysis.total_score}`}>
              <strong>{analysis.total_score}</strong><span>/100</span>
            </div>
          ) : null}
        </div>
        <div className="detail-byline">
          <strong>{value.source_name ?? "未知来源"}</strong>
          {value.revision.author ? <span>{value.revision.author}</span> : null}
          <time>{formatTime(value.revision.published_at)}</time>
          {originalUrl ? <a href={originalUrl} target="_blank" rel="noreferrer">新窗口打开原文 ↗</a> : null}
        </div>
      </header>

      <div className="reference-mobile-tabs" role="tablist" aria-label="阅读视图">
        <button className={mobileView === "analysis" ? "active" : ""} onClick={() => setMobileView("analysis")}>AI 分析</button>
        <button className={mobileView === "original" ? "active" : ""} onClick={() => setMobileView("original")}>原文</button>
      </div>

      <div className="reference-reading-layout">
        <section className={`reference-original ${mobileView !== "original" ? "mobile-hidden" : ""}`}>
          <div className="original-toolbar">
            <strong>原文阅读</strong>
            {originalUrl ? <a href={originalUrl} target="_blank" rel="noreferrer">新窗口打开原文</a> : null}
          </div>
          {value.iframe_url ? (
            <iframe
              title={`原文：${value.revision.title}`}
              src={value.iframe_url}
              sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
              referrerPolicy="no-referrer-when-downgrade"
            />
          ) : null}
          <div className="original-fallback">
            <strong>如果原文无法显示</strong>
            <p>部分网站禁止被嵌入。你仍可在新窗口阅读；这里保留 RSS 元数据作为回退。</p>
            <dl>
              <div><dt>标题</dt><dd>{value.revision.title}</dd></div>
              <div><dt>摘要</dt><dd>{value.revision.summary ?? "—"}</dd></div>
              <div><dt>作者</dt><dd>{value.revision.author ?? "—"}</dd></div>
            </dl>
          </div>
        </section>

        <aside className={`reference-analysis-rail ${mobileView !== "analysis" ? "mobile-hidden" : ""}`}>
          {processing ? (
            <section className="rail-section">
              <p className="section-kicker">ANALYSIS IN PROGRESS</p>
              <h2>{referenceStatusLabels[value.analysis_status]}</h2>
              <ol className="reference-stage-list">
                {stages.slice(0, -1).map((stage, index) => (
                  <li className={index <= activeStage ? "active" : ""} key={stage}>
                    <span>{index + 1}</span>{referenceStatusLabels[stage]}
                  </li>
                ))}
              </ol>
            </section>
          ) : null}
          {value.analysis_status === "failed" ? (
            <section className="rail-section detail-error">
              <p className="section-kicker">TECHNICAL FAILURE</p>
              <h2>分析未完成</h2>
              <p>{value.analysis_error_message ?? "工作流运行失败，请修复后重试。"}</p>
              <button disabled={reanalyze.isPending} onClick={() => reanalyze.mutate()}>
                {reanalyze.isPending ? "正在排队…" : "重新分析"}
              </button>
            </section>
          ) : null}
          {(value.analysis_status === "initial_rejected" || value.analysis_status === "fine_rejected") ? (
            <section className="rail-section notice warning">
              <h2>{referenceStatusLabels[value.analysis_status]}</h2>
              <p>{analysis?.screening.reason ?? "内容未通过当前业务筛选门槛。"}</p>
            </section>
          ) : null}
          {analysis ? (
            <>
              <section className="rail-section">
                <p className="section-kicker">ONE SENTENCE</p>
                <h2>一句话总结</h2>
                <p className="rail-lead">{analysis.one_sentence_summary ?? "—"}</p>
              </section>
              <section className="rail-section">
                <p className="section-kicker">SUMMARY</p>
                <h2>内容摘要</h2>
                <p className="long-copy">{analysis.summary ?? analysis.screening.summary ?? "—"}</p>
              </section>
              {analysis.viewpoints.length ? (
                <section className="rail-section">
                  <p className="section-kicker">VIEWPOINTS</p><h2>核心观点</h2>
                  <ol className="viewpoint-list">
                    {analysis.viewpoints.map((item) => <li key={item.statement}><strong>{item.statement}</strong><p>{item.explanation}</p></li>)}
                  </ol>
                </section>
              ) : null}
              {analysis.key_quotes.length ? (
                <section className="rail-section">
                  <p className="section-kicker">KEY QUOTES</p><h2>关键引文</h2>
                  <div className="quote-list">{analysis.key_quotes.map((quote) => <blockquote key={quote.text}><p>“{quote.text}”</p>{quote.context ? <cite>{quote.context}</cite> : null}</blockquote>)}</div>
                </section>
              ) : null}
              <section className="rail-section">
                <div className="score-heading"><div><p className="section-kicker">QUALITY</p><h2>六维评分</h2></div><div className="total-score"><strong>{analysis.total_score ?? "—"}</strong><span>/100</span></div></div>
                <div className="dimension-grid">{analysis.dimensions.map((dimension) => <div className="dimension-card" key={dimension.name}><div><strong>{dimensionLabels[dimension.name] ?? dimension.name}</strong><span>权重 {Math.round(dimension.weight * 100)}%</span></div><data>{dimension.value}</data><p>{dimension.reason}</p></div>)}</div>
                {analysis.recommendation_level ? <div className="recommendation"><strong>{analysis.recommendation_level}</strong><span>{analysis.recommendation_reason}</span></div> : null}
              </section>
              <section className="rail-section">
                <p className="section-kicker">TAXONOMY</p><h2>分类与标签</h2>
                <div className="classification-stack">
                  {analysis.primary_category ? <span className="category-chip">{analysis.primary_category}</span> : null}
                  {analysis.secondary_categories.map((category) => <span key={category}>{category}</span>)}
                  {analysis.tags.map((tag) => <span key={tag}>#{tag}</span>)}
                </div>
              </section>
              <section className="rail-section">
                <p className="section-kicker">PROVENANCE</p><h2>Agent 追溯</h2>
                <div className="provenance-list">{Object.entries(analysis.provenance).map(([stage, execution]) => <div className="provenance-card" key={stage}><span>{stage}</span><strong>{execution.provider} · {execution.model}</strong><code>Agent {execution.agent_id} · v{execution.agent_version}</code></div>)}</div>
              </section>
            </>
          ) : !processing && value.analysis_status !== "failed" ? (
            <section className="rail-section"><h2>暂无结构化分析</h2><p>当前引用尚未生成可展示的分析结果。</p></section>
          ) : null}
        </aside>
      </div>
    </article>
  );
}
