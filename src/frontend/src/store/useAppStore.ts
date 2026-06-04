import { create } from "zustand";

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
}

export const useAppStore = create<AppStore>((set) => ({
  workDir: "",
  setWorkDir: (dir) => set({ workDir: dir }),

  tree: null,
  setTree: (tree) => set({ tree }),

  selectedPaths: new Set(),
  toggleSelect: (path, filePaths) =>
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
}));

export function collectFilePaths(node: FileNode): string[] {
  if (node.type === "file") return [node.path];
  return node.children.flatMap(collectFilePaths);
}
