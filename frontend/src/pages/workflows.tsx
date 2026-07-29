import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query";
import {useState} from "react";

import {api, type Workflow} from "../api/client";
import {Empty, ErrorNotice, PageHeader, Panel, Status} from "../components";

const EXAMPLE = `name: article-analysis
trigger:
  events: [reference.discovered]
nodes:
  - id: resolve
    type: resolve
    input:
      reference_id: $.trigger.reference_id
output: {}
`;

export function WorkflowsPage() {
  const queryClient = useQueryClient();
  const [source, setSource] = useState("");
  const [validation, setValidation] = useState<string | null>(null);
  const workflows = useQuery({
    queryKey: ["workflows"],
    queryFn: () => api<{items: Workflow[]}>("/workflows"),
    retry: false
  });
  const validate = useMutation({
    mutationFn: () => api<{name: string; topological_order: string[]}>("/workflows/validate", {
      method: "POST",
      body: JSON.stringify({source})
    }),
    onSuccess: (result) => setValidation(`通过：${result.topological_order.join(" → ")}`)
  });
  const create = useMutation({
    mutationFn: () => api<Workflow>("/workflows", {
      method: "POST",
      body: JSON.stringify({source})
    }),
    onSuccess: () => queryClient.invalidateQueries({queryKey: ["workflows"]})
  });
  const activate = useMutation({
    mutationFn: (id: string) => api(`/workflows/${id}/activate`, {method: "POST"}),
    onSuccess: () => queryClient.invalidateQueries({queryKey: ["workflows"]})
  });

  return (
    <>
      <PageHeader
        eyebrow="SAFE AUTOMATION"
        title="工作流"
        description="用受限 YAML 编排解析、Agent、条件和 webhook 节点；不执行任意代码。"
      />
      <div className="workflow-layout">
        <Panel title="YAML 定义" className="editor-panel">
          <label className="sr-only" htmlFor="workflow-source">YAML 定义</label>
          <textarea
            id="workflow-source"
            value={source}
            onChange={(event) => {
              setSource(event.target.value);
              setValidation(null);
            }}
            placeholder={EXAMPLE}
            spellCheck={false}
          />
          <div className="button-row">
            <button className="secondary" disabled={!source || validate.isPending} onClick={() => validate.mutate()}>校验</button>
            <button disabled={!source || create.isPending} onClick={() => create.mutate()}>保存草稿</button>
          </div>
          {validation ? <div className="notice success">{validation}</div> : null}
          {validate.error ? <ErrorNotice error={validate.error} /> : null}
          {create.error ? <ErrorNotice error={create.error} /> : null}
        </Panel>
        <Panel title="工作流版本">
          {workflows.error ? <ErrorNotice error={workflows.error} /> : null}
          {!workflows.isLoading && !workflows.data?.items.length ? (
            <Empty>校验并保存第一个工作流。</Empty>
          ) : workflows.data?.items.map((item) => (
            <div className="list-row workflow-row" key={item.id}>
              <div><strong>{item.name}</strong><small>版本 {item.version}</small></div>
              <div className="row-actions">
                <Status value={item.status} />
                {item.status !== "active" ? <button className="tiny" onClick={() => activate.mutate(item.id)}>激活</button> : null}
              </div>
            </div>
          ))}
        </Panel>
      </div>
    </>
  );
}
