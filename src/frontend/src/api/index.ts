import { getBackendPort } from "../ipc/backend";
import { apiFetch } from "./client";

export type IndexEvent =
  | { type: "progress"; done: number; total: number; file: string }
  | { type: "done"; file: string }
  | { type: "skip"; file: string }
  | { type: "error"; file: string; msg: string };

export interface IndexStatusItem {
  file_path: string;
  status: string;
  error_msg: string | null;
  indexed_at: string | null;
}

export async function* streamIndex(
  paths: string[],
): AsyncGenerator<IndexEvent> {
  const port = await getBackendPort();
  const res = await fetch(`http://127.0.0.1:${port}/index`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paths }),
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
            yield JSON.parse(line.slice(6)) as IndexEvent;
          } catch {
            // ignore malformed SSE lines
          }
        }
      }
    }
  } finally {
    await reader.cancel().catch(() => {});
  }
}

export function getStatuses(): Promise<IndexStatusItem[]> {
  return apiFetch<IndexStatusItem[]>("/index/status");
}

export function refreshStale(): Promise<{ started: number }> {
  return apiFetch<{ started: number }>("/index/refresh-stale", {
    method: "POST",
  });
}
