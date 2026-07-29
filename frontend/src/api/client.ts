const TOKEN_KEY = "zeromind_token";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string
  ) {
    super(message);
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

async function decode<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({})) as {
    detail?: {code?: string; message?: string} | string;
  };
  if (!response.ok) {
    const detail = body.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail?.message ?? detail?.code ?? `请求失败（${response.status}）`;
    const code = typeof detail === "object" ? detail?.code : undefined;
    throw new ApiError(message, response.status, code);
  }
  return body as T;
}

export async function api<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("content-type", "application/json");
  }
  const response = await fetch(`/api/v1${path}`, {...init, headers});
  if (response.status === 401 && path !== "/auth/token") {
    setToken(null);
    window.dispatchEvent(new Event("zeromind:unauthorized"));
  }
  return decode<T>(response);
}

export async function upload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  return api<T>(path, {method: "POST", body: form});
}

export type Subscription = {
  id: string;
  title: string;
  feed_url: string;
  site_url: string | null;
  categories: string[];
  enabled: boolean;
  health: string;
  next_poll_at: string;
  last_checked_at: string | null;
  consecutive_failures: number;
};

export type Reference = {
  id: string;
  subscription_id: string;
  original_url: string | null;
  current_revision: number;
  first_seen_at: string;
  last_seen_at: string;
};

export type Provider = {
  id: string;
  name: string;
  provider: string;
  model: string;
  api_key_env: string;
  enabled: boolean;
};

export type Agent = {
  id: string;
  name: string;
  description: string;
  capabilities: string[];
  provider_profile_id: string;
  enabled: boolean;
  version: number;
};

export type Workflow = {
  id: string;
  name: string;
  version: number;
  status: string;
  updated_at: string;
};

export type WorkflowRun = {
  id: string;
  definition_id: string;
  status: string;
  output: Record<string, unknown> | null;
  error: string | null;
  started_at: string;
  completed_at: string | null;
  steps: Array<{
    id: string;
    node_id: string;
    status: string;
    attempts: number;
    error: string | null;
  }>;
};

export type Webhook = {
  id: string;
  name: string;
  url: string;
  secret_env: string;
  events: string[];
  enabled: boolean;
  max_attempts: number;
};
