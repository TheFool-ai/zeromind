import {useQuery} from "@tanstack/react-query";
import {useState} from "react";

import {api, type WorkflowRun} from "../api/client";
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
              <div className="timeline-item" key={step.id}>
                <span className="timeline-index">{index + 1}</span>
                <div><strong>{step.node_id}</strong><small>尝试 {step.attempts} 次 {step.error ? `· ${step.error}` : ""}</small></div>
                <Status value={step.status} />
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
