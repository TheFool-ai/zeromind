import { InMemoryCredentialStore } from "@earendil-works/pi-ai";
import { createHash } from "node:crypto";
import {
  createAgentSession,
  DefaultResourceLoader,
  ModelRuntime,
  SessionManager,
  SettingsManager,
} from "@earendil-works/pi-coding-agent";

import {
  buildPrompt,
  buildSessionConfig,
  type EmitEvent,
  type ExecuteRequest,
  parseModelOutput,
} from "./protocol.js";

export interface ExecutionResult {
  output: Record<string, unknown>;
  usage: Record<string, number>;
  responseSha256: string;
  responseCharacterCount: number;
}

export class RunnerFailure extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly responseSha256?: string,
    public readonly responseCharacterCount?: number,
  ) {
    super(message);
  }
}

export async function executeWithPi(
  request: ExecuteRequest,
  emit: EmitEvent,
): Promise<ExecutionResult> {
  const credentials = new InMemoryCredentialStore();
  const modelRuntime = await ModelRuntime.create({
    credentials,
    modelsPath: null,
  });
  await modelRuntime.setRuntimeApiKey(request.provider, request.api_key);
  const model = modelRuntime.getModel(request.provider, request.model);
  if (!model) {
    throw new Error(
      `model ${request.provider}/${request.model} is not registered`,
    );
  }

  const cwd = process.cwd();
  const settingsManager = SettingsManager.inMemory();
  const resourceLoader = new DefaultResourceLoader({
    cwd,
    agentDir: cwd,
    settingsManager,
    noExtensions: true,
    noSkills: true,
    noPromptTemplates: true,
    noThemes: true,
    noContextFiles: true,
    systemPrompt: request.system_prompt,
  });
  await resourceLoader.reload();
  const isolation = buildSessionConfig(request);
  const { session } = await createAgentSession({
    cwd,
    modelRuntime,
    model,
    thinkingLevel: request.thinking_level,
    noTools: isolation.noTools,
    resourceLoader,
    settingsManager,
    sessionManager: SessionManager.inMemory(cwd),
  });

  const unsubscribe = session.subscribe((event) => {
    if (
      event.type === "message_update" &&
      event.assistantMessageEvent.type === "text_delta"
    ) {
      emit({
        id: request.id,
        type: "delta",
        delta: event.assistantMessageEvent.delta,
      });
    }
  });
  try {
    await session.prompt(buildPrompt(request), {
      expandPromptTemplates: false,
    });
    await session.agent.waitForIdle();
    const text = session.getLastAssistantText();
    if (!text) {
      throw new Error("Pi returned no assistant output");
    }
    const responseSha256 = createHash("sha256").update(text).digest("hex");
    const responseCharacterCount = Array.from(text).length;
    let output: Record<string, unknown>;
    try {
      output = parseModelOutput(text);
    } catch {
      throw new RunnerFailure(
        "json_invalid",
        "model returned invalid JSON",
        responseSha256,
        responseCharacterCount,
      );
    }
    const stats = session.getSessionStats();
    return {
      output,
      usage: {
        input: stats.tokens.input,
        output: stats.tokens.output,
        cache_read: stats.tokens.cacheRead,
        cache_write: stats.tokens.cacheWrite,
        total: stats.tokens.total,
        cost: stats.cost,
      },
      responseSha256,
      responseCharacterCount,
    };
  } finally {
    unsubscribe();
    session.dispose();
    await modelRuntime.removeRuntimeApiKey(request.provider);
  }
}
