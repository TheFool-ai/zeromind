import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query";
import {useState, type MouseEvent} from "react";
import {Link} from "react-router-dom";

import {api, type Reference} from "../api/client";
import {
  Empty,
  ErrorNotice,
  formatTime,
  PageHeader,
  ReferenceStatus,
  referenceStatusGroup,
  type ReferenceStatusGroup
} from "../components";
import {plainText} from "../text";

const filters: Array<[ReferenceStatusGroup, string]> = [
  ["all", "全部"],
  ["pending", "待分析"],
  ["processing", "分析中"],
  ["completed", "已完成"],
  ["rejected", "已拒绝"],
  ["failed", "失败"]
];

export function ReferencesPage() {
  const [filter, setFilter] = useState<ReferenceStatusGroup>("all");
  const queryClient = useQueryClient();
  const references = useQuery({
    queryKey: ["references"],
    queryFn: () => api<{items: Reference[]}>("/references"),
    retry: false
  });
  const reanalyze = useMutation({
    mutationFn: (id: string) => api(`/references/${id}/reanalyze`, {method: "POST"}),
    onSuccess: () => queryClient.invalidateQueries({queryKey: ["references"]})
  });
  const items = references.data?.items.filter((item) =>
    filter === "all" || referenceStatusGroup(item.analysis_status) === filter
  ) ?? [];

  function retry(event: MouseEvent<HTMLButtonElement>, id: string) {
    event.preventDefault();
    event.stopPropagation();
    reanalyze.mutate(id);
  }

  return (
    <>
      <PageHeader
        eyebrow="REFERENCE INDEX"
        title="内容引用"
        description="这里只保存原文地址与 RSS 元数据修订；文章正文在工作流运行时即时读取。"
      />
      <div className="reference-toolbar" aria-label="引用状态筛选">
        {filters.map(([value, label]) => (
          <button
            className={filter === value ? "active" : ""}
            key={value}
            onClick={() => setFilter(value)}
          >{label}</button>
        ))}
      </div>
      {references.error ? <ErrorNotice error={references.error} /> : null}
      {!references.isLoading && !items.length ? (
          <Empty>尚未发现内容。下一次 Feed 抓取后，引用会显示在这里。</Empty>
        ) : (
          <div className="reference-grid">
            {items.map((item) => (
              <Link className="reference-card" to={`/references/${item.id}`} key={item.id}>
                <div className="reference-meta">
                  <ReferenceStatus value={item.analysis_status} />
                  <time>{formatTime(item.published_at)}</time>
                </div>
                <p className="reference-source">
                  {item.source_name ?? "未知来源"}
                  {item.author ? ` · ${item.author}` : ""}
                </p>
                <h2>{item.title ?? "未命名内容"}</h2>
                <p className="reference-summary">
                  {plainText(item.analysis?.one_sentence_summary ?? item.summary, "暂无摘要")}
                </p>
                {item.analysis ? (
                  <div className="reference-analysis-preview">
                    {item.analysis.total_score !== null ? (
                      <strong aria-label={`质量评分 ${item.analysis.total_score}`}>
                        {item.analysis.total_score}<small>/100</small>
                      </strong>
                    ) : null}
                    {item.analysis.primary_category ? <span>{item.analysis.primary_category}</span> : null}
                    {item.analysis.tags.slice(0, 3).map((tag) => <span key={tag}>#{tag}</span>)}
                  </div>
                ) : null}
                {item.analysis_status === "failed" ? (
                  <div className="reference-failure">
                    <span>{item.analysis_error_message ?? "分析运行失败"}</span>
                    <button
                      className="tiny secondary"
                      disabled={reanalyze.isPending}
                      onClick={(event) => retry(event, item.id)}
                    >重新分析</button>
                  </div>
                ) : null}
                <footer><span>REV {item.current_revision}</span><span>查看详情 →</span></footer>
              </Link>
            ))}
          </div>
        )}
    </>
  );
}
