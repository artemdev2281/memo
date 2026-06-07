import { getBackendPort } from "../ipc/backend";
import { apiFetch } from "./client";

export type GenEvent =
  | { type: "token"; content: string }
  | { type: "thinking"; content: string }
  | { type: "done"; suggested_filename: string }
  | { type: "error"; msg: string };

export async function* streamGenerate(
  request: string,
  format: ".txt" | ".md",
  contextPaths: string[],
  model: string,
  thinking: boolean,
): AsyncGenerator<GenEvent> {
  const port = await getBackendPort();
  const res = await fetch(`http://127.0.0.1:${port}/generate/document`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      request,
      format,
      context_paths: contextPaths,
      model,
      thinking,
    }),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);

  const body = res.body;
  if (!body) throw new Error("No response body");
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() ?? "";
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            yield JSON.parse(line.slice(6)) as GenEvent;
          } catch {
            // ignore malformed SSE
          }
        }
      }
    }
  } finally {
    await reader.cancel().catch(() => {});
  }
}

export function saveDocument(
  folder: string,
  filename: string,
  content: string,
): Promise<{ path: string; name: string }> {
  return apiFetch<{ path: string; name: string }>("/generate/save", {
    method: "POST",
    body: JSON.stringify({ folder, filename, content }),
  });
}
