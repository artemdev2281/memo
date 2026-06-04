import { useRef, useState } from "react";
import {
  FileNode,
  collectFilePaths,
  useAppStore,
} from "../../store/useAppStore";
import "./FileTree.css";

const STATUS_ICON: Record<string, string> = {
  indexed: "✅",
  stale: "⚠️",
  error: "❌",
};

function FileIcon({ node }: { node: FileNode }) {
  if (node.type === "dir") return <span className="ft-icon">📁</span>;
  const icon = node.status ? STATUS_ICON[node.status] : "📄";
  return <span className="ft-icon">{icon}</span>;
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

  if (checkRef.current) {
    checkRef.current.indeterminate = checkState === "some";
  }

  const isIndexing = indexProgress !== null;

  return (
    <div className="ft-node">
      <div className="ft-row" style={{ paddingLeft: depth * 16 }}>
        {selectionMode && (
          <input
            ref={checkRef}
            type="checkbox"
            className="ft-check"
            checked={checkState === "all"}
            disabled={isIndexing || filePaths.length === 0}
            onChange={() => toggleSelect(node.path, filePaths)}
          />
        )}
        {node.type === "dir" && (
          <button
            className="ft-expand"
            onClick={() => setExpanded((v) => !v)}
            aria-label={expanded ? "collapse" : "expand"}
          >
            {expanded ? "▾" : "▸"}
          </button>
        )}
        <FileIcon node={node} />
        <span className="ft-name" title={node.path}>
          {node.name}
        </span>
      </div>
      {node.type === "dir" && expanded && node.children.length > 0 && (
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
