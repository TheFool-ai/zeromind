import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query";
import {useState, type FormEvent} from "react";

import {api, type Agent, type AgentVersion, type Provider} from "../api/client";
import {Empty, ErrorNotice, PageHeader, Panel, Status} from "../components";

export function AgentsPage() {
  const queryClient = useQueryClient();
  const [view, setView] = useState<"agents" | "providers">("agents");
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
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
  const versions = useQuery({
    queryKey: ["agent-versions", selectedAgent?.id],
    queryFn: () => api<{items: AgentVersion[]}>(`/agents/${selectedAgent?.id}/versions`),
    enabled: Boolean(selectedAgent),
    retry: false
  });
  const createProvider = useMutation({
    mutationFn: (value: Record<string, unknown>) =>
      api("/providers", {method: "POST", body: JSON.stringify(value)}),
    onSuccess: () => queryClient.invalidateQueries({queryKey: ["providers"]})
  });
  const createAgent = useMutation({
    mutationFn: (value: Record<string, unknown>) =>
      api("/agents", {method: "POST", body: JSON.stringify(value)}),
    onSuccess: () => queryClient.invalidateQueries({queryKey: ["agents"]})
  });
  const toggleAgent = useMutation({
    mutationFn: (value: {id: string; enabled: boolean}) =>
      api(`/agents/${value.id}/${value.enabled ? "disable" : "enable"}`, {
        method: "POST"
      }),
    onSuccess: () => queryClient.invalidateQueries({queryKey: ["agents"]})
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

  function submitAgent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    createAgent.mutate({
      name: data.get("name"),
      description: data.get("description"),
      capabilities: String(data.get("capabilities"))
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean),
      system_prompt: data.get("system_prompt"),
      provider_profile_id: data.get("provider_profile_id"),
      input_schema: {type: "object"},
      output_schema: {type: "object"}
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
        <>
          <div className="split">
            <Panel title="注册 Agent">
              <form className="form-stack" onSubmit={submitAgent}>
                <label>名称<input name="name" required placeholder="summarizer" /></label>
                <label>说明<input name="description" required placeholder="生成中文结构化摘要" /></label>
                <label>能力（逗号分隔）<input name="capabilities" required placeholder="summarize, zh" /></label>
                <label>
                  Provider
                  <select name="provider_profile_id" required defaultValue="">
                    <option value="" disabled>选择 Provider</option>
                    {providers.data?.items.map((item) => (
                      <option key={item.id} value={item.id}>{item.name} · {item.model}</option>
                    ))}
                  </select>
                </label>
                <label>System prompt<textarea name="system_prompt" required placeholder="只返回符合 JSON Schema 的分析结果。" /></label>
                <button disabled={!providers.data?.items.length}>注册 Agent</button>
                {createAgent.error ? <ErrorNotice error={createAgent.error} /> : null}
              </form>
            </Panel>
            <Panel>
              <Empty>Agent 的输入输出 Schema 默认从宽。需要严格契约时，可通过 API 更新为具体 JSON Schema。</Empty>
            </Panel>
          </div>
          <Panel title="已注册 Agent">
            {agents.error ? <ErrorNotice error={agents.error} /> : null}
            {!agents.isLoading && !agents.data?.items.length ? (
              <Empty>尚未注册 Agent。先配置 Provider，再注册分析 Agent。</Empty>
            ) : (
              <div className="card-grid">
                {agents.data?.items.map((item) => (
                  <article className="agent-card" key={item.id}>
                    <div className="card-top"><Status value={item.enabled ? "enabled" : "disabled"} /><span>v{item.version}</span></div>
                    <h2>{item.name}</h2>
                    <p>{item.description}</p>
                    <div className="tag-list">{item.capabilities.map((capability) => <span key={capability}>{capability}</span>)}</div>
                    <button
                      className="tiny secondary card-action"
                      onClick={() => toggleAgent.mutate({id: item.id, enabled: item.enabled})}
                    >
                      {item.enabled ? "停用 Agent" : "启用 Agent"}
                    </button>
                    <button
                      className="tiny secondary"
                      onClick={() => setSelectedAgent(item)}
                    >
                      查看版本
                    </button>
                  </article>
                ))}
              </div>
            )}
          </Panel>
          {selectedAgent ? (
            <Panel title={`${selectedAgent.name} · 版本历史`}>
              {versions.error ? <ErrorNotice error={versions.error} /> : null}
              {versions.data?.items.map((version) => (
                <details className="version-row" key={version.id}>
                  <summary>
                    <strong>v{version.version}</strong>
                    <small>{version.capabilities.join(" · ")} · {version.created_at}</small>
                  </summary>
                  <h3>System prompt</h3>
                  <pre>{version.system_prompt}</pre>
                  <h3>输出 Schema</h3>
                  <pre>{JSON.stringify(version.output_schema, null, 2)}</pre>
                </details>
              ))}
            </Panel>
          ) : null}
        </>
      )}
    </>
  );
}
