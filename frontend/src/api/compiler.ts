import type { CompileEvent, HealthResponse } from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`);

  if (!response.ok) {
    throw new Error(`Health check failed with HTTP ${response.status}`);
  }

  return response.json();
}

export async function compilePrompt(
  prompt: string,
  onEvent: (event: CompileEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/compile`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ prompt }),
    signal
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Compile request failed with HTTP ${response.status}`);
  }

  if (!response.body) {
    throw new Error("The compiler response did not include a readable stream.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();

    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    buffer = drainSseBuffer(buffer, onEvent);
  }

  buffer += decoder.decode();
  drainSseBuffer(`${buffer}\n\n`, onEvent);
}

function drainSseBuffer(buffer: string, onEvent: (event: CompileEvent) => void): string {
  const frames = buffer.split(/\r?\n\r?\n/);
  const remainder = frames.pop() ?? "";

  for (const frame of frames) {
    const data = frame
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.replace(/^data:\s?/, ""))
      .join("\n");

    if (!data.trim()) {
      continue;
    }

    onEvent(JSON.parse(data) as CompileEvent);
  }

  return remainder;
}
