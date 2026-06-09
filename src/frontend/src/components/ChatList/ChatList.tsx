import { useEffect, useState } from "react";
import { createChat, deleteChat, listChats, updateChat } from "../../api/chat";
import { useAppStore } from "../../store/useAppStore";
import { IconPencil, IconPlus, IconTrash } from "../Icon/Icon";
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
  const [listError, setListError] = useState<string | null>(null);

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
    setListError(null);
    try {
      const chat = await createChat({
        model: selectedModel || "",
        context_type: contextType,
        context_paths: contextPaths,
      });
      addChat(chat);
      setActiveChatId(chat.id);
      setMessages([]);
    } catch (e) {
      setListError(`Не удалось создать чат: ${(e as Error).message}`);
    }
  }

  async function handleDelete(e: React.MouseEvent, id: number) {
    e.stopPropagation();
    try {
      await deleteChat(id);
    } catch (err) {
      setListError(`Не удалось удалить чат: ${(err as Error).message}`);
      return;
    }
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
      try {
        const updated = await updateChat(id, { title: editTitle.trim() });
        updateChatInList(updated);
      } catch {
        // keep the old title on failure
      }
    }
    setEditingId(null);
  }

  return (
    <div className="chat-list">
      <div className="chat-list-header">
        <span className="chat-list-title">Чаты</span>
        <button className="chat-list-new-btn" onClick={handleNewChat} title="Новый чат">
          <IconPlus size={14} />
        </button>
      </div>
      {listError && <div className="chat-list-error">{listError}</div>}
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
              <div className="chat-list-item-edit">
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
                    <IconPencil size={12} />
                  </button>
                  <button
                    className="chat-action-btn chat-action-danger"
                    title="Удалить"
                    onClick={(e) => handleDelete(e, chat.id)}
                  >
                    <IconTrash size={12} />
                  </button>
                </div>
              </>
            )}
          </div>
        ))}
        {chats.length === 0 && (
          <p className="chat-list-empty">Нажмите + для нового чата</p>
        )}
      </div>
    </div>
  );
}
