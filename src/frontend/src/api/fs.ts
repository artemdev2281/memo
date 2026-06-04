import { FileNode } from "../store/useAppStore";
import { apiFetch } from "./client";

export function getTree(path: string, depth = 5): Promise<FileNode> {
  return apiFetch<FileNode>(
    `/fs/tree?path=${encodeURIComponent(path)}&depth=${depth}`,
  );
}
