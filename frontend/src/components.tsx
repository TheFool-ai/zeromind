import type {PropsWithChildren, ReactNode} from "react";

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
