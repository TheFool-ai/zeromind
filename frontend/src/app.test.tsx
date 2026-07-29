import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./app";

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {"content-type": "application/json"}
  });
}

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
});
