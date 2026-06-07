import { create } from "zustand";
import type { ChatItem, MessageItem } from "../api/chat";

export type IndexStatus = "indexed" | "stale" | "error" | null;

export interface FileNode {
  name: string;
  path: string;
  type: "file" | "dir";
  status: IndexStatus;
  children: FileNode[];
}

interface AppStore {
  workDir: string;
  setWorkDir: (dir: string) => void;

  tree: FileNode | null;
  setTree: (tree: FileNode | null) => void;

  selectedPaths: Set<string>;
  toggleSelect: (path: string, filePaths: string[]) => void;
  setSelected: (paths: string[]) => void;
  clearSelection: () => void;

  indexProgress: { done: number; total: number } | null;
  setIndexProgress: (p: { done: number; total: number } | null) => void;

  indexErrors: Record<string, string>;
  addIndexError: (path: string, msg: string) => void;
  clearIndexErrors: () => void;

  // Chat state
  chats: ChatItem[];
  setChats: (chats: ChatItem[]) => void;
  addChat: (chat: ChatItem) => void;
  updateChatInList: (chat: ChatItem) => void;
  removeChatFromList: (id: number) => void;

  activeChatId: number | null;
  setActiveChatId: (id: number | null) => void;

  messages: MessageItem[];
  setMessages: (msgs: MessageItem[]) => void;
  appendMessage: (msg: MessageItem) => void;
  updateLastAssistantMessage: (content: string) => void;
  updateLastAssistantThinking: (thinking: string) => void;

  selectedModel: string;
  setSelectedModel: (model: string) => void;

  availableModels: string[];
  setAvailableModels: (models: string[]) => void;

  streamingChatId: number | null;
  setStreamingChatId: (id: number | null) => void;

  thinkingEnabled: boolean;
  setThinkingEnabled: (v: boolean) => void;

  rightPanelMode: "chat" | "generate";
  setRightPanelMode: (mode: "chat" | "generate") => void;
}

const _savedModel = typeof localStorage !== "undefined"
  ? localStorage.getItem("memo_selected_model") ?? ""
  : "";

const _savedThinking = typeof localStorage !== "undefined"
  ? localStorage.getItem("memo_thinking_enabled") !== "false"
  : true;

export const useAppStore = create<AppStore>((set) => ({
  workDir: "",
  setWorkDir: (dir) => set({ workDir: dir }),

  tree: null,
  setTree: (tree) => set({ tree }),

  selectedPaths: new Set(),
  toggleSelect: (_path, filePaths) =>
    set((state) => {
      const s = new Set(state.selectedPaths);
      const allSelected = filePaths.every((p) => s.has(p));
      if (allSelected) {
        filePaths.forEach((p) => s.delete(p));
      } else {
        filePaths.forEach((p) => s.add(p));
      }
      return { selectedPaths: s };
    }),
  setSelected: (paths) => set({ selectedPaths: new Set(paths) }),
  clearSelection: () => set({ selectedPaths: new Set() }),

  indexProgress: null,
  setIndexProgress: (p) => set({ indexProgress: p }),

  indexErrors: {},
  addIndexError: (path, msg) =>
    set((state) => ({ indexErrors: { ...state.indexErrors, [path]: msg } })),
  clearIndexErrors: () => set({ indexErrors: {} }),

  // Chat state
  chats: [],
  setChats: (chats) => set({ chats }),
  addChat: (chat) => set((state) => ({ chats: [chat, ...state.chats] })),
  updateChatInList: (chat) =>
    set((state) => ({
      chats: state.chats.map((c) => (c.id === chat.id ? chat : c)),
    })),
  removeChatFromList: (id) =>
    set((state) => ({ chats: state.chats.filter((c) => c.id !== id) })),

  activeChatId: null,
  setActiveChatId: (id) => set({ activeChatId: id }),

  messages: [],
  setMessages: (msgs) => set({ messages: msgs }),
  appendMessage: (msg) =>
    set((state) => ({ messages: [...state.messages, msg] })),
  updateLastAssistantMessage: (content) =>
    set((state) => {
      const msgs = [...state.messages];
      const last = msgs[msgs.length - 1];
      if (last && last.role === "assistant") {
        msgs[msgs.length - 1] = { ...last, content };
      }
      return { messages: msgs };
    }),
  updateLastAssistantThinking: (thinking) =>
    set((state) => {
      const msgs = [...state.messages];
      const last = msgs[msgs.length - 1];
      if (last && last.role === "assistant") {
        msgs[msgs.length - 1] = { ...last, thinking };
      }
      return { messages: msgs };
    }),

  selectedModel: _savedModel,
  setSelectedModel: (model) => {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem("memo_selected_model", model);
    }
    set({ selectedModel: model });
  },

  availableModels: [],
  setAvailableModels: (models) => set({ availableModels: models }),

  streamingChatId: null,
  setStreamingChatId: (id) => set({ streamingChatId: id }),

  thinkingEnabled: _savedThinking,
  setThinkingEnabled: (v) => {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem("memo_thinking_enabled", String(v));
    }
    set({ thinkingEnabled: v });
  },

  rightPanelMode: "chat",
  setRightPanelMode: (mode) => set({ rightPanelMode: mode }),
}));

export function collectFilePaths(node: FileNode): string[] {
  if (node.type === "file") return [node.path];
  return node.children.flatMap(collectFilePaths);
}
