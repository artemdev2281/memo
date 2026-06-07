import { useEffect, useState } from "react";
import { createChat, deleteChat, listChats, updateChat } from "../../api/chat";
import { useAppStore } from "../../store/useAppStore";
import "./ChatList.css";

export function ChatList() {
  const {
    chats,
    setChats,
    addChat,
    updateChatInList,
    removeChatFromList,
    activeChatId,
    setActiveChatId,
    setMessages,
    selectedModel,
    workDir,
    selectedPaths,
  } = useAppStore();

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState("");

  useEffect(() => {
    listChats().then(setChats).catch(() => {});
  }, []);

  async function handleNewChat() {
    const contextPaths = selectedPaths.size > 0
      ? [...selectedPaths]
      : workDir ? [workDir] : [];
    const contextType = contextPaths.length > 0
      ? (selectedPaths.size > 0 ? "files" : "folder")
      : "none";
    const chat = await createChat({
      model: selectedModel || "",
      context_type: contextType,
      context_paths: contextPaths,
    });
    addChat(chat);
    setActiveChatId(chat.id);
    setMessages([]);
  }

  async function handleDelete(e: React.MouseEvent, id: number) {
    e.stopPropagation();
    await deleteChat(id);
    removeChatFromList(id);
    if (activeChatId === id) {
      setActiveChatId(null);
      setMessages([]);
    }
  }

  function startEdit(e: React.MouseEvent, id: number, title: string) {
    e.stopPropagation();
    setEditingId(id);
    setEditTitle(title);
  }

  async function commitEdit(id: number) {
    if (editTitle.trim()) {
      const updated = await updateChat(id, { title: editTitle.trim() });
      updateChatInList(updated);
    }
    setEditingId(null);
  }

  return (
    <div className="chat-list">
      <div className="chat-list-header">
        <span className="chat-list-title">Чаты</span>
        <button className="chat-list-new-btn" onClick={handleNewChat} title="Новый чат">
          +
        </button>
      </div>
      <div className="chat-list-items">
        {chats.map((chat) => (
          <div
            key={chat.id}
            className={`chat-list-item${activeChatId === chat.id ? " active" : ""}`}
            onClick={() => {
              if (activeChatId === chat.id) return;
              setMessages([]);
              setActiveChatId(chat.id);
            }}
          >
            {editingId === chat.id ? (
              <div className="chat-list-item-edit" style={{ flex: 1 }}>
                <input
                  autoFocus
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  onBlur={() => commitEdit(chat.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitEdit(chat.id);
                    if (e.key === "Escape") setEditingId(null);
                  }}
                  onClick={(e) => e.stopPropagation()}
                />
              </div>
            ) : (
              <>
                <span className="chat-list-item-title" title={chat.title}>
                  {chat.title}
                </span>
                <div className="chat-list-item-actions">
                  <button
                    className="chat-action-btn"
                    title="Переименовать"
                    onClick={(e) => startEdit(e, chat.id, chat.title)}
                  >
                    ✏
                  </button>
                  <button
                    className="chat-action-btn"
                    title="Удалить"
                    onClick={(e) => handleDelete(e, chat.id)}
                  >
                    ✕
                  </button>
                </div>
              </>
            )}
          </div>
        ))}
        {chats.length === 0 && (
          <p style={{ color: "#666", fontSize: 12, padding: "8px 12px" }}>
            Нажмите + для нового чата
          </p>
        )}
      </div>
    </div>
  );
}
