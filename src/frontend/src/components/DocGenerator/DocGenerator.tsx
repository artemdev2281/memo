import { useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { saveDocument, streamGenerate } from "../../api/generate";
import { getTree } from "../../api/fs";
import { useAppStore } from "../../store/useAppStore";
import {
  IconAlertTriangle,
  IconCheck,
  IconFolder,
  IconPaperclip,
  IconSave,
  IconSparkles,
  Spinner,
} from "../Icon/Icon";
import "./DocGenerator.css";

type Format = ".txt" | ".md";

export function DocGenerator() {
  const {
    workDir,
    selectedPaths,
    selectedModel,
    thinkingEnabled,
    setTree,
  } = useAppStore();

  const [format, setFormat] = useState<Format>(".md");
  const [request, setRequest] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatedContent, setGeneratedContent] = useState("");
  const [suggestedFilename, setSuggestedFilename] = useState("");
  const [showSaveRow, setShowSaveRow] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const previewEndRef = useRef<HTMLDivElement>(null);

  const contextPaths =
    selectedPaths.size > 0
      ? [...selectedPaths]
      : workDir
      ? [workDir]
      : [];

  async function handleGenerate() {
    const text = request.trim();
    if (!text || isGenerating) return;
    if (!selectedModel) {
      setError("Выберите модель в панели чата.");
      return;
    }

    setIsGenerating(true);
    setGeneratedContent("");
    setSuggestedFilename("");
    setSaveSuccess(null);
    setShowSaveRow(false);
    setError(null);

    let content = "";
    try {
      for await (const event of streamGenerate(
        text,
        format,
        contextPaths,
        selectedModel,
        thinkingEnabled,
      )) {
        if (event.type === "token") {
          content += event.content;
          setGeneratedContent(content);
          previewEndRef.current?.scrollIntoView({ behavior: "smooth" });
        } else if (event.type === "done") {
          setSuggestedFilename(event.suggested_filename);
          setSaveName(event.suggested_filename);
          setShowSaveRow(true);
        } else if (event.type === "error") {
          setError(event.msg);
        }
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setIsGenerating(false);
    }
  }

  async function handleSave() {
    if (!saveName.trim()) return;
    if (!workDir) {
      setError("Выберите папку для сохранения в левой панели.");
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      const result = await saveDocument(workDir, saveName.trim(), generatedContent);
      setSaveSuccess(result.name);
      setShowSaveRow(false);
      const tree = await getTree(workDir);
      setTree(tree);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="docgen-panel">
      <div className="docgen-toolbar">
        <div className="docgen-format-toggle">
          <button
            className={`docgen-fmt-btn${format === ".md" ? " active" : ""}`}
            onClick={() => setFormat(".md")}
          >
            Markdown
          </button>
          <button
            className={`docgen-fmt-btn${format === ".txt" ? " active" : ""}`}
            onClick={() => setFormat(".txt")}
          >
            Plain text
          </button>
        </div>
        <span className="docgen-context-badge" title={contextPaths.join(", ")}>
          {selectedPaths.size > 0 ? (
            <>
              <IconPaperclip size={11} />
              {selectedPaths.size} файл(ов)
            </>
          ) : workDir ? (
            <>
              <IconFolder size={11} />
              {workDir.split(/[\\/]/).pop() || workDir}
            </>
          ) : (
            "Без контекста"
          )}
        </span>
      </div>

      <div className="docgen-input-row">
        <textarea
          className="docgen-request-input"
          placeholder="Опишите документ, который нужно создать…"
          value={request}
          disabled={isGenerating}
          onChange={(e) => setRequest(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleGenerate();
            }
          }}
          rows={3}
        />
        <button
          className="docgen-gen-btn"
          onClick={handleGenerate}
          disabled={isGenerating || !request.trim()}
        >
          {isGenerating ? <Spinner size={14} /> : <IconSparkles size={14} />}
          {isGenerating ? "Создаю…" : "Создать"}
        </button>
      </div>

      {error && (
        <div className="alert alert-error docgen-alert">
          <IconAlertTriangle size={14} />
          {error}
        </div>
      )}

      {generatedContent && (
        <div className="docgen-preview">
          <div className="docgen-preview-header">
            Превью
            {suggestedFilename && (
              <span className="docgen-preview-filename">{suggestedFilename}</span>
            )}
          </div>
          <div className="docgen-preview-content">
            {format === ".md" ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>
                {generatedContent}
              </ReactMarkdown>
            ) : (
              <pre className="docgen-plain-text">{generatedContent}</pre>
            )}
            <div ref={previewEndRef} />
          </div>
        </div>
      )}

      {showSaveRow && generatedContent && (
        <div className="docgen-save-row">
          <input
            className="input docgen-save-input"
            type="text"
            value={saveName}
            onChange={(e) => setSaveName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSave();
            }}
            placeholder="Имя файла"
          />
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={isSaving || !saveName.trim()}
          >
            {isSaving ? <Spinner size={13} /> : <IconSave size={13} />}
            Сохранить
          </button>
        </div>
      )}

      {saveSuccess && (
        <div className="alert alert-success docgen-alert">
          <IconCheck size={14} />
          <span>
            Файл сохранён: <strong>{saveSuccess}</strong>
          </span>
        </div>
      )}
    </div>
  );
}
