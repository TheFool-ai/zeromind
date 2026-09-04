import {useQuery} from "@tanstack/react-query";

import {api} from "../api/client";
import {ErrorNotice, PageHeader, Panel, Status} from "../components";

type Ready = {
  status: string;
  dependencies: Record<string, string>;
};

export function OverviewPage() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => fetch("/health/ready").then(async (response) => {
      const body = await response.json() as Ready;
      if (!response.ok) return body;
      return body;
    }),
    retry: false
  });
  const subscriptions = useQuery({
    queryKey: ["subscriptions", "count"],
    queryFn: () => api<{items: unknown[]}>("/subscriptions"),
    retry: false
  });
  const runs = useQuery({
    queryKey: ["runs", "count"],
    queryFn: () => api<{items: unknown[]}>("/workflow-runs"),
    retry: false
  });

  return (
    <>
      <PageHeader
        eyebrow="SYSTEM PULSE"
        title="信息收集总览"
        description="从订阅发现到 Agent 分析，关注每一段链路的当前状态。"
      />
      {health.error ? <ErrorNotice error={health.error} /> : null}
      <div className="metric-grid">
        <Panel>
          <span className="metric-label">订阅源</span>
          <strong className="metric">{subscriptions.data?.items?.length ?? "—"}</strong>
          <small>每 30 分钟轮询</small>
        </Panel>
        <Panel>
          <span className="metric-label">工作流运行</span>
          <strong className="metric">{runs.data?.items?.length ?? "—"}</strong>
          <small>持久化结构化结果</small>
        </Panel>
        <Panel>
          <span className="metric-label">系统就绪</span>
          <strong className="metric compact">
            <Status value={health.data?.status ?? "checking"} />
          </strong>
          <small>API / DB / Redis / Pi</small>
        </Panel>
      </div>
      <Panel title="依赖状态">
        <div className="dependency-list">
          {Object.entries(health.data?.dependencies ?? {}).map(([name, value]) => (
            <div key={name}>
              <span>{name}</span>
              <Status value={value} />
            </div>
          ))}
        </div>
      </Panel>
    </>
  );
}
