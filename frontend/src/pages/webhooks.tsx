import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query";
import type {FormEvent} from "react";

import {api, type Webhook} from "../api/client";
import {Empty, ErrorNotice, PageHeader, Panel, Status} from "../components";

export function WebhooksPage() {
  const queryClient = useQueryClient();
  const webhooks = useQuery({
    queryKey: ["webhooks"],
    queryFn: () => api<{items: Webhook[]}>("/webhooks"),
    retry: false
  });
  const create = useMutation({
    mutationFn: (value: Record<string, unknown>) =>
      api("/webhooks", {method: "POST", body: JSON.stringify(value)}),
    onSuccess: () => queryClient.invalidateQueries({queryKey: ["webhooks"]})
  });
  const disable = useMutation({
    mutationFn: (id: string) => api(`/webhooks/${id}/disable`, {method: "POST"}),
    onSuccess: () => queryClient.invalidateQueries({queryKey: ["webhooks"]})
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    create.mutate({
      name: data.get("name"),
      url: data.get("url"),
      secret_env: data.get("secret_env"),
      events: ["workflow.completed"],
      max_attempts: 3
    });
    event.currentTarget.reset();
  }
  return (
    <>
      <PageHeader
        eyebrow="DELIVERY"
        title="Webhook"
        description="将结构化分析结果签名投递到外部系统，目标地址会经过 SSRF 策略检查。"
      />
      <div className="split">
        <Panel title="添加终点">
          <form className="form-stack" onSubmit={submit}>
            <label>名称<input name="name" required placeholder="knowledge-base" /></label>
            <label>HTTPS URL<input name="url" required type="url" placeholder="https://hooks.example/events" /></label>
            <label>签名密钥环境变量<input name="secret_env" required placeholder="WEBHOOK_SECRET" /></label>
            <button>保存 Webhook</button>
            {create.error ? <ErrorNotice error={create.error} /> : null}
          </form>
        </Panel>
        <Panel title="投递终点">
          {webhooks.error ? <ErrorNotice error={webhooks.error} /> : null}
          {!webhooks.isLoading && !webhooks.data?.items.length ? (
            <Empty>尚未配置 webhook。</Empty>
          ) : webhooks.data?.items.map((item) => (
            <div className="list-row" key={item.id}>
              <div><strong>{item.name}</strong><small>{item.url}</small><code>{item.secret_env}</code></div>
              <div className="row-actions">
                <Status value={item.enabled ? "enabled" : "disabled"} />
                {item.enabled ? <button className="tiny secondary" onClick={() => disable.mutate(item.id)}>停用</button> : null}
              </div>
            </div>
          ))}
        </Panel>
      </div>
    </>
  );
}
