import { useRef, useState } from "react";
import type { OrganizeFile, OrganizePreview as Preview } from "../../api/organize";
import { applyOrganization } from "../../api/organize";
import {
  IconAlertTriangle,
  IconCheck,
  IconFileText,
  IconFolder,
  IconPencil,
  IconPlus,
  IconX,
  Spinner,
} from "../Icon/Icon";
import "./OrganizePreview.css";

interface EditableCluster {
  id: string | number;
  name: string;
  files: OrganizeFile[];
}

interface DragState {
  filePath: string;
  sourceId: string | number;
}

interface Props {
  preview: Preview;
  folder: string;
  onDone: (result: { folders_created: number; files_moved: number }) => void;
  onCancel: () => void;
}

let _nextId = 1;
function newId(): string {
  return `new_${_nextId++}`;
}

export function OrganizePreview({ preview, folder, onDone, onCancel }: Props) {
  const [clusters, setClusters] = useState<EditableCluster[]>(() => {
    const result: EditableCluster[] = (preview.clusters || []).map((c) => ({
      id: c.id,
      name: c.name,
      files: [...c.files],
    }));
    const misc = preview.misc || [];
    if (misc.length > 0) {
      result.push({ id: "misc", name: "Разное", files: [...misc] });
    }
    return result;
  });

  const [editingId, setEditingId] = useState<string | number | null>(null);
  const [editName, setEditName] = useState("");
  const [dragging, setDragging] = useState<DragState | null>(null);
  const [dragOverId, setDragOverId] = useState<string | number | null>(null);
  const [isApplying, setIsApplying] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);
  const editInputRef = useRef<HTMLInputElement>(null);

  function startEdit(id: string | number, name: string) {
    setEditingId(id);
    setEditName(name);
    setTimeout(() => editInputRef.current?.focus(), 0);
  }

  function commitEdit(id: string | number) {
    if (editName.trim()) {
      setClusters((prev) =>
        prev.map((c) => (c.id === id ? { ...c, name: editName.trim() } : c)),
      );
    }
    setEditingId(null);
  }

  function addCluster() {
    setClusters((prev) => [...prev, { id: newId(), name: "Новая папка", files: [] }]);
  }

  function removeCluster(id: string | number) {
    setClusters((prev) => {
      const target = prev.find((c) => c.id === id);
      if (!target) return prev;
      const orphans = target.files;
      const miscIdx = prev.findIndex((c) => c.id === "misc");
      if (orphans.length === 0) {
        return prev.filter((c) => c.id !== id);
      }
      if (miscIdx >= 0) {
        return prev
          .filter((c) => c.id !== id)
          .map((c) =>
            c.id === "misc" ? { ...c, files: [...c.files, ...orphans] } : c,
          );
      }
      return prev
        .filter((c) => c.id !== id)
        .concat([{ id: "misc", name: "Разное", files: orphans }]);
    });
  }

  function onDragStart(filePath: string, sourceId: string | number) {
    setDragging({ filePath, sourceId });
  }

  function onDragOver(e: React.DragEvent, targetId: string | number) {
    e.preventDefault();
    setDragOverId(targetId);
  }

  function onDrop(e: React.DragEvent, targetId: string | number) {
    e.preventDefault();
    setDragOverId(null);
    if (!dragging || dragging.sourceId === targetId) {
      setDragging(null);
      return;
    }
    const { filePath, sourceId } = dragging;
    setClusters((prev) => {
      let movedFile: OrganizeFile | undefined;
      const updated = prev.map((c) => {
        if (c.id === sourceId) {
          const file = c.files.find((f) => f.path === filePath);
          movedFile = file;
          return { ...c, files: c.files.filter((f) => f.path !== filePath) };
        }
        return c;
      });
      if (!movedFile) return prev;
      return updated.map((c) =>
        c.id === targetId ? { ...c, files: [...c.files, movedFile!] } : c,
      );
    });
    setDragging(null);
  }

  async function handleApply() {
    setIsApplying(true);
    setApplyError(null);
    const plan = clusters
      .filter((c) => c.files.length > 0)
      .map((c) => ({
        folder_name: c.name,
        files: c.files.map((f) => f.path),
      }));
    try {
      const result = await applyOrganization(folder, plan);
      onDone(result);
    } catch (e) {
      setApplyError((e as Error).message);
      setIsApplying(false);
    }
  }

  const totalFiles = clusters.reduce((s, c) => s + c.files.length, 0);

  return (
    <div className="op-root">
      <div className="op-header">
        <span className="op-title">Предложенная организация</span>
        {preview.single_cluster && (
          <span className="op-warning">
            <IconAlertTriangle size={12} />
            Все документы одной темы — организация может не потребоваться
          </span>
        )}
      </div>

      <div className="op-clusters">
        {clusters.length === 0 && (
          <p className="op-empty">Нет папок для отображения</p>
        )}
        {clusters.map((cluster) => (
          <div
            key={cluster.id}
            className={`op-cluster${dragOverId === cluster.id ? " op-drag-over" : ""}`}
            onDragOver={(e) => onDragOver(e, cluster.id)}
            onDrop={(e) => onDrop(e, cluster.id)}
            onDragLeave={() => setDragOverId(null)}
          >
            <div className="op-cluster-header">
              <span className="op-cluster-icon">
                <IconFolder size={14} />
              </span>
              {editingId === cluster.id ? (
                <input
                  ref={editInputRef}
                  className="op-edit-input"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  onBlur={() => commitEdit(cluster.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitEdit(cluster.id);
                    if (e.key === "Escape") setEditingId(null);
                  }}
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <span
                  className="op-cluster-name"
                  onDoubleClick={() => startEdit(cluster.id, cluster.name)}
                  title="Двойной клик для переименования"
                >
                  {cluster.name}
                </span>
              )}
              <div className="op-cluster-actions">
                <button
                  className="op-action-btn"
                  title="Переименовать"
                  onClick={() => startEdit(cluster.id, cluster.name)}
                >
                  <IconPencil size={12} />
                </button>
                <button
                  className="op-action-btn op-action-remove"
                  title="Удалить папку (файлы → Разное)"
                  onClick={() => removeCluster(cluster.id)}
                >
                  <IconX size={12} />
                </button>
              </div>
              <span className="op-file-count">{cluster.files.length}</span>
            </div>
            <div className="op-files">
              {cluster.files.length === 0 && (
                <span className="op-empty-cluster">пусто (перетащите файлы сюда)</span>
              )}
              {cluster.files.map((file) => (
                <div
                  key={file.path}
                  className="op-file"
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData("text/plain", file.path);
                    onDragStart(file.path, cluster.id);
                  }}
                  title={file.path}
                >
                  <IconFileText size={12} />
                  {file.name}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="op-footer">
        <button className="btn" onClick={addCluster}>
          <IconPlus size={13} />
          Папка
        </button>
        <div style={{ flex: 1 }} />
        {applyError && <span className="op-apply-error">{applyError}</span>}
        <span className="op-summary">{totalFiles} файл(ов)</span>
        <button className="btn" onClick={onCancel} disabled={isApplying}>
          Отмена
        </button>
        <button
          className="btn btn-primary"
          onClick={handleApply}
          disabled={isApplying || totalFiles === 0}
        >
          {isApplying ? <Spinner size={13} /> : <IconCheck size={13} />}
          {isApplying ? "Применяю…" : "Применить"}
        </button>
      </div>
    </div>
  );
}
