import type {PropsWithChildren, ReactNode} from "react";

import type {
  AnalysisDecision,
  GeneratedAnalysisStatus
} from "./api/client";

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
