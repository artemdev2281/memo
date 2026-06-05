import { getBackendPort } from "../ipc/backend";
import { apiFetch } from "./client";

export interface ChatItem {
  id: number;
  title: string;
  model: string;
  context_type: "folder" | "files" | "none";
  context_paths: string[];
  include_subfolders: boolean;
  created_at: string;
  updated_at: string;
}

export interface MessageItem {
  id: number;
  chat_id: number;
  role: "user" | "assistant";
  content: string;
  sources: string[];
  thinking?: string | null;
  created_at: string;
}

export type ChatEvent =
  | { type: "token"; content: string }
  | { type: "thinking"; content: string }
  | { type: "done"; sources: string[]; stale_warning: boolean }
  | { type: "error"; msg: string };

export function listChats(): Promise<ChatItem[]> {
  return apiFetch<ChatItem[]>("/chats");
}

export function createChat(body: {
  model: string;
  context_type?: string;
  context_paths?: string[];
  include_subfolders?: boolean;
}): Promise<ChatItem> {
  return apiFetch<ChatItem>("/chats", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateChat(
  id: number,
  body: Partial<Pick<ChatItem, "title" | "model" | "context_type" | "context_paths" | "include_subfolders">>,
): Promise<ChatItem> {
  return apiFetch<ChatItem>(`/chats/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteChat(id: number): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(`/chats/${id}`, { method: "DELETE" });
}

export function listMessages(chatId: number): Promise<MessageItem[]> {
  return apiFetch<MessageItem[]>(`/chats/${chatId}/messages`);
}

export async function* streamMessage(
  chatId: number,
  content: string,
  model: string,
  contextPaths: string[],
  thinking: boolean,
): AsyncGenerator<ChatEvent> {
  const port = await getBackendPort();
  const res = await fetch(`http://127.0.0.1:${port}/chats/${chatId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, model, context_paths: contextPaths, thinking }),
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
            yield JSON.parse(line.slice(6)) as ChatEvent;
          } catch {
            // ignore malformed SSE
          }
        }
      }
    }
  } finally {
    // Release the stream if the consumer breaks early (e.g. chat switch).
    await reader.cancel().catch(() => {});
  }
}

export function listModels(): Promise<string[]> {
  return apiFetch<string[]>("/models");
}
