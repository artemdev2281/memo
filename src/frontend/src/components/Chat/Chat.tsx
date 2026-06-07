import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { listMessages, listModels, streamMessage } from "../../api/chat";
import { useAppStore } from "../../store/useAppStore";
import "./Chat.css";

function ContextBadge() {
  const { workDir, selectedPaths } = useAppStore();
  if (selectedPaths.size > 0) {
    return (
      <span className="chat-context-badge" title={[...selectedPaths].join(", ")}>
        📎 {selectedPaths.size} файл(ов)
      </span>
    );
  }
  if (workDir) {
    return (
      <span className="chat-context-badge" title={workDir}>
        📁 {workDir.split(/[\\/]/).pop() || workDir}
      </span>
    );
  }
  return <span className="chat-context-badge">Без контекста</span>;
}

export function Chat() {
  const {
    activeChatId,
    messages,
    setMessages,
    appendMessage,
    updateLastAssistantMessage,
    updateLastAssistantThinking,
    selectedModel,
    setSelectedModel,
    availableModels,
    setAvailableModels,
    streamingChatId,
    setStreamingChatId,
    selectedPaths,
    workDir,
    chats,
    addChat,
    setActiveChatId,
    thinkingEnabled,
    setThinkingEnabled,
  } = useAppStore();

  const [input, setInput] = useState("");
  const [streamError, setStreamError] = useState<string | null>(null);
  const [indexingStatus, setIndexingStatus] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // True while THIS chat (the one on screen) is streaming.
  const activeStreaming = streamingChatId !== null && streamingChatId === activeChatId;

  useEffect(() => {
    let cancelled = false;
    listModels()
      .then((models) => {
        if (cancelled) return;
        setAvailableModels(models);
        if (!selectedModel && models.length > 0) {
          const preferred = models.find((m) => m.startsWith("qwen3")) ?? models[0];
          setSelectedModel(preferred);
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (activeChatId !== null) {
      let cancelled = false;
      const loadForId = activeChatId;
      listMessages(loadForId)
        .then((msgs) => {
          // Skip if the request was cancelled (chat switched again) OR if we
          // are actively streaming into this very chat. In the latter case the
          // optimistic messages appended by handleSend are still live — calling
          // setMessages([]) would wipe them before the stream finishes.
          if (!cancelled && useAppStore.getState().streamingChatId !== loadForId) {
            setMessages(msgs);
          }
        })
        .catch(() => {});
      return () => { cancelled = true; };
    }
  }, [activeChatId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const contextPaths =
    selectedPaths.size > 0
      ? [...selectedPaths]
      : workDir
      ? [workDir]
      : [];

  async function handleSend() {
    const text = input.trim();
    if (!text || activeStreaming) return;
    if (!selectedModel) {
      setStreamError("Выберите модель из списка выше.");
      return;
    }

    let chatId = activeChatId;
    if (chatId === null) {
      const { createChat } = await import("../../api/chat");
      const chat = await createChat({
        model: selectedModel,
        context_type: contextPaths.length > 0 ? (selectedPaths.size > 0 ? "files" : "folder") : "none",
        context_paths: contextPaths,
      });
      addChat(chat);
      setActiveChatId(chat.id);
      chatId = chat.id;
    }

    setInput("");
    setStreamError(null);
    setIndexingStatus(null);
    setStreamingChatId(chatId);

    const userMsg = {
      id: Date.now(),
      chat_id: chatId,
      role: "user" as const,
      content: text,
      sources: [],
      created_at: new Date().toISOString(),
    };
    appendMessage(userMsg);

    const assistantMsg = {
      id: Date.now() + 1,
      chat_id: chatId,
      role: "assistant" as const,
      content: "",
      sources: [],
      thinking: "",
      created_at: new Date().toISOString(),
    };
    appendMessage(assistantMsg);

    let fullContent = "";
    let fullThinking = "";
    let finalSources: string[] = [];

    try {
      for await (const event of streamMessage(chatId, text, selectedModel, contextPaths, thinkingEnabled)) {
        if (useAppStore.getState().activeChatId !== chatId) break;
        if (event.type === "indexing") {
          const name = event.file.split(/[\\/]/).pop() || event.file;
          setIndexingStatus(`Индексация: ${name} (${event.done}/${event.total})`);
        } else if (event.type === "token") {
          setIndexingStatus(null);
          fullContent += event.content;
          updateLastAssistantMessage(fullContent);
        } else if (event.type === "thinking") {
          setIndexingStatus(null);
          fullThinking += event.content;
          updateLastAssistantThinking(fullThinking);
        } else if (event.type === "done") {
          finalSources = event.sources;
          setMessages(
            useAppStore.getState().messages.map((m) =>
              m.id === assistantMsg.id
                ? { ...m, content: fullContent, thinking: fullThinking || null, sources: finalSources }
                : m,
            ),
          );
        } else if (event.type === "error") {
          setStreamError(event.msg);
          updateLastAssistantMessage(fullContent || "(ошибка)");
        }
      }
    } catch (e) {
      setStreamError((e as Error).message);
    } finally {
      setIndexingStatus(null);
      if (useAppStore.getState().streamingChatId === chatId) {
        setStreamingChatId(null);
      }
    }
  }

  if (activeChatId === null && chats.length === 0) {
    return (
      <div className="chat-panel">
        <div className="chat-no-chat">
          <p>Создайте чат для начала работы</p>
          <button
            className="chat-no-chat-btn"
            onClick={async () => {
              const { createChat } = await import("../../api/chat");
              const chat = await createChat({
                model: selectedModel || "",
                context_type: contextPaths.length > 0 ? (selectedPaths.size > 0 ? "files" : "folder") : "none",
                context_paths: contextPaths,
              });
              addChat(chat);
              setActiveChatId(chat.id);
            }}
          >
            + Новый чат
          </button>
        </div>
      </div>
    );
  }

  const lastMsg = messages[messages.length - 1];

  return (
    <div className="chat-panel">
      <div className="chat-toolbar">
        <select
          className="chat-model-select"
          value={selectedModel}
          onChange={(e) => setSelectedModel(e.target.value)}
        >
          {availableModels.length === 0 && (
            <option value="">— Ollama недоступна —</option>
          )}
          {availableModels.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
        <button
          className={`chat-think-toggle${thinkingEnabled ? " active" : ""}`}
          onClick={() => setThinkingEnabled(!thinkingEnabled)}
          title={thinkingEnabled ? "Режим рассуждений включён" : "Режим рассуждений выключен"}
        >
          💭
        </button>
        <ContextBadge />
      </div>

      <div className="chat-messages">
        {messages.length === 0 && !activeStreaming && (
          <div className="chat-empty">Задайте вопрос по выбранным документам</div>
        )}
        {messages.map((msg) => {
          const isLast = msg === lastMsg;
          const showThinkingStatus =
            msg.role === "assistant" &&
            isLast &&
            activeStreaming &&
            !!msg.thinking &&
            !msg.content;
          const showIndexingStatus =
            msg.role === "assistant" && isLast && activeStreaming && !!indexingStatus && !msg.content;
          return (
            <div key={msg.id} className={`chat-message ${msg.role}`}>
              {msg.role === "assistant" && showIndexingStatus && (
                <div className="chat-thinking-status">
                  <span className="chat-thinking-dots">{indexingStatus}</span>
                </div>
              )}
              {msg.role === "assistant" && showThinkingStatus && !showIndexingStatus && (
                <div className="chat-thinking-status">
                  <span className="chat-thinking-dots">Думаю</span>
                </div>
              )}
              {msg.role === "assistant" && msg.thinking && (
                <details className="chat-think-block">
                  <summary>Рассуждения</summary>
                  <div className="chat-think-content">{msg.thinking}</div>
                </details>
              )}
              <div className="chat-message-content">
                {msg.role === "assistant" ? (
                  msg.content ? (
                    <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>
                      {msg.content}
                    </ReactMarkdown>
                  ) : (
                    !showThinkingStatus && !showIndexingStatus && <span style={{ color: "#555" }}>…</span>
                  )
                ) : (
                  <p>{msg.content}</p>
                )}
              </div>
              {msg.role === "assistant" && msg.sources.length > 0 && (
                <div className="chat-sources">
                  {msg.sources.map((s) => (
                    <span key={s} className="chat-source-chip">
                      {s}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
        {streamError && <div className="chat-error-msg">⚠ {streamError}</div>}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-row">
        <textarea
          className="chat-input"
          placeholder="Задайте вопрос…"
          value={input}
          disabled={activeStreaming}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          rows={1}
        />
        <button
          className="chat-send-btn"
          onClick={handleSend}
          disabled={activeStreaming || !input.trim()}
          title="Отправить (Enter)"
        >
          ➤
        </button>
      </div>
    </div>
  );
}
