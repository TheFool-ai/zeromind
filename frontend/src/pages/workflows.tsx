import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query";
import {useState} from "react";

import {api, type Workflow} from "../api/client";
import {Empty, ErrorNotice, PageHeader, Panel, Status} from "../components";

type WorkflowValidation = {
  name: string;
  topological_order: string[];
  projection: string | null;
  terminal_gates: string[];
  warnings: string[];
};

const EXAMPLE = `name: valuable-article-analysis
trigger:
  events: [reference.discovered]
projection: content_analysis_v1
nodes:
  - id: reference
    type: reference
    input:
      reference_id: $.trigger.reference_id
      revision: $.trigger.revision
  - id: screen
    type: agent
    agent_id: 00000000-0000-0000-0000-000000000101
    depends_on: [reference]
    input:
      metadata: $.steps.reference
      audience: software-builders
  - id: initial_gate
    type: gate
    depends_on: [screen]
    predicate: {left: $.steps.screen.score, operator: gte, right: 30}
    reject:
      output:
        schema_version: 1
        status: initial_rejected
        reference: $.steps.reference
        screening: $.steps.screen
  - id: resolve
    type: resolve
    depends_on: [initial_gate]
    input:
      reference_id: $.trigger.reference_id
  - id: analyze
    type: agent
    agent_id: 00000000-0000-0000-0000-000000000102
    depends_on: [resolve]
    input:
      metadata: $.steps.reference
      document: $.steps.resolve
      audience: software-builders
  - id: quality_score
    type: score
    depends_on: [analyze]
    input:
      dimensions:
        relevance:
          value: $.steps.analyze.scores.relevance.value
          reason: $.steps.analyze.scores.relevance.reason
          weight: 1.0
  - id: fine_gate
    type: gate
    depends_on: [quality_score]
    predicate: {left: $.steps.quality_score.total, operator: gte, right: 70}
    reject:
      output:
        schema_version: 1
        status: fine_rejected
        reference: $.steps.reference
        screening: $.steps.screen
        content: $.steps.analyze
        score: $.steps.quality_score
output:
  schema_version: 1
  status: qualified
  reference: $.steps.reference
  screening: $.steps.screen
  content: $.steps.analyze
  score: $.steps.quality_score
`;

export function WorkflowsPage() {
  const queryClient = useQueryClient();
  const [source, setSource] = useState("");
  const [validation, setValidation] =
    useState<WorkflowValidation | null>(null);
  const workflows = useQuery({
    queryKey: ["workflows"],
    queryFn: () => api<{items: Workflow[]}>("/workflows"),
    retry: false
  });
  const validate = useMutation({
    mutationFn: () => api<WorkflowValidation>("/workflows/validate", {
      method: "POST",
      body: JSON.stringify({source})
    }),
    onSuccess: setValidation
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
          {validation ? (
            <div className="workflow-validation">
              <div className="notice success">
                <strong>校验通过：{validation.name}</strong>
                <span>
                  执行顺序：{validation.topological_order.join(" → ")}
                </span>
                <span>
                  结果投影：{validation.projection ?? "无"}
                </span>
                <span>
                  终止门禁：
                  {validation.terminal_gates.length
                    ? validation.terminal_gates.join("、")
                    : "无"}
                </span>
              </div>
              {validation.warnings.map((warning) => (
                <div className="notice warning" key={warning}>
                  {warning}
                </div>
              ))}
            </div>
          ) : null}
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
