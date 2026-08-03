import { describe, expect, it } from "vitest";

import { handleLine, type RunnerExecutor } from "./handler.js";
import { RunnerFailure } from "./pi-executor.js";

const request = {
  id: "request-1",
  type: "execute",
  provider: "openai",
  model: "gpt-5-mini",
  api_key: "secret-value",
  thinking_level: "off",
  system_prompt: "Analyze.",
  input: { title: "Article" },
  output_schema: { type: "object" },
};

describe("handleLine", () => {
  it("emits a correlated completion from the executor", async () => {
    const executor: RunnerExecutor = async (_request, emit) => {
      emit({ id: "request-1", type: "delta", delta: "working" });
      return {
        output: { summary: "Done" },
        usage: { input: 2, output: 1, cost: 0.001 },
        responseSha256: "a".repeat(64),
        responseCharacterCount: 18,
      };
    };
    const events: unknown[] = [];

    await handleLine(JSON.stringify(request), (event) => events.push(event), executor);

    expect(events).toEqual([
      { id: "request-1", type: "delta", delta: "working" },
      {
        id: "request-1",
        type: "completed",
        output: { summary: "Done" },
        usage: { input: 2, output: 1, cost: 0.001 },
        response_sha256: "a".repeat(64),
        response_character_count: 18,
      },
    ]);
  });

  it("emits invalid JSON diagnostics without the raw response", async () => {
    const executor: RunnerExecutor = async () => {
      throw new RunnerFailure(
        "json_invalid",
        "model returned invalid JSON",
        "b".repeat(64),
        42,
      );
    };
    const events: unknown[] = [];

    await handleLine(JSON.stringify(request), (event) => events.push(event), executor);

    expect(events).toEqual([
      {
        id: "request-1",
        type: "failed",
        code: "json_invalid",
        message: "model returned invalid JSON",
        response_sha256: "b".repeat(64),
        response_character_count: 42,
      },
    ]);
    expect(JSON.stringify(events)).not.toContain("ARTICLE BODY");
  });

  it("reports validation failure without exposing the API key", async () => {
    const events: unknown[] = [];

    await handleLine(
      JSON.stringify({ ...request, output_schema: undefined }),
      (event) => events.push(event),
    );

    expect(events).toHaveLength(1);
    expect(JSON.stringify(events[0])).toContain("failed");
    expect(JSON.stringify(events[0])).not.toContain("secret-value");
  });
});
