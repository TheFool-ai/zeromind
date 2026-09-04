import { describe, expect, it } from "vitest";

import {
  buildPrompt,
  buildSessionConfig,
  parseExecuteRequest,
  parseModelOutput,
} from "./protocol.js";

const valid = {
  id: "request-1",
  type: "execute",
  provider: "openai",
  model: "gpt-5-mini",
  api_key: "secret",
  thinking_level: "medium",
  system_prompt: "Analyze the article.",
  input: { title: "Article" },
  output_schema: {
    type: "object",
    required: ["summary"],
    properties: { summary: { type: "string" } },
  },
};

describe("parseExecuteRequest", () => {
  it("accepts the complete typed request", () => {
    expect(parseExecuteRequest(valid)).toEqual(valid);
  });

  it("rejects requests without an output schema", () => {
    const malformed = { ...valid, output_schema: undefined };

    expect(() => parseExecuteRequest(malformed)).toThrow("output_schema");
  });
});

describe("Pi session isolation", () => {
  it("disables every Pi tool and session persistence", () => {
    const request = parseExecuteRequest(valid);

    expect(buildSessionConfig(request)).toMatchObject({
      noTools: "all",
      sessionPersistence: false,
    });
  });

  it("keeps provider credentials out of the model prompt", () => {
    const request = parseExecuteRequest(valid);

    const prompt = buildPrompt(request);

    expect(prompt).toContain('"title":"Article"');
    expect(prompt).toContain('"summary"');
    expect(prompt).not.toContain("secret");
  });
});

describe("parseModelOutput", () => {
  it("accepts a JSON code block after provider reasoning text", () => {
    expect(
      parseModelOutput('Analysis complete.\n```json\n{"summary":"Useful"}\n```'),
    ).toEqual({ summary: "Useful" });
  });

  it("rejects prose with an unmarked JSON fragment", () => {
    expect(() =>
      parseModelOutput('The answer is {"summary":"Useful"}.'),
    ).toThrow();
  });
});
