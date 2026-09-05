import {QueryClient, QueryClientProvider} from "@tanstack/react-query";
import {useState} from "react";
import {
  BrowserRouter,
  Navigate,
  NavLink,
  Route,
  Routes,
  useParams
} from "react-router-dom";

import {AgentsPage} from "./pages/agents";
import {AnalysisDetailPage} from "./pages/analysis-detail";
import {AnalysesPage} from "./pages/analyses";
import {OverviewPage} from "./pages/overview";
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
  ["/analyses", "信息流", "04"],
  ["/agents", "智能体", "05"],
  ["/workflows", "工作流", "06"],
  ["/runs", "运行记录", "07"],
  ["/webhooks", "Webhook", "08"]
] as const;

function LegacyReferenceRedirect() {
  const {referenceId} = useParams<{referenceId: string}>();
  return (
    <Navigate
      to={referenceId ? `/runs?reference=${encodeURIComponent(referenceId)}` : "/runs"}
      replace
    />
  );
}

function Shell() {
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
        </div>
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/subscriptions" element={<SubscriptionsPage />} />
          <Route path="/rsshub" element={<RSSHubPage />} />
          <Route path="/references" element={<Navigate to="/runs" replace />} />
          <Route path="/references/:referenceId" element={<LegacyReferenceRedirect />} />
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
  const [client] = useState(() => new QueryClient({
    defaultOptions: {queries: {staleTime: 15_000, retry: false}}
  }));
  return (
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <Shell />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
