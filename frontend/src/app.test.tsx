import { render, screen } from "@testing-library/react";
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
