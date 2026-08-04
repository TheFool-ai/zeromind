import type {PropsWithChildren, ReactNode} from "react";

import type {
  AnalysisDecision,
  GeneratedAnalysisStatus,
  ReferenceAnalysisStatus
} from "./api/client";

export const referenceStatusLabels: Record<ReferenceAnalysisStatus, string> = {
  pending: "待分析",
  queued: "已排队",
  screening: "元数据初筛",
  resolving: "读取原文",
  analyzing: "核心分析",
  classifying: "分类标注",
  scoring: "质量评分",
  reviewing: "审核反思",
  finalizing: "最终优化",
  initial_rejected: "初筛拒绝",
  fine_rejected: "细筛拒绝",
  completed: "分析完成",
  failed: "分析失败"
};

export type ReferenceStatusGroup =
  | "all" | "pending" | "processing" | "completed" | "rejected" | "failed";

export function referenceStatusGroup(status: ReferenceAnalysisStatus): ReferenceStatusGroup {
  if (status === "pending") return "pending";
  if (status === "completed") return "completed";
  if (status === "initial_rejected" || status === "fine_rejected") return "rejected";
  if (status === "failed") return "failed";
  return "processing";
}

export function ReferenceStatus({value}: {value: ReferenceAnalysisStatus}) {
  const group = referenceStatusGroup(value);
  const tone = group === "completed" ? "good" : group === "failed" ? "bad" : "neutral";
  return <span className={`status ${tone}`}>{referenceStatusLabels[value]}</span>;
}

export const analysisStatusLabels = {
  initial_rejected: "初筛拒绝",
  fine_rejected: "细筛拒绝",
  qualified: "通过",
  rejected: "已拒绝"
} as const satisfies Record<
  GeneratedAnalysisStatus | AnalysisDecision,
  string
>;

export const dimensionLabels: Record<string, string> = {
  relevance: "相关性",
  information_value: "信息价值",
  depth: "深度",
  practicality: "实用性",
  novelty: "新颖性",
  clarity: "清晰度",
  evidence: "证据质量",
  actionability: "可操作性"
};

export function PageHeader({
  eyebrow,
  title,
  description,
  action
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="lede">{description}</p>
      </div>
      {action}
    </header>
  );
}

export function Panel({
  title,
  children,
  className = ""
}: PropsWithChildren<{title?: string; className?: string}>) {
  return (
    <section className={`panel ${className}`}>
      {title ? <h2>{title}</h2> : null}
      {children}
    </section>
  );
}

export function Status({value}: {value: string}) {
  const tone = ["healthy", "active", "completed", "enabled"].includes(value)
    ? "good"
    : ["error", "failed", "exhausted"].includes(value)
      ? "bad"
      : "neutral";
  return <span className={`status ${tone}`}>{value}</span>;
}

export function AnalysisStatus({
  value
}: {
  value: GeneratedAnalysisStatus | AnalysisDecision;
}) {
  const tone = value === "qualified" ? "good" : "bad";
  return (
    <span className={`status ${tone}`}>
      {analysisStatusLabels[value]}
    </span>
  );
}

export function Empty({children}: PropsWithChildren) {
  return <div className="empty">{children}</div>;
}

export function ErrorNotice({error}: {error: unknown}) {
  const message = error instanceof Error ? error.message : "未知错误";
  return <div role="alert" className="notice error">加载失败：{message}</div>;
}

export function formatTime(value: string | null | undefined): string {
  return value
    ? new Intl.DateTimeFormat("zh-CN", {
        dateStyle: "medium",
        timeStyle: "short"
      }).format(new Date(value))
    : "—";
}
