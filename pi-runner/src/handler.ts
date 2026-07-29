import { executeWithPi, type ExecutionResult } from "./pi-executor.js";
import {
  type EmitEvent,
  type ExecuteRequest,
  parseExecuteRequest,
} from "./protocol.js";

export type RunnerExecutor = (
  request: ExecuteRequest,
  emit: EmitEvent,
) => Promise<ExecutionResult>;

function requestId(value: unknown): string {
  if (
    typeof value === "object" &&
    value !== null &&
    "id" in value &&
    typeof value.id === "string"
  ) {
    return value.id;
  }
  return "unknown";
}

function safeMessage(error: unknown, secret?: string): string {
  const message = error instanceof Error ? error.message : "runner execution failed";
  return secret ? message.replaceAll(secret, "[redacted]") : message;
}

export async function handleLine(
  line: string,
  emit: EmitEvent,
  executor: RunnerExecutor = executeWithPi,
): Promise<void> {
  let decoded: unknown;
  let request: ExecuteRequest | undefined;
  try {
    decoded = JSON.parse(line);
    request = parseExecuteRequest(decoded);
    const result = await executor(request, emit);
    emit({
      id: request.id,
      type: "completed",
      output: result.output,
      usage: result.usage,
    });
  } catch (error) {
    emit({
      id: request?.id ?? requestId(decoded),
      type: "failed",
      code: request ? "pi_execution_failed" : "invalid_request",
      message: safeMessage(error, request?.api_key),
    });
  }
}

