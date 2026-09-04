import { handleLine } from "./handler.js";
import type { RunnerEvent } from "./protocol.js";

function emit(event: RunnerEvent): void {
  process.stdout.write(`${JSON.stringify(event)}\n`);
}

async function main(): Promise<void> {
  process.stdin.setEncoding("utf8");
  let buffer = "";
  for await (const chunk of process.stdin) {
    buffer += chunk;
    while (true) {
      const newline = buffer.indexOf("\n");
      if (newline < 0) {
        break;
      }
      let line = buffer.slice(0, newline);
      buffer = buffer.slice(newline + 1);
      if (line.endsWith("\r")) {
        line = line.slice(0, -1);
      }
      if (line.trim()) {
        await handleLine(line, emit);
      }
    }
  }
  if (buffer.trim()) {
    await handleLine(buffer.endsWith("\r") ? buffer.slice(0, -1) : buffer, emit);
  }
}

await main();
