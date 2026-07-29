import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query";
import {useState, type FormEvent} from "react";

import {api, upload, type Subscription} from "../api/client";
import {
  Empty,
  ErrorNotice,
  formatTime,
  PageHeader,
  Panel,
  Status
} from "../components";

type OpmlPreview = {
  title: string | null;
  entries: Array<{title: string; feed_url: string}>;
  invalid_entries: Array<{feed_url: string; reason: string}>;
  duplicate_count: number;
};

export function SubscriptionsPage() {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<OpmlPreview | null>(null);
  const subscriptions = useQuery({
    queryKey: ["subscriptions"],
    queryFn: () => api<{items: Subscription[]}>("/subscriptions"),
    retry: false
  });
  const create = useMutation({
    mutationFn: (data: {title: string; feed_url: string}) =>
      api<Subscription>("/subscriptions", {
        method: "POST",
        body: JSON.stringify(data)
      }),
    onSuccess: () => queryClient.invalidateQueries({queryKey: ["subscriptions"]})
  });
  const previewMutation = useMutation({
    mutationFn: (value: File) => upload<OpmlPreview>("/subscriptions/opml/preview", value),
    onSuccess: setPreview
  });
  const importMutation = useMutation({
    mutationFn: (value: File) => upload("/subscriptions/opml/import", value),
    onSuccess: () => {
      setPreview(null);
      queryClient.invalidateQueries({queryKey: ["subscriptions"]});
    }
  });
  const toggle = useMutation({
    mutationFn: (value: {id: string; enabled: boolean}) =>
      api(`/subscriptions/${value.id}/${value.enabled ? "disable" : "enable"}`, {
        method: "POST"
      }),
    onSuccess: () => queryClient.invalidateQueries({queryKey: ["subscriptions"]})
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    create.mutate({
      title: String(data.get("title")),
      feed_url: String(data.get("feed_url"))
    });
    event.currentTarget.reset();
  }

  return (
    <>
      <PageHeader
        eyebrow="SOURCES"
        title="RSS 订阅源"
        description="逐条添加，或先预览再批量导入 OPML。抓取状态与失败次数会在这里汇总。"
      />
      <div className="split">
        <Panel title="添加订阅">
          <form onSubmit={submit} className="form-stack">
            <label>名称<input name="title" required placeholder="技术雷达" /></label>
            <label>Feed URL<input name="feed_url" type="url" required placeholder="https://example.com/rss" /></label>
            <button disabled={create.isPending}>添加订阅</button>
            {create.error ? <ErrorNotice error={create.error} /> : null}
          </form>
        </Panel>
        <Panel title="导入 OPML">
          <div className="form-stack">
            <label>
              选择 OPML 文件
              <input
                type="file"
                accept=".opml,.xml,text/xml"
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null);
                  setPreview(null);
                }}
              />
            </label>
            <div className="button-row">
              <button
                className="secondary"
                disabled={!file || previewMutation.isPending}
                onClick={() => file && previewMutation.mutate(file)}
              >
                预览 OPML
              </button>
              <button
                disabled={!file || !preview || importMutation.isPending}
                onClick={() => file && importMutation.mutate(file)}
              >
                确认导入
              </button>
            </div>
            {previewMutation.error ? <ErrorNotice error={previewMutation.error} /> : null}
            {preview ? (
              <div className="preview-list">
                <small>{preview.entries.length} 个有效条目 · {preview.invalid_entries.length} 个无效条目</small>
                {preview.entries.map((entry) => (
                  <div key={entry.feed_url}>
                    <strong>{entry.title}</strong>
                    <code>{entry.feed_url}</code>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </Panel>
      </div>
      <Panel title="当前订阅">
        {subscriptions.error ? <ErrorNotice error={subscriptions.error} /> : null}
        {!subscriptions.isLoading && !subscriptions.data?.items.length ? (
          <Empty>还没有订阅源。添加第一条 RSS，信息流就会从这里开始。</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>名称</th><th>Feed</th><th>健康</th><th>下次轮询</th><th>失败</th><th>操作</th></tr></thead>
              <tbody>
                {subscriptions.data?.items.map((item) => (
                  <tr key={item.id}>
                    <td><strong>{item.title}</strong></td>
                    <td><a href={item.feed_url} target="_blank" rel="noreferrer">{item.feed_url}</a></td>
                    <td><Status value={item.health} /></td>
                    <td>{formatTime(item.next_poll_at)}</td>
                    <td>{item.consecutive_failures}</td>
                    <td>
                      <button
                        className="tiny secondary"
                        onClick={() => toggle.mutate({id: item.id, enabled: item.enabled})}
                      >
                        {item.enabled ? "停用" : "启用"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
