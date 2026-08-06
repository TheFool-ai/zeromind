import {keepPreviousData, useInfiniteQuery, useQuery} from "@tanstack/react-query";
import {useMemo, useState} from "react";
import {Link} from "react-router-dom";

import {
  api,
  type AnalysisCard,
  type AnalysisDecision,
  type Subscription
} from "../api/client";
import {
  AnalysisStatus,
  Empty,
  ErrorNotice,
  formatTime,
  PageHeader
} from "../components";

type AnalysisPage = {
  items: AnalysisCard[];
  next_cursor: string | null;
};

type AnalysisSort = "score" | "time";

function queryPath(
  filters: {
    effectiveDecision: AnalysisDecision;
    minimumScore: string;
    category: string;
    subscriptionId: string;
    from: string;
    to: string;
    sort: AnalysisSort;
  },
  cursor: string | null
): string {
  const query = new URLSearchParams({
    effective_decision: filters.effectiveDecision,
    sort: filters.sort
  });
  if (filters.minimumScore) {
    query.set("minimum_score", filters.minimumScore);
  }
  if (filters.category.trim()) {
    query.set("category", filters.category.trim());
  }
  if (filters.subscriptionId) {
    query.set("subscription_id", filters.subscriptionId);
  }
  if (filters.from) {
    query.set("observed_from", `${filters.from}T00:00:00Z`);
  }
  if (filters.to) {
    query.set("observed_to", `${filters.to}T23:59:59.999Z`);
  }
  if (cursor) {
    query.set("cursor", cursor);
  }
  return `/analyses?${query.toString()}`;
}

function AnalysisCardView({item}: {item: AnalysisCard}) {
  return (
    <article className="analysis-card">
      <div className="analysis-card-main">
        <div className="analysis-card-top">
          <AnalysisStatus value={item.generated_status} />
          {item.overridden ? (
            <span className="override-badge">人工改判</span>
          ) : null}
          <span className="analysis-source">
            <strong>{item.source_name}</strong>
            <time>{formatTime(item.published_at ?? item.observed_at)}</time>
          </span>
        </div>
        <h2>
          <Link to={`/analyses/${item.id}`}>{item.title}</Link>
        </h2>
        <p className="analysis-summary">
          {item.one_sentence_summary ?? "该条目没有生成一句话摘要。"}
        </p>
        <div className="analysis-classification">
          {item.primary_category ? (
            <span className="category-chip">{item.primary_category}</span>
          ) : null}
          {item.tags.map((tag) => (
            <span key={tag}>#{tag}</span>
          ))}
        </div>
      </div>
      <div
        className="analysis-card-score"
        aria-label={`综合评分 ${item.total_score ?? "暂无"}`}
      >
        <strong>{item.total_score ?? "—"}</strong>
        <span>综合评分</span>
      </div>
      <div className="analysis-card-footer">
        <span>查看完整分析 →</span>
        {item.original_url ? (
          <a
            href={item.original_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            查看原文
          </a>
        ) : (
          <span className="muted">无原文地址</span>
        )}
      </div>
    </article>
  );
}

export function AnalysesPage() {
  const [effectiveDecision, setEffectiveDecision] =
    useState<AnalysisDecision>("qualified");
  const [minimumScore, setMinimumScore] = useState("");
  const [category, setCategory] = useState("");
  const [subscriptionId, setSubscriptionId] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [sort, setSort] = useState<AnalysisSort>("score");
  const filters = useMemo(
    () => ({
      effectiveDecision,
      minimumScore,
      category,
      subscriptionId,
      from,
      to,
      sort
    }),
    [
      effectiveDecision,
      minimumScore,
      category,
      subscriptionId,
      from,
      to,
      sort
    ]
  );
  const subscriptions = useQuery({
    queryKey: ["subscriptions", "analysis-filter"],
    queryFn: () => api<{items: Subscription[]}>("/subscriptions"),
    retry: false
  });
  const analyses = useInfiniteQuery({
    queryKey: ["analyses", filters],
    queryFn: ({pageParam}) =>
      api<AnalysisPage>(
        queryPath(filters, typeof pageParam === "string" ? pageParam : null)
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    placeholderData: keepPreviousData,
    retry: false
  });
  const items = analyses.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <>
      <PageHeader
        eyebrow="STRUCTURED SIGNAL"
        title="信息流"
        description="用初筛、细筛和确定性评分过滤噪声，只保留值得投入注意力的内容。"
      />
      <section className="analysis-filters" aria-label="信息流筛选">
        <div className="segmented analysis-sort-filter" aria-label="信息流排序">
          <button
            type="button"
            className={sort === "score" ? "active" : ""}
            aria-pressed={sort === "score"}
            onClick={() => setSort("score")}
          >
            评分优先
          </button>
          <button
            type="button"
            className={sort === "time" ? "active" : ""}
            aria-pressed={sort === "time"}
            onClick={() => setSort("time")}
          >
            时间优先
          </button>
        </div>
        <div className="segmented analysis-decision-filter">
          <button
            type="button"
            className={effectiveDecision === "qualified" ? "active" : ""}
            aria-pressed={effectiveDecision === "qualified"}
            onClick={() => setEffectiveDecision("qualified")}
          >
            通过内容
          </button>
          <button
            type="button"
            className={effectiveDecision === "rejected" ? "active" : ""}
            aria-pressed={effectiveDecision === "rejected"}
            onClick={() => setEffectiveDecision("rejected")}
          >
            已拒绝
          </button>
        </div>
        <label>
          最低分数
          <input
            type="number"
            min="0"
            max="100"
            value={minimumScore}
            onChange={(event) => setMinimumScore(event.target.value)}
            placeholder="不限"
          />
        </label>
        <label>
          分类
          <input
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            placeholder="例如：AI"
          />
        </label>
        <label>
          订阅源
          <select
            value={subscriptionId}
            onChange={(event) => setSubscriptionId(event.target.value)}
          >
            <option value="">全部订阅源</option>
            {subscriptions.data?.items.map((subscription) => (
              <option key={subscription.id} value={subscription.id}>
                {subscription.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          开始日期
          <input
            type="date"
            value={from}
            onChange={(event) => setFrom(event.target.value)}
          />
        </label>
        <label>
          结束日期
          <input
            type="date"
            value={to}
            onChange={(event) => setTo(event.target.value)}
          />
        </label>
      </section>

      {subscriptions.error ? (
        <ErrorNotice error={subscriptions.error} />
      ) : null}
      {analyses.error ? <ErrorNotice error={analyses.error} /> : null}
      {analyses.isLoading ? (
        <div className="analysis-loading" aria-live="polite">
          正在整理信息流…
        </div>
      ) : null}
      {!analyses.isLoading && !analyses.error && items.length === 0 ? (
        <Empty>
          当前筛选条件下没有内容。可以降低分数门槛或查看已拒绝内容。
        </Empty>
      ) : null}
      {items.length > 0 ? (
        <section className="analysis-stream" aria-label="结构化分析结果">
          {items.map((item) => (
            <AnalysisCardView key={item.id} item={item} />
          ))}
        </section>
      ) : null}
      {analyses.hasNextPage ? (
        <div className="load-more">
          <button
            type="button"
            className="secondary"
            disabled={analyses.isFetchingNextPage}
            onClick={() => void analyses.fetchNextPage()}
          >
            {analyses.isFetchingNextPage ? "加载中…" : "加载更多"}
          </button>
        </div>
      ) : null}
    </>
  );
}
