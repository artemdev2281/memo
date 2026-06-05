import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { listMessages, listModels, streamMessage } from "../../api/chat";
import { useAppStore } from "../../store/useAppStore";
import "./Chat.css";

function parseThink(raw: string): { thinking: string; answer: string; isThinking: boolean } {
  const open = raw.indexOf("<think>");
  if (open === -1) return { thinking: "", answer: raw, isThinking: false };
  const close = raw.indexOf("</think>", open);
  if (close === -1) {
    return {
      thinking: raw.slice(open + 7),
      answer: raw.slice(0, open),
      isThinking: true,
    };
  }
  return {
    thinking: raw.slice(open + 7, close),
    answer: (raw.slice(0, open) + raw.slice(close + 8)).trimStart(),
    isThinking: false,
  };
}

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
    selectedModel,
    setSelectedModel,
    availableModels,
    setAvailableModels,
    isStreaming,
    setIsStreaming,
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
  const [isThinking, setIsThinking] = useState(false);
  const [thinkMap, setThinkMap] = useState<Record<number, string>>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listModels()
      .then((models) => {
        setAvailableModels(models);
        if (!selectedModel && models.length > 0) {
          const preferred = models.find((m) => m.startsWith("qwen3")) ?? models[0];
          setSelectedModel(preferred);
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (activeChatId !== null) {
      let cancelled = false;
      listMessages(activeChatId)
        .then((msgs) => { if (!cancelled) setMessages(msgs); })
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
    if (!text || isStreaming) return;
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
    setIsStreaming(true);
    setIsThinking(false);

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
      created_at: new Date().toISOString(),
    };
    appendMessage(assistantMsg);

    let fullContent = "";
    let finalSources: string[] = [];

    try {
      for await (const event of streamMessage(chatId, text, selectedModel, contextPaths, thinkingEnabled)) {
        if (useAppStore.getState().activeChatId !== chatId) break;
        if (event.type === "token") {
          fullContent += event.content;
          const { thinking, answer, isThinking: inThink } = parseThink(fullContent);
          setIsThinking(inThink);
          if (thinkingEnabled && thinking) {
            setThinkMap((prev) => ({ ...prev, [assistantMsg.id]: thinking }));
          }
          updateLastAssistantMessage(thinkingEnabled ? answer : answer);
        } else if (event.type === "done") {
          setIsThinking(false);
          finalSources = event.sources;
          const { thinking, answer } = parseThink(fullContent);
          if (thinkingEnabled && thinking) {
            setThinkMap((prev) => ({ ...prev, [assistantMsg.id]: thinking }));
          }
          updateLastAssistantMessage(answer);
          setMessages(
            useAppStore.getState().messages.map((m) =>
              m.id === assistantMsg.id
                ? { ...m, content: answer, sources: finalSources }
                : m,
            ),
          );
        } else if (event.type === "error") {
          setIsThinking(false);
          setStreamError(event.msg);
          updateLastAssistantMessage(fullContent || "(ошибка)");
        }
      }
    } catch (e) {
      setIsThinking(false);
      setStreamError((e as Error).message);
    } finally {
      setIsStreaming(false);
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
        {messages.length === 0 && !isStreaming && (
          <div className="chat-empty">Задайте вопрос по выбранным документам</div>
        )}
        {messages.map((msg) => (
          <div key={msg.id} className={`chat-message ${msg.role}`}>
            {msg.role === "assistant" && thinkingEnabled && (
              <>
                {isStreaming && isThinking && msg === messages[messages.length - 1] && (
                  <div className="chat-thinking-status">
                    <span className="chat-thinking-dots">Думаю</span>
                  </div>
                )}
                {thinkMap[msg.id] && (
                  <details className="chat-think-block">
                    <summary>Рассуждения</summary>
                    <div className="chat-think-content">{thinkMap[msg.id]}</div>
                  </details>
                )}
              </>
            )}
            <div className="chat-message-content">
              {msg.role === "assistant" ? (
                msg.content ? (
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                ) : (
                  !isThinking && <span style={{ color: "#555" }}>…</span>
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
        ))}
        {streamError && <div className="chat-error-msg">⚠ {streamError}</div>}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-row">
        <textarea
          className="chat-input"
          placeholder="Задайте вопрос…"
          value={input}
          disabled={isStreaming}
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
          disabled={isStreaming || !input.trim()}
          title="Отправить (Enter)"
        >
          ➤
        </button>
      </div>
    </div>
  );
}
