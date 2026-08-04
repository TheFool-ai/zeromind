import {render, screen, waitFor, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./app";

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {"content-type": "application/json"}
  });
}

const analysisCard = {
  id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  reference_id: "11111111-1111-1111-1111-111111111111",
  subscription_id: "22222222-2222-2222-2222-222222222222",
  source_name: "Example Engineering",
  source_feed_url: "https://example.com/feed",
  title: "A useful article",
  original_url: "https://example.com/article",
  author: "Ada",
  published_at: "2026-07-30T00:00:00Z",
  observed_at: "2026-07-31T05:00:00Z",
  generated_status: "qualified",
  effective_decision: "qualified",
  primary_category: "AI",
  tags: ["agents", "workflows"],
  one_sentence_summary: "一篇可落地的 Agent 工作流指南。",
  total_score: 86,
  recommendation_level: "recommended",
  recommendation_reason: "信息密度高",
  overridden: true
} as const;

const analysisDetail = {
  ...analysisCard,
  reference_revision: 3,
  workflow_definition_id: "33333333-3333-3333-3333-333333333333",
  workflow_definition_version: 2,
  workflow_run_id: "44444444-4444-4444-4444-444444444444",
  screening: {
    score: 85,
    reason: "主题相关且包含实质性技术内容。",
    summary: "元数据初筛通过。"
  },
  secondary_categories: ["Engineering"],
  summary: "文章解释了如何组合 Agent、确定性门禁和结构化输出。",
  viewpoints: [
    {
      statement: "确定性门禁让筛选结果更可解释。",
      explanation: "阈值可以被观察、复核和测试。"
    },
    {
      statement: "模型判断与业务政策应分离。",
      explanation: "Agent 负责理解，DSL 负责稳定执行决策。"
    }
  ],
  key_quotes: [
    {
      text: "让模型负责判断，让规则负责边界。",
      context: "作者讨论评分策略时"
    }
  ],
  dimensions: [
    {name: "relevance", value: 92, weight: 0.2, reason: "高度相关"},
    {name: "depth", value: 90, weight: 0.2, reason: "论证深入"},
    {name: "novelty", value: 78, weight: 0.15, reason: "有新视角"},
    {name: "clarity", value: 88, weight: 0.15, reason: "结构清晰"},
    {name: "evidence", value: 82, weight: 0.15, reason: "证据充分"},
    {name: "actionability", value: 84, weight: 0.15, reason: "可直接实践"}
  ],
  provenance: {
    screening: {
      agent_id: "55555555-5555-5555-5555-555555555555",
      agent_version: 1,
      provider: "openai",
      model: "gpt-5-mini",
      usage: {}
    },
    analysis: {
      agent_id: "66666666-6666-6666-6666-666666666666",
      agent_version: 2,
      provider: "openai",
      model: "gpt-5",
      usage: {}
    }
  },
  overrides: [
    {
      id: "77777777-7777-7777-7777-777777777777",
      sequence: 1,
      decision: "qualified",
      reason: "人工复核确认内容具有长期参考价值。",
      actor_subject: "reviewer",
      created_at: "2026-07-31T06:00:00Z"
    }
  ],
  notes: [],
  created_at: "2026-07-31T05:00:00Z"
} as const;

const referenceDetail = {
  id: analysisCard.reference_id,
  subscription_id: analysisCard.subscription_id,
  identity_key: "guid:reading-detail",
  original_url: analysisCard.original_url,
  current_revision: 3,
  first_seen_at: "2026-07-30T00:00:00Z",
  last_seen_at: "2026-07-31T00:00:00Z",
  analysis_status: "completed",
  analysis_status_revision: 3,
  analysis_workflow_run_id: analysisDetail.workflow_run_id,
  analysis_error_code: null,
  analysis_error_message: null,
  analysis_status_updated_at: "2026-07-31T05:00:00Z",
  analysis_started_at: "2026-07-31T04:00:00Z",
  analysis_completed_at: "2026-07-31T05:00:00Z",
  revision: {
    id: "88888888-8888-8888-8888-888888888888",
    number: 3,
    fingerprint: "fingerprint",
    url: analysisCard.original_url,
    title: analysisCard.title,
    summary: '<p>RSS <strong>元数据摘要</strong></p><img src="preview.jpg">',
    author: analysisCard.author,
    published_at: analysisCard.published_at,
    updated_at: null,
    observed_at: analysisCard.observed_at
  },
  source_name: analysisCard.source_name,
  source_feed_url: analysisCard.source_feed_url,
  source_site_url: "https://example.com",
  iframe_url: analysisCard.original_url,
  analysis: analysisDetail
} as const;

describe("ZeroMind administration", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/");
  });

  it("authenticates then renders the management navigation", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      response({access_token: "token", token_type: "bearer"})
    );
    render(<App />);

    await userEvent.type(screen.getByLabelText("用户名"), "admin");
    await userEvent.type(screen.getByLabelText("密码"), "secret");
    await userEvent.click(screen.getByRole("button", {name: "登录"}));

    expect(await screen.findByRole("link", {name: "订阅源"})).toBeVisible();
    expect(screen.getByRole("link", {name: "工作流"})).toBeVisible();
    expect(localStorage.getItem("zeromind_token")).toBe("token");
  });

  it("shows subscription list errors without losing navigation", async () => {
    localStorage.setItem("zeromind_token", "token");
    window.history.replaceState({}, "", "/subscriptions");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      response({detail: {code: "database_unavailable"}}, 503)
    );
    render(<App />);

    expect(await screen.findByRole("alert")).toHaveTextContent("加载失败");
    expect(screen.getByRole("link", {name: "订阅源"})).toBeVisible();
  });

  it("previews an OPML file before importing it", async () => {
    localStorage.setItem("zeromind_token", "token");
    window.history.replaceState({}, "", "/subscriptions");
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(response({items: []}))
      .mockResolvedValueOnce(
        response({
          title: "Reading",
          entries: [
            {
              title: "Example",
              feed_url: "https://example.com/rss",
              site_url: null,
              categories: []
            }
          ],
          invalid_entries: [],
          duplicate_count: 0
        })
      );
    render(<App />);

    const file = new File(["<opml/>"], "feeds.opml", {type: "text/xml"});
    await userEvent.upload(await screen.findByLabelText("选择 OPML 文件"), file);
    await userEvent.click(screen.getByRole("button", {name: "预览 OPML"}));

    expect(await screen.findByText("https://example.com/rss")).toBeVisible();
    expect(screen.getByRole("button", {name: "确认导入"})).toBeEnabled();
  });

  it("submits an RSSHub locator without browser URL rejection", async () => {
    localStorage.setItem("zeromind_token", "token");
    window.history.replaceState({}, "", "/subscriptions");
    let submitted: Record<string, string> | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      if (init?.method === "POST") {
        submitted = JSON.parse(String(init.body)) as Record<string, string>;
        return response({
          id: "feed-1",
          title: submitted.title,
          feed_url: submitted.feed_url,
          site_url: null,
          categories: [],
          enabled: true,
          health: "healthy",
          next_poll_at: "2026-07-30T00:00:00Z",
          last_checked_at: null,
          consecutive_failures: 0
        }, 201);
      }
      return response({items: []});
    });
    render(<App />);

    await userEvent.type(await screen.findByLabelText("名称"), "Vista8");
    await userEvent.type(
      screen.getByLabelText("Feed URL"),
      "rsshub://twitter/user/vista8"
    );
    expect(
      screen.getByText("支持 https://… 和 rsshub://… 地址")
    ).toBeVisible();
    await userEvent.click(screen.getByRole("button", {name: "添加订阅"}));

    expect(submitted).toEqual({
      title: "Vista8",
      feed_url: "rsshub://twitter/user/vista8"
    });
  });

  it("registers an RSSHub instance without echoing its access key", async () => {
    localStorage.setItem("zeromind_token", "token");
    window.history.replaceState({}, "", "/rsshub");
    let submitted: Record<string, unknown> | undefined;
    let instances: unknown[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      if (init?.method === "POST") {
        submitted = JSON.parse(String(init.body)) as Record<string, unknown>;
        const created = {
          id: "rsshub-1",
          name: submitted.name,
          base_url: submitted.base_url,
          authentication_mode: submitted.authentication_mode,
          enabled: true,
          active: true,
          has_access_key: true,
          created_at: "2026-07-30T00:00:00Z",
          updated_at: "2026-07-30T00:00:00Z"
        };
        instances = [created];
        return response(created, 201);
      }
      return response({items: instances});
    });
    render(<App />);

    await userEvent.type(await screen.findByLabelText("实例名称"), "Primary");
    await userEvent.type(
      screen.getByLabelText("Base URL"),
      "https://rsshub.example.com"
    );
    await userEvent.type(
      screen.getByLabelText("Access Key（可选）"),
      "instance-secret"
    );
    await userEvent.click(screen.getByRole("button", {name: "添加实例"}));

    expect(submitted).toEqual({
      name: "Primary",
      base_url: "https://rsshub.example.com",
      access_key: "instance-secret",
      authentication_mode: "key",
      enabled: true
    });
    expect(await screen.findByText("已配置密钥")).toBeVisible();
    expect(screen.queryByDisplayValue("instance-secret")).not.toBeInTheDocument();
  });

  it("activates a configured RSSHub instance", async () => {
    localStorage.setItem("zeromind_token", "token");
    window.history.replaceState({}, "", "/rsshub");
    let instances = [
      {
        id: "primary",
        name: "Primary",
        base_url: "https://rsshub.example.com",
        authentication_mode: "key",
        enabled: true,
        active: true,
        has_access_key: false,
        created_at: "2026-07-30T00:00:00Z",
        updated_at: "2026-07-30T00:00:00Z"
      },
      {
        id: "backup",
        name: "Backup",
        base_url: "https://backup.example.com",
        authentication_mode: "key",
        enabled: true,
        active: false,
        has_access_key: false,
        created_at: "2026-07-30T00:00:00Z",
        updated_at: "2026-07-30T00:00:00Z"
      }
    ];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith("/rsshub/instances/backup/activate")) {
        instances = instances.map((instance) => ({
          ...instance,
          active: instance.id === "backup"
        }));
        return response(instances[1]);
      }
      if (init?.method === "DELETE") return response({}, 204);
      return response({items: instances});
    });
    render(<App />);

    await userEvent.click(
      await screen.findByRole("button", {name: "设为活动实例 Backup"})
    );

    const backupRow = await screen.findByRole("row", {name: /Backup/});
    expect(within(backupRow).getByText("活动")).toBeVisible();
  });

  it("can explicitly clear a saved RSSHub access key while editing", async () => {
    localStorage.setItem("zeromind_token", "token");
    window.history.replaceState({}, "", "/rsshub");
    const instance = {
      id: "primary",
      name: "Primary",
      base_url: "https://rsshub.example.com",
      authentication_mode: "key",
      enabled: true,
      active: true,
      has_access_key: true,
      created_at: "2026-07-30T00:00:00Z",
      updated_at: "2026-07-30T00:00:00Z"
    };
    let submitted: Record<string, unknown> | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      if (init?.method === "PUT") {
        submitted = JSON.parse(String(init.body)) as Record<string, unknown>;
        return response({...instance, has_access_key: false});
      }
      return response({items: [instance]});
    });
    render(<App />);

    await userEvent.click(
      await screen.findByRole("button", {name: "编辑 Primary"})
    );
    await userEvent.click(screen.getByLabelText("清除已保存的 Access Key"));
    await userEvent.click(screen.getByRole("button", {name: "保存实例"}));

    expect(submitted).toMatchObject({access_key: null});
  });

  it("shows registered agent configuration history", async () => {
    localStorage.setItem("zeromind_token", "token");
    window.history.replaceState({}, "", "/agents");
    const agent = {
      id: "33333333-3333-3333-3333-333333333333",
      name: "文章核心分析",
      description: "提取核心洞察",
      capabilities: ["extract-content-insights"],
      provider_profile_id: "11111111-1111-1111-1111-111111111111",
      enabled: true,
      version: 2,
      version_id: "44444444-4444-4444-4444-444444444444"
    };
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith(`/agents/${agent.id}/versions`)) {
        return response({
          items: [{
            ...agent,
            agent_id: agent.id,
            system_prompt: "只依据正文提取事实。",
            input_schema: {type: "object"},
            output_schema: {type: "object"},
            created_at: "2026-08-03T00:00:00Z"
          }]
        });
      }
      if (url.endsWith("/providers")) return response({items: []});
      return response({items: [agent]});
    });
    render(<App />);

    await userEvent.click(await screen.findByRole("button", {name: "查看版本"}));
    await userEvent.click((await screen.findAllByText("v2"))[1]);

    expect(await screen.findByText("只依据正文提取事实。")).toBeVisible();
    expect(screen.getByText("文章核心分析 · 版本历史")).toBeVisible();
  });

  it("renders workflow validation errors returned by the API", async () => {
    localStorage.setItem("zeromind_token", "token");
    window.history.replaceState({}, "", "/workflows");
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(response({items: []}))
      .mockResolvedValueOnce(
        response(
          {detail: {code: "invalid_workflow", message: "graph contains a cycle"}},
          422
        )
      );
    render(<App />);

    await userEvent.type(await screen.findByLabelText("YAML 定义"), "name: cyclic");
    await userEvent.click(screen.getByRole("button", {name: "校验"}));

    expect(await screen.findByRole("alert")).toHaveTextContent("graph contains a cycle");
  });

  it("shows workflow projection, terminal gates, and validation warnings", async () => {
    localStorage.setItem("zeromind_token", "token");
    window.history.replaceState({}, "", "/workflows");
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(response({items: []}))
      .mockResolvedValueOnce(
        response({
          name: "valuable-article-analysis",
          topological_order: [
            "reference",
            "screen",
            "initial_gate",
            "resolve",
            "analyze",
            "quality_score",
            "fine_gate"
          ],
          projection: "content_analysis_v1",
          terminal_gates: ["initial_gate", "fine_gate"],
          warnings: ["请确认两个 Agent 的输出 Schema 与投影契约一致。"]
        })
      );
    render(<App />);

    await userEvent.type(
      await screen.findByLabelText("YAML 定义"),
      "name: valuable-article-analysis"
    );
    await userEvent.click(screen.getByRole("button", {name: "校验"}));

    expect(await screen.findByText(/content_analysis_v1/)).toBeVisible();
    expect(screen.getByText(/终止门禁.*initial_gate.*fine_gate/)).toBeVisible();
    expect(
      screen.getByText("请确认两个 Agent 的输出 Schema 与投影契约一致。")
    ).toBeVisible();
  });

  it("returns to login when the administrator token expires", async () => {
    localStorage.setItem("zeromind_token", "expired");
    window.history.replaceState({}, "", "/references");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      response({detail: {code: "authentication_required"}}, 401)
    );

    render(<App />);

    expect(await screen.findByRole("button", {name: "登录"})).toBeVisible();
    expect(localStorage.getItem("zeromind_token")).toBeNull();
  });

  it("shows publication time for content references", async () => {
    localStorage.setItem("zeromind_token", "token");
    window.history.replaceState({}, "", "/references");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      response({
        items: [
          {
            id: "11111111-1111-1111-1111-111111111111",
            subscription_id: "22222222-2222-2222-2222-222222222222",
            identity_key: "guid:42",
            original_url: "https://example.com/post",
            current_revision: 1,
            published_at: "2026-07-29T00:00:00Z",
            first_seen_at: "2030-01-01T00:00:00Z",
            last_seen_at: "2030-01-01T00:00:00Z"
          }
        ]
      })
    );

    render(<App />);

    expect(await screen.findByText(/2026年7月29日/)).toBeVisible();
    expect(screen.queryByText(/2030年1月1日/)).not.toBeInTheDocument();
  });

  it("shows lifecycle labels, analysis preview, failure and retry controls", async () => {
    localStorage.setItem("zeromind_token", "token");
    window.history.replaceState({}, "", "/references");
    const base = {
      subscription_id: analysisCard.subscription_id,
      identity_key: "guid:item",
      original_url: analysisCard.original_url,
      current_revision: 1,
      published_at: analysisCard.published_at,
      first_seen_at: analysisCard.observed_at,
      last_seen_at: analysisCard.observed_at,
      analysis_status_revision: 1,
      analysis_workflow_run_id: null,
      analysis_error_code: null,
      analysis_error_message: null,
      analysis_status_updated_at: analysisCard.observed_at,
      analysis_started_at: null,
      analysis_completed_at: null,
      summary: '<p>RSS <strong>summary</strong></p><img src="preview.jpg">',
      author: "Ada",
      source_name: "Example Engineering",
      source_feed_url: analysisCard.source_feed_url,
      analysis: null
    };
    const items = [
      {...base, id: "10000000-0000-0000-0000-000000000001", title: "Pending title", analysis_status: "pending"},
      {...base, id: "10000000-0000-0000-0000-000000000002", title: "Analyzing title", analysis_status: "analyzing"},
      {...base, id: "10000000-0000-0000-0000-000000000003", title: "Completed title", analysis_status: "completed", analysis: analysisCard},
      {...base, id: "10000000-0000-0000-0000-000000000004", title: "Rejected title", analysis_status: "fine_rejected"},
      {...base, id: "10000000-0000-0000-0000-000000000005", title: "Failed title", analysis_status: "failed", analysis_error_message: "Provider unavailable"}
    ];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) =>
      init?.method === "POST"
        ? response({analysis_status: "pending"}, 202)
        : response({items})
    );

    render(<App />);

    expect(await screen.findByText("Pending title")).toBeVisible();
    expect(screen.getAllByText("RSS summary")).toHaveLength(4);
    expect(screen.queryByText(/<strong>/)).not.toBeInTheDocument();
    expect(screen.getByText("核心分析")).toBeVisible();
    expect(screen.getByText("分析完成")).toBeVisible();
    expect(screen.getByText("细筛拒绝")).toBeVisible();
    expect(screen.getByText("分析失败")).toBeVisible();
    expect(screen.getByText("Provider unavailable")).toBeVisible();
    expect(screen.getByLabelText("质量评分 86")).toBeVisible();
    expect(screen.getByRole("link", {name: /Completed title/})).toHaveAttribute(
      "href",
      "/references/10000000-0000-0000-0000-000000000003"
    );
    await userEvent.click(screen.getByRole("button", {name: "重新分析"}));
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/reanalyze"),
      expect.objectContaining({method: "POST"})
    ));
  });

  it("renders the original and complete structured analysis side by side", async () => {
    localStorage.setItem("zeromind_token", "token");
    window.history.replaceState({}, "", `/references/${analysisCard.reference_id}`);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response(referenceDetail));

    render(<App />);

    expect(await screen.findByRole("heading", {name: "A useful article"})).toBeVisible();
    expect(screen.getByText("分析完成")).toBeVisible();
    expect(screen.getByLabelText("总评分 86")).toBeVisible();
    expect(screen.getByText("一句话总结")).toBeVisible();
    expect(screen.getByText("RSS 元数据摘要")).toBeVisible();
    expect(screen.queryByText(/<strong>/)).not.toBeInTheDocument();
    expect(screen.getByText(analysisDetail.summary)).toBeVisible();
    expect(screen.getByText("确定性门禁让筛选结果更可解释。")).toBeVisible();
    expect(screen.getByText(/让模型负责判断/)).toBeVisible();
    expect(screen.getByText("六维评分")).toBeVisible();
    expect(screen.getByText("recommended")).toBeVisible();
    expect(screen.getByText("Agent 追溯")).toBeVisible();
    const frame = screen.getByTitle("原文：A useful article");
    expect(frame).toHaveAttribute("sandbox", "allow-scripts allow-same-origin allow-forms allow-popups");
    expect(frame.getAttribute("sandbox")).not.toContain("allow-top-navigation");
    expect(screen.getAllByRole("link", {name: /新窗口打开原文/})[0]).toHaveAttribute("target", "_blank");
  });

  it("renders the structured information flow in Chinese", async () => {
    localStorage.setItem("zeromind_token", "token");
    window.history.replaceState({}, "", "/analyses");
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/subscriptions")) {
        return response({items: []});
      }
      if (url.includes("/analyses")) {
        return response({items: [analysisCard], next_cursor: null});
      }
      return response({detail: {code: "not_found"}}, 404);
    });

    render(<App />);

    expect(await screen.findByRole("link", {name: "信息流"})).toBeVisible();
    expect(
      await screen.findByRole("link", {name: "A useful article"})
    ).toBeVisible();
    expect(screen.getByText("Example Engineering")).toBeVisible();
    expect(screen.getByText("86")).toBeVisible();
    expect(screen.getByText("AI")).toBeVisible();
    expect(
      screen.getByText("一篇可落地的 Agent 工作流指南。")
    ).toBeVisible();
    expect(screen.getByText("人工改判")).toBeVisible();
    expect(screen.getByRole("button", {name: "已拒绝"})).toBeVisible();
    expect(screen.getByRole("link", {name: "查看原文"})).toHaveAttribute(
      "target",
      "_blank"
    );
  });

  it("renders analysis details and submits a manual decision override", async () => {
    localStorage.setItem("zeromind_token", "token");
    window.history.replaceState(
      {},
      "",
      `/analyses/${analysisCard.id}`
    );
    let overrideRequest: RequestInit | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (init?.method === "POST") {
        overrideRequest = init;
        return response({
          ...analysisDetail,
          effective_decision: "rejected",
          overridden: true
        });
      }
      return response(analysisDetail);
    });

    render(<App />);

    expect(await screen.findByText(analysisDetail.summary)).toBeVisible();
    expect(screen.getByText("确定性门禁让筛选结果更可解释。")).toBeVisible();
    expect(screen.getByText("模型判断与业务政策应分离。")).toBeVisible();
    expect(screen.getByText("相关性")).toBeVisible();
    expect(screen.getByText("可操作性")).toBeVisible();
    expect(screen.getAllByText("15%")).toHaveLength(4);
    expect(screen.getByText("让模型负责判断，让规则负责边界。")).toBeVisible();
    expect(screen.getByText("主题相关且包含实质性技术内容。")).toBeVisible();
    expect(screen.getByText(/工作流版本 2/)).toBeVisible();
    expect(screen.getByText(/gpt-5-mini/)).toBeVisible();
    expect(screen.getAllByText(/openai/)).toHaveLength(2);
    expect(
      screen.getByText("人工复核确认内容具有长期参考价值。")
    ).toBeVisible();

    await userEvent.selectOptions(
      screen.getByLabelText("人工决策"),
      "rejected"
    );
    await userEvent.type(
      screen.getByLabelText("改判理由"),
      "人工复核发现关键论据缺少来源。"
    );
    await userEvent.click(screen.getByRole("button", {name: "提交改判"}));

    expect(JSON.parse(String(overrideRequest?.body))).toEqual({
      decision: "rejected",
      reason: "人工复核发现关键论据缺少来源。"
    });
  });

  it("creates, edits, and deletes a reading note from analysis details", async () => {
    localStorage.setItem("zeromind_token", "token");
    window.history.replaceState(
      {},
      "",
      `/analyses/${analysisCard.id}`
    );
    let notes: Array<Record<string, unknown>> = [];
    let notePayload: Record<string, unknown> | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes("/notes")) {
        if (init?.method === "POST") {
          notePayload = JSON.parse(String(init.body)) as Record<
            string,
            unknown
          >;
          const created = {
            id: "88888888-8888-8888-8888-888888888888",
            ...notePayload,
            owner_subject: "admin",
            created_at: "2026-07-31T08:00:00Z",
            updated_at: "2026-07-31T08:00:00Z"
          };
          notes = [created];
          return response(created, 201);
        }
        if (init?.method === "PUT") {
          const payload = JSON.parse(String(init.body)) as Record<
            string,
            unknown
          >;
          notes = notes.map((note) => ({
            ...note,
            ...payload,
            updated_at: "2026-07-31T08:30:00Z"
          }));
          return response(notes[0]);
        }
        if (init?.method === "DELETE") {
          notes = [];
          return new Response(null, {status: 204});
        }
        return response({items: notes});
      }
      return response(analysisDetail);
    });

    render(<App />);

    expect(await screen.findByText("还没有笔记")).toBeVisible();
    await userEvent.type(
      screen.getByLabelText("笔记正文"),
      "这条评分规则可以用于项目评审。"
    );
    await userEvent.click(screen.getByRole("button", {name: "保存笔记"}));

    expect(
      await screen.findByText("这条评分规则可以用于项目评审。")
    ).toBeVisible();
    expect(notePayload).toEqual({
      reference_id: "11111111-1111-1111-1111-111111111111",
      analysis_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      body: "这条评分规则可以用于项目评审。"
    });

    await userEvent.click(screen.getByRole("button", {name: "编辑笔记"}));
    const editor = screen.getByLabelText("笔记正文");
    await userEvent.clear(editor);
    await userEvent.type(editor, "更新后的项目评审规则。");
    await userEvent.click(screen.getByRole("button", {name: "保存修改"}));

    expect(await screen.findByText("更新后的项目评审规则。")).toBeVisible();
    await userEvent.click(
      screen.getByRole("button", {name: /删除笔记/})
    );
    await waitFor(() => {
      expect(
        screen.queryByText("更新后的项目评审规则。")
      ).not.toBeInTheDocument();
    });
    expect(screen.getByText("还没有笔记")).toBeVisible();
  });

  it("keeps analysis content visible when reading notes fail to load", async () => {
    localStorage.setItem("zeromind_token", "token");
    window.history.replaceState(
      {},
      "",
      `/analyses/${analysisCard.id}`
    );
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      if (String(input).includes("/notes")) {
        return response(
          {detail: {code: "notes_unavailable", message: "笔记服务不可用"}},
          503
        );
      }
      return response(analysisDetail);
    });

    render(<App />);

    expect(await screen.findByText(analysisDetail.summary)).toBeVisible();
    const notesPanel = await screen.findByRole("region", {name: "阅读笔记"});
    expect(within(notesPanel).getByRole("alert")).toHaveTextContent(
      "笔记服务不可用"
    );
  });
});
