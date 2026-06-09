import { useEffect, useRef, useState } from "react";
import {
  FileNode,
  collectFilePaths,
  useAppStore,
} from "../../store/useAppStore";
import {
  IconChevronDown,
  IconChevronRight,
  IconFileText,
  IconFolder,
} from "../Icon/Icon";
import "./FileTree.css";

const STATUS_TITLE: Record<string, string> = {
  indexed: "Проиндексирован",
  stale: "Устарел — требуется переиндексация",
  error: "Ошибка индексации",
};

function StatusDot({ status }: { status: string | null }) {
  if (!status) return null;
  return (
    <span
      className={`ft-status ft-status-${status}`}
      title={STATUS_TITLE[status] ?? status}
    />
  );
}

function getCheckState(
  node: FileNode,
  selectedPaths: Set<string>,
): "all" | "some" | "none" {
  const files = collectFilePaths(node);
  if (files.length === 0) return "none";
  const count = files.filter((p) => selectedPaths.has(p)).length;
  if (count === 0) return "none";
  if (count === files.length) return "all";
  return "some";
}

interface NodeProps {
  node: FileNode;
  depth: number;
  selectionMode: boolean;
}

function TreeNode({ node, depth, selectionMode }: NodeProps) {
  const [expanded, setExpanded] = useState(depth < 2);
  const { selectedPaths, toggleSelect, indexProgress } = useAppStore();
  const checkRef = useRef<HTMLInputElement>(null);

  const filePaths = collectFilePaths(node);
  const checkState = getCheckState(node, selectedPaths);

  // `indeterminate` is a DOM property, not an attribute — sync it after render
  // (a ref write during render misses the first paint entirely).
  useEffect(() => {
    if (checkRef.current) {
      checkRef.current.indeterminate = checkState === "some";
    }
  }, [checkState, selectionMode]);

  const isIndexing = indexProgress !== null;
  const isDir = node.type === "dir";

  return (
    <div className="ft-node">
      <div
        className="ft-row"
        style={{ paddingLeft: 8 + depth * 16 }}
        onClick={isDir ? () => setExpanded((v) => !v) : undefined}
      >
        {selectionMode && (
          <input
            ref={checkRef}
            type="checkbox"
            className="ft-check"
            checked={checkState === "all"}
            disabled={isIndexing || filePaths.length === 0}
            onClick={(e) => e.stopPropagation()}
            onChange={() => toggleSelect(node.path, filePaths)}
          />
        )}
        <span className={`ft-expand${isDir ? "" : " ft-expand-spacer"}`}>
          {isDir && (expanded ? <IconChevronDown size={12} /> : <IconChevronRight size={12} />)}
        </span>
        <span className={`ft-icon${isDir ? " ft-icon-dir" : ""}`}>
          {isDir ? <IconFolder size={14} /> : <IconFileText size={14} />}
        </span>
        <span className="ft-name" title={node.path}>
          {node.name}
        </span>
        {node.type === "file" && <StatusDot status={node.status} />}
      </div>
      {isDir && expanded && node.children.length > 0 && (
        <div className="ft-children">
          {node.children.map((child) => (
            <TreeNode
              key={child.path}
              node={child}
              depth={depth + 1}
              selectionMode={selectionMode}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface FileTreeProps {
  root: FileNode;
  selectionMode: boolean;
}

export function FileTree({ root, selectionMode }: FileTreeProps) {
  return (
    <div className="file-tree">
      {root.children.length === 0 ? (
        <p className="ft-empty">Папка пуста</p>
      ) : (
        root.children.map((child) => (
          <TreeNode
            key={child.path}
            node={child}
            depth={0}
            selectionMode={selectionMode}
          />
        ))
      )}
    </div>
  );
}
