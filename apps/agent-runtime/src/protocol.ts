export type JsonSchema = Record<string, unknown>;

export interface ExecuteRequest {
  id: string;
  type: "execute";
  provider: string;
  model: string;
  api_key: string;
  thinking_level:
    | "off"
    | "minimal"
    | "low"
    | "medium"
    | "high"
    | "xhigh"
    | "max";
  system_prompt: string;
  input: Record<string, unknown>;
  output_schema: JsonSchema;
}

export interface SessionIsolationConfig {
  noTools: "all";
  sessionPersistence: false;
}

export type RunnerEvent =
  | { id: string; type: "delta"; delta: string }
  | {
      id: string;
      type: "completed";
      output: Record<string, unknown>;
      usage: Record<string, number>;
      response_sha256: string;
      response_character_count: number;
    }
  | {
      id: string;
      type: "failed";
      code: string;
      message: string;
      response_sha256?: string;
      response_character_count?: number;
    };

export type EmitEvent = (event: RunnerEvent) => void;

const thinkingLevels = new Set([
  "off",
  "minimal",
  "low",
  "medium",
  "high",
  "xhigh",
  "max",
]);

function object(value: unknown, field: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${field} must be an object`);
  }
  return value as Record<string, unknown>;
}

function string(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${field} must be a non-empty string`);
  }
  return value;
}

export function parseExecuteRequest(value: unknown): ExecuteRequest {
  const candidate = object(value, "request");
  if (candidate.type !== "execute") {
    throw new Error("type must be execute");
  }
  const thinkingLevel = string(candidate.thinking_level, "thinking_level");
  if (!thinkingLevels.has(thinkingLevel)) {
    throw new Error("thinking_level is unsupported");
  }
  return {
    id: string(candidate.id, "id"),
    type: "execute",
    provider: string(candidate.provider, "provider"),
    model: string(candidate.model, "model"),
    api_key: string(candidate.api_key, "api_key"),
    thinking_level: thinkingLevel as ExecuteRequest["thinking_level"],
    system_prompt: string(candidate.system_prompt, "system_prompt"),
    input: object(candidate.input, "input"),
    output_schema: object(candidate.output_schema, "output_schema"),
  };
}

export function buildSessionConfig(
  _request: ExecuteRequest,
): SessionIsolationConfig {
  return {
    noTools: "all",
    sessionPersistence: false,
  };
}

export function buildPrompt(request: ExecuteRequest): string {
  return [
    "Analyze the following structured input.",
    "Return only one JSON object that conforms exactly to the supplied JSON Schema.",
    `INPUT:${JSON.stringify(request.input)}`,
    `OUTPUT_SCHEMA:${JSON.stringify(request.output_schema)}`,
  ].join("\n");
}

export function parseModelOutput(text: string): Record<string, unknown> {
  const trimmed = text.trim();
  const fenced = /```(?:json)?\s*([\s\S]*?)\s*```/i.exec(trimmed);
  const candidate = fenced?.[1] ?? trimmed;
  const value: unknown = JSON.parse(candidate);
  return object(value, "model output");
}
