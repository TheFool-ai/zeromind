import {useQuery} from "@tanstack/react-query";
import {useState} from "react";

import {api, type AgentSession, type WorkflowRun} from "../api/client";
import {Empty, ErrorNotice, formatTime, PageHeader, Panel, Status} from "../components";

export function RunsPage() {
  const [selected, setSelected] = useState<string | null>(null);
  const runs = useQuery({
    queryKey: ["workflow-runs"],
    queryFn: () => api<{items: WorkflowRun[]}>("/workflow-runs"),
    refetchInterval: 10_000,
    retry: false
  });
  const current = runs.data?.items.find((item) => item.id === selected) ?? runs.data?.items[0];
  const sessions = useQuery({
    queryKey: ["agent-sessions", current?.id],
    queryFn: () => api<{items: AgentSession[]}>(`/agent-sessions?workflow_run_id=${current?.id}`),
    enabled: Boolean(current),
    refetchInterval: 10_000,
    retry: false
  });

  return (
    <>
      <PageHeader
        eyebrow="EXECUTION LEDGER"
        title="运行记录"
        description="查看 DAG 节点时间线、重试次数和最终结构化结果。正文不会进入记录。"
      />
      {runs.error ? <ErrorNotice error={runs.error} /> : null}
      {!runs.isLoading && !runs.data?.items.length ? (
        <Panel><Empty>还没有工作流运行。</Empty></Panel>
      ) : (
        <div className="run-layout">
          <Panel title="最近运行">
            {runs.data?.items.map((run) => (
              <button className={`run-select ${current?.id === run.id ? "active" : ""}`} key={run.id} onClick={() => setSelected(run.id)}>
                <span><strong>{run.id.slice(0, 8)}</strong><small>{formatTime(run.started_at)}</small></span>
                <Status value={run.status} />
              </button>
            ))}
          </Panel>
          <Panel title="节点时间线">
            {current?.steps.map((step, index) => (
              <div className="timeline-group" key={step.id}>
                <div className="timeline-item">
                  <span className="timeline-index">{index + 1}</span>
                  <div><strong>{step.node_id}</strong><small>尝试 {step.attempts} 次 {step.error ? `· ${step.error}` : ""}</small></div>
                  <Status value={step.status} />
                </div>
                {sessions.data?.items
                  .filter((session) => session.step_run_id === step.id)
                  .map((session) => (
                    <details className="session-row" key={session.id}>
                      <summary>
                        Agent · {session.provider}/{session.model} · 尝试 {session.attempt}
                        <Status value={session.status} />
                      </summary>
                      <small>Agent {session.agent_id} · 版本 {session.agent_version_id}</small>
                      {session.error_message ? <p>{session.error_code}: {session.error_message}</p> : null}
                      <pre>{JSON.stringify(session.output ?? session.sanitized_input, null, 2)}</pre>
                    </details>
                  ))}
              </div>
            ))}
            <h3>结构化结果</h3>
            <pre>{JSON.stringify(current?.output ?? {}, null, 2)}</pre>
          </Panel>
        </div>
      )}
    </>
  );
}
