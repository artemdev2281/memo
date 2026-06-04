import { useState } from "react";
import { getTree } from "../../api/fs";
import { refreshStale, streamIndex } from "../../api/index";
import { useAppStore } from "../../store/useAppStore";
import { FileTree } from "../FileTree/FileTree";
import "./LeftPanel.css";

export function LeftPanel() {
  const {
    workDir,
    setWorkDir,
    tree,
    setTree,
    selectedPaths,
    clearSelection,
    indexProgress,
    setIndexProgress,
    clearIndexErrors,
    addIndexError,
    indexErrors,
  } = useAppStore();

  const [errorsExpanded, setErrorsExpanded] = useState(false);

  const [pathInput, setPathInput] = useState(workDir);
  const [selectionMode, setSelectionMode] = useState(false);
  const [isIndexing, setIsIndexing] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  function toggleSelectionMode() {
    if (selectionMode) {
      clearSelection();
    }
    setSelectionMode((v) => !v);
  }

  async function loadTree(dir: string) {
    setLoadError(null);
    try {
      const result = await getTree(dir);
      setTree(result);
      setWorkDir(dir);
    } catch (e) {
      setLoadError(`Не удалось открыть папку: ${(e as Error).message}`);
    }
  }

  async function handleIndex() {
    if (selectedPaths.size === 0 || isIndexing) return;
    setIsIndexing(true);
    clearIndexErrors();
    setErrorsExpanded(false);
    setIndexProgress({ done: 0, total: selectedPaths.size });
    try {
      for await (const event of streamIndex([...selectedPaths])) {
        if (event.type === "progress") {
          setIndexProgress({ done: event.done, total: event.total });
        } else if (event.type === "error") {
          addIndexError(event.file, event.msg);
        }
      }
      if (workDir) await loadTree(workDir);
    } catch (e) {
      setLoadError(`Ошибка индексации: ${(e as Error).message}`);
    } finally {
      setIsIndexing(false);
      setIndexProgress(null);
    }
  }

  async function handleRefreshStale() {
    if (isRefreshing) return;
    setIsRefreshing(true);
    try {
      const result = await refreshStale();
      if (result.started === 0) {
        // nothing to refresh
      }
      setTimeout(async () => {
        if (workDir) await loadTree(workDir);
        setIsRefreshing(false);
      }, 1500);
    } catch (e) {
      setLoadError(`Ошибка обновления: ${(e as Error).message}`);
      setIsRefreshing(false);
    }
  }

  const progress = indexProgress;
  const progressPct =
    progress && progress.total > 0
      ? Math.round((progress.done / progress.total) * 100)
      : 0;

  return (
    <div className="left-panel">
      <div className="lp-path-row">
        <input
          className="lp-path-input"
          type="text"
          placeholder="Путь к папке…"
          value={pathInput}
          onChange={(e) => setPathInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") loadTree(pathInput.trim());
          }}
        />
        <button
          className="lp-btn lp-btn-open"
          onClick={() => loadTree(pathInput.trim())}
          title="Открыть папку"
        >
          ↗
        </button>
      </div>

      {loadError && <div className="lp-error">{loadError}</div>}

      <div className="lp-toolbar">
        <button
          className={`lp-btn lp-btn-select${selectionMode ? " active" : ""}`}
          disabled={isIndexing}
          onClick={toggleSelectionMode}
          title={selectionMode ? "Выйти из режима выбора" : "Выбрать файлы"}
        >
          ☑ Выбрать{selectionMode && selectedPaths.size > 0 ? ` (${selectedPaths.size})` : ""}
        </button>
        <button
          className="lp-btn lp-btn-index"
          disabled={!selectionMode || selectedPaths.size === 0 || isIndexing}
          onClick={handleIndex}
          title="Проиндексировать выбранные файлы"
        >
          {isIndexing ? "⏳ Индексация…" : "⚡ Индексировать"}
        </button>
        <button
          className="lp-btn lp-btn-refresh"
          disabled={isRefreshing || isIndexing}
          onClick={handleRefreshStale}
          title="Обновить устаревшие файлы"
        >
          {isRefreshing ? "⏳" : "↻"} Устаревшие
        </button>
      </div>

      {progress && (
        <div className="lp-progress">
          <div
            className="lp-progress-bar"
            style={{ width: `${progressPct}%` }}
          />
          <span className="lp-progress-label">
            {progress.done} / {progress.total}
          </span>
        </div>
      )}

      {Object.keys(indexErrors).length > 0 && (
        <div className="lp-index-errors">
          <button
            className="lp-index-errors-header"
            onClick={() => setErrorsExpanded((v) => !v)}
          >
            ⚠️ {Object.keys(indexErrors).length} файл(ов) не проиндексировано
            <span className="lp-index-errors-chevron">
              {errorsExpanded ? "▾" : "▸"}
            </span>
          </button>
          {errorsExpanded && (
            <ul className="lp-index-errors-list">
              {Object.entries(indexErrors).map(([path, msg]) => (
                <li key={path} title={path}>
                  <span className="lp-err-name">
                    {path.split(/[\\/]/).pop()}
                  </span>
                  <span className="lp-err-msg">{msg}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="lp-tree">
        {!tree ? (
          <div className="lp-placeholder">
            <p>Введите путь к папке и нажмите Enter или ↗</p>
          </div>
        ) : (
          <FileTree root={tree} selectionMode={selectionMode} />
        )}
      </div>
    </div>
  );
}
