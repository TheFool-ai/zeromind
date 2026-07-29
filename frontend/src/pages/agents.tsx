import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query";
import {useState, type FormEvent} from "react";

import {api, type Agent, type Provider} from "../api/client";
import {Empty, ErrorNotice, PageHeader, Panel, Status} from "../components";

export function AgentsPage() {
  const queryClient = useQueryClient();
  const [view, setView] = useState<"agents" | "providers">("agents");
  const providers = useQuery({
    queryKey: ["providers"],
    queryFn: () => api<{items: Provider[]}>("/providers"),
    retry: false
  });
  const agents = useQuery({
    queryKey: ["agents"],
    queryFn: () => api<{items: Agent[]}>("/agents"),
    retry: false
  });
  const createProvider = useMutation({
    mutationFn: (value: Record<string, unknown>) =>
      api("/providers", {method: "POST", body: JSON.stringify(value)}),
    onSuccess: () => queryClient.invalidateQueries({queryKey: ["providers"]})
  });

  function submitProvider(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    createProvider.mutate({
      name: data.get("name"),
      provider: data.get("provider"),
      model: data.get("model"),
      api_key_env: data.get("api_key_env"),
      thinking_level: "off",
      parameters: {}
    });
    event.currentTarget.reset();
  }

  return (
    <>
      <PageHeader
        eyebrow="AGENT GATEWAY"
        title="Agent 与 Provider"
        description="Agent 绑定逻辑能力与结构化输入输出；密钥只通过环境变量名引用。"
        action={
          <div className="segmented">
            <button className={view === "agents" ? "active" : ""} onClick={() => setView("agents")}>Agents</button>
            <button className={view === "providers" ? "active" : ""} onClick={() => setView("providers")}>Providers</button>
          </div>
        }
      />
      {view === "providers" ? (
        <div className="split">
          <Panel title="注册 Provider">
            <form className="form-stack" onSubmit={submitProvider}>
              <label>配置名称<input name="name" required placeholder="openai-default" /></label>
              <label>Provider<input name="provider" required placeholder="openai" /></label>
              <label>模型<input name="model" required placeholder="gpt-5-mini" /></label>
              <label>密钥环境变量<input name="api_key_env" required placeholder="OPENAI_API_KEY" /></label>
              <button>保存 Provider</button>
            </form>
          </Panel>
          <Panel title="Provider 配置">
            {providers.error ? <ErrorNotice error={providers.error} /> : null}
            {providers.data?.items.map((item) => (
              <div className="list-row" key={item.id}>
                <div><strong>{item.name}</strong><small>{item.provider} / {item.model}</small></div>
                <code>{item.api_key_env}</code>
              </div>
            ))}
          </Panel>
        </div>
      ) : (
        <Panel title="已注册 Agent">
          {agents.error ? <ErrorNotice error={agents.error} /> : null}
          {!agents.isLoading && !agents.data?.items.length ? (
            <Empty>尚未注册 Agent。先配置 Provider，再通过 API 或此控制台注册分析 Agent。</Empty>
          ) : (
            <div className="card-grid">
              {agents.data?.items.map((item) => (
                <article className="agent-card" key={item.id}>
                  <div className="card-top"><Status value={item.enabled ? "enabled" : "disabled"} /><span>v{item.version}</span></div>
                  <h2>{item.name}</h2>
                  <p>{item.description}</p>
                  <div className="tag-list">{item.capabilities.map((capability) => <span key={capability}>{capability}</span>)}</div>
                </article>
              ))}
            </div>
          )}
        </Panel>
      )}
    </>
  );
}
