import { InMemoryCredentialStore } from "@earendil-works/pi-ai";
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
    const stats = session.getSessionStats();
    return {
      output: parseModelOutput(text),
      usage: {
        input: stats.tokens.input,
        output: stats.tokens.output,
        cache_read: stats.tokens.cacheRead,
        cache_write: stats.tokens.cacheWrite,
        total: stats.tokens.total,
        cost: stats.cost,
      },
    };
  } finally {
    unsubscribe();
    session.dispose();
    await modelRuntime.removeRuntimeApiKey(request.provider);
  }
}

