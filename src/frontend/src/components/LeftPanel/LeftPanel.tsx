import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { getTree } from "../../api/fs";
import { refreshStale, streamIndex } from "../../api/index";
import { analyzeOrganization, OrganizePreview as Preview } from "../../api/organize";
import { useAppStore } from "../../store/useAppStore";
import { FileTree } from "../FileTree/FileTree";
import {
  IconAlertTriangle,
  IconArrowRight,
  IconCheck,
  IconCheckSquare,
  IconChevronDown,
  IconChevronRight,
  IconFolderOpen,
  IconFolders,
  IconRefresh,
  IconSearch,
  IconZap,
  Spinner,
} from "../Icon/Icon";
import { OrganizePreview } from "../OrganizePreview/OrganizePreview";
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

  // Organize state
  const [organizeMode, setOrganizeMode] = useState(false);
  const [includeSubfolders, setIncludeSubfolders] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [organizePreview, setOrganizePreview] = useState<Preview | null>(null);
  const [organizeResult, setOrganizeResult] = useState<{ folders_created: number; files_moved: number } | null>(null);
  const [organizeError, setOrganizeError] = useState<string | null>(null);

  function toggleSelectionMode() {
    if (selectionMode) clearSelection();
    setSelectionMode((v) => !v);
  }

  async function handleBrowse() {
    const selected = await open({ directory: true, multiple: false });
    if (typeof selected === "string" && selected) {
      setPathInput(selected);
      await loadTree(selected);
    }
  }

  async function loadTree(dir: string) {
    if (!dir) return;
    setLoadError(null);
    try {
      const result = await getTree(dir);
      setTree(result);
      setWorkDir(dir);
    } catch (e) {
      setLoadError(`Не удалось открыть папку: ${(e as Error).message}`);
    }
  }

  // Refresh the tree every 4 seconds to pick up watcher-triggered stale status changes.
  useEffect(() => {
    if (!workDir) return;
    const id = setInterval(() => {
      if (!isIndexing) loadTree(workDir);
    }, 4000);
    return () => clearInterval(id);
  }, [workDir, isIndexing]);

  async function handleIndex() {
    if (selectedPaths.size === 0 || isIndexing) return;
    setIsIndexing(true);
    clearIndexErrors();
    setErrorsExpanded(false);
    setIndexProgress({ done: 0, total: 0 });
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
      await refreshStale();
      setTimeout(async () => {
        if (workDir) await loadTree(workDir);
        setIsRefreshing(false);
      }, 1500);
    } catch (e) {
      setLoadError(`Ошибка обновления: ${(e as Error).message}`);
      setIsRefreshing(false);
    }
  }

  function handleOrganizeStart() {
    setOrganizeMode(true);
    setOrganizePreview(null);
    setOrganizeResult(null);
    setOrganizeError(null);
  }

  async function handleAnalyze() {
    if (!workDir || isAnalyzing) return;
    setIsAnalyzing(true);
    setOrganizeError(null);
    setOrganizePreview(null);
    try {
      const filePaths = selectedPaths.size > 0 ? [...selectedPaths] : undefined;
      const preview = await analyzeOrganization(workDir, includeSubfolders, filePaths);
      setOrganizePreview(preview);
    } catch (e) {
      setOrganizeError(`Ошибка анализа: ${(e as Error).message}`);
    } finally {
      setIsAnalyzing(false);
    }
  }

  function handleOrganizeDone(result: { folders_created: number; files_moved: number }) {
    setOrganizeResult(result);
    setOrganizeMode(false);
    setOrganizePreview(null);
    if (workDir) loadTree(workDir);
  }

  function handleOrganizeCancel() {
    setOrganizeMode(false);
    setOrganizePreview(null);
    setOrganizeError(null);
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
          className="input lp-path-input"
          type="text"
          placeholder="Путь к папке…"
          value={pathInput}
          onChange={(e) => setPathInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") loadTree(pathInput.trim());
          }}
        />
        <button className="btn lp-icon-btn" onClick={handleBrowse} title="Выбрать папку">
          <IconFolderOpen size={15} />
        </button>
        <button
          className="btn lp-icon-btn"
          onClick={() => loadTree(pathInput.trim())}
          title="Открыть папку"
        >
          <IconArrowRight size={15} />
        </button>
      </div>

      {loadError && (
        <div className="alert alert-error">
          <IconAlertTriangle size={14} />
          {loadError}
        </div>
      )}

      {!organizeMode && (
        <div className="lp-toolbar">
          <button
            className={`btn lp-tool-btn${selectionMode ? " active" : ""}`}
            disabled={isIndexing}
            onClick={toggleSelectionMode}
            title={selectionMode ? "Выйти из режима выбора" : "Выбрать файлы"}
          >
            <IconCheckSquare size={13} />
            Выбрать{selectionMode && selectedPaths.size > 0 ? ` (${selectedPaths.size})` : ""}
          </button>
          <button
            className="btn btn-primary lp-tool-btn"
            disabled={!selectionMode || selectedPaths.size === 0 || isIndexing}
            onClick={handleIndex}
            title="Проиндексировать выбранные файлы"
          >
            {isIndexing ? <Spinner size={13} /> : <IconZap size={13} />}
            {isIndexing ? "Индексация…" : "Индексировать"}
          </button>
          <button
            className="btn lp-tool-btn"
            disabled={isRefreshing || isIndexing}
            onClick={handleRefreshStale}
            title="Обновить устаревшие файлы"
          >
            {isRefreshing ? <Spinner size={13} /> : <IconRefresh size={13} />}
            Устаревшие
          </button>
          <button
            className="btn lp-tool-btn"
            disabled={!workDir || isIndexing}
            onClick={handleOrganizeStart}
            title="Авто-организация файлов"
          >
            <IconFolders size={13} />
            Организовать
          </button>
        </div>
      )}

      {progress && (
        <div className="lp-progress">
          <div className="lp-progress-bar" style={{ width: `${progressPct}%` }} />
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
            <IconAlertTriangle size={13} />
            {Object.keys(indexErrors).length} файл(ов) не проиндексировано
            <span className="lp-index-errors-chevron">
              {errorsExpanded ? <IconChevronDown size={12} /> : <IconChevronRight size={12} />}
            </span>
          </button>
          {errorsExpanded && (
            <ul className="lp-index-errors-list">
              {Object.entries(indexErrors).map(([path, msg]) => (
                <li key={path} title={path}>
                  <span className="lp-err-name">{path.split(/[\\/]/).pop()}</span>
                  <span className="lp-err-msg">{msg}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {organizeResult && !organizeMode && (
        <div className="alert alert-success">
          <IconCheck size={14} />
          Создано папок: {organizeResult.folders_created}, перемещено файлов: {organizeResult.files_moved}
        </div>
      )}

      <div className="lp-tree">
        {organizeMode ? (
          <div className="lp-organize-container">
            {(!organizePreview || organizePreview.empty) && (
              <div className="lp-organize-options">
                <label className="lp-subfolder-toggle">
                  <input
                    type="checkbox"
                    checked={includeSubfolders}
                    onChange={(e) => setIncludeSubfolders(e.target.checked)}
                  />
                  Включая подпапки
                </label>
                <div className="lp-organize-btn-row">
                  <button
                    className="btn btn-primary"
                    onClick={handleAnalyze}
                    disabled={isAnalyzing || !workDir}
                  >
                    {isAnalyzing ? <Spinner size={13} /> : <IconSearch size={13} />}
                    {isAnalyzing
                      ? "Анализирую…"
                      : selectedPaths.size > 0
                        ? `Анализировать (${selectedPaths.size} файл.)`
                        : "Анализировать"}
                  </button>
                  <button className="btn" onClick={handleOrganizeCancel}>
                    Отмена
                  </button>
                </div>
                {organizeError && (
                  <div className="alert alert-error">
                    <IconAlertTriangle size={14} />
                    {organizeError}
                  </div>
                )}
                {isAnalyzing && (
                  <p className="lp-analyzing-hint">Анализирую файлы, это может занять несколько минут…</p>
                )}
                {organizePreview?.empty && (
                  <p className="lp-empty-hint">Нет файлов для анализа.</p>
                )}
              </div>
            )}
            {organizePreview && !organizePreview.empty && (
              <OrganizePreview
                preview={organizePreview}
                folder={workDir}
                onDone={handleOrganizeDone}
                onCancel={handleOrganizeCancel}
              />
            )}
          </div>
        ) : !tree ? (
          <div className="lp-placeholder">
            <IconFolderOpen size={36} />
            <p>Откройте папку с документами,<br />чтобы начать работу</p>
          </div>
        ) : (
          <FileTree root={tree} selectionMode={selectionMode} />
        )}
      </div>
    </div>
  );
}
