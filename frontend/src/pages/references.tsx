import {useQuery} from "@tanstack/react-query";

import {api, type Reference} from "../api/client";
import {Empty, ErrorNotice, formatTime, PageHeader, Panel} from "../components";

export function ReferencesPage() {
  const references = useQuery({
    queryKey: ["references"],
    queryFn: () => api<{items: Reference[]}>("/references"),
    retry: false
  });
  return (
    <>
      <PageHeader
        eyebrow="REFERENCE INDEX"
        title="内容引用"
        description="这里只保存原文地址与 RSS 元数据修订；文章正文在工作流运行时即时读取。"
      />
      <Panel>
        {references.error ? <ErrorNotice error={references.error} /> : null}
        {!references.isLoading && !references.data?.items.length ? (
          <Empty>尚未发现内容。下一次 Feed 抓取后，引用会显示在这里。</Empty>
        ) : (
          <div className="reference-grid">
            {references.data?.items.map((item) => (
              <article className="reference-card" key={item.id}>
                <div className="reference-meta">
                  <span>REV {item.current_revision}</span>
                  <time>{formatTime(item.published_at)}</time>
                </div>
                <h2>{item.original_url ? new URL(item.original_url).hostname : "无原文地址"}</h2>
                {item.original_url ? <a href={item.original_url} target="_blank" rel="noreferrer">{item.original_url}</a> : null}
                <code>{item.id}</code>
              </article>
            ))}
          </div>
        )}
      </Panel>
    </>
  );
}
