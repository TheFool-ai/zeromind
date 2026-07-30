import {QueryClient, QueryClientProvider} from "@tanstack/react-query";
import {useEffect, useState, type FormEvent} from "react";
import {
  BrowserRouter,
  Navigate,
  NavLink,
  Route,
  Routes
} from "react-router-dom";

import {api, setToken as persistToken, getToken} from "./api/client";
import {AgentsPage} from "./pages/agents";
import {AnalysisDetailPage} from "./pages/analysis-detail";
import {AnalysesPage} from "./pages/analyses";
import {OverviewPage} from "./pages/overview";
import {ReferencesPage} from "./pages/references";
import {RSSHubPage} from "./pages/rsshub";
import {RunsPage} from "./pages/runs";
import {SubscriptionsPage} from "./pages/subscriptions";
import {WebhooksPage} from "./pages/webhooks";
import {WorkflowsPage} from "./pages/workflows";
import "./styles.css";

const navigation = [
  ["/", "总览", "01"],
  ["/subscriptions", "订阅源", "02"],
  ["/rsshub", "RSSHub", "03"],
  ["/references", "内容引用", "04"],
  ["/analyses", "信息流", "05"],
  ["/agents", "智能体", "06"],
  ["/workflows", "工作流", "07"],
  ["/runs", "运行记录", "08"],
  ["/webhooks", "Webhook", "09"]
] as const;

function Login({onLogin}: {onLogin: (token: string) => void}) {
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setPending(true);
    setError(null);
    try {
      const result = await api<{access_token: string}>("/auth/token", {
        method: "POST",
        body: JSON.stringify({
          username: data.get("username"),
          password: data.get("password")
        })
      });
      onLogin(result.access_token);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "登录失败");
    } finally {
      setPending(false);
    }
  }
  return (
    <main className="login">
      <section className="login-card">
        <div className="brand-mark">ZM</div>
        <p className="eyebrow">REFERENCE-FIRST INTELLIGENCE</p>
        <h1>ZeroMind</h1>
        <p>把分散的信息流，收束为可追踪的结构化认知。</p>
        <form onSubmit={submit} className="form-stack">
          <label>用户名<input name="username" autoComplete="username" required /></label>
          <label>密码<input name="password" type="password" autoComplete="current-password" required /></label>
          <button disabled={pending}>{pending ? "验证中…" : "登录"}</button>
          {error ? <div role="alert" className="notice error">{error}</div> : null}
        </form>
      </section>
      <aside className="login-aside">
        <span>RSS → Reference → Resolve → Agent → Result</span>
        <blockquote>“保留来源，而不是复制世界。”</blockquote>
      </aside>
    </main>
  );
}

function Shell({logout}: {logout: () => void}) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><span>ZM</span><strong>ZeroMind</strong></div>
        <nav>
          {navigation.map(([path, label, index]) => (
            <NavLink key={path} to={path} end={path === "/"} aria-label={label}>
              <span>{index}</span>{label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span className="live-dot" /> 系统在线
          <button className="text-button" onClick={logout}>退出</button>
        </div>
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/subscriptions" element={<SubscriptionsPage />} />
          <Route path="/rsshub" element={<RSSHubPage />} />
          <Route path="/references" element={<ReferencesPage />} />
          <Route path="/analyses" element={<AnalysesPage />} />
          <Route
            path="/analyses/:analysisId"
            element={<AnalysisDetailPage />}
          />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/workflows" element={<WorkflowsPage />} />
          <Route path="/runs" element={<RunsPage />} />
          <Route path="/webhooks" element={<WebhooksPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export function App() {
  const [token, setToken] = useState(getToken());
  const [client] = useState(() => new QueryClient({
    defaultOptions: {queries: {staleTime: 15_000, retry: false}}
  }));
  function login(value: string) {
    persistToken(value);
    setToken(value);
  }
  function logout() {
    persistToken(null);
    client.clear();
    setToken(null);
  }
  useEffect(() => {
    const unauthorized = () => {
      client.clear();
      setToken(null);
    };
    window.addEventListener("zeromind:unauthorized", unauthorized);
    return () => window.removeEventListener("zeromind:unauthorized", unauthorized);
  }, [client]);
  return (
    <QueryClientProvider client={client}>
      <BrowserRouter>
        {token ? <Shell logout={logout} /> : <Login onLogin={login} />}
      </BrowserRouter>
    </QueryClientProvider>
  );
}
