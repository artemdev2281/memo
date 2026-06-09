import { Chat } from "./components/Chat/Chat";
import { ChatList } from "./components/ChatList/ChatList";
import { DocGenerator } from "./components/DocGenerator/DocGenerator";
import { IconFileText, IconMessage } from "./components/Icon/Icon";
import { Layout } from "./components/Layout/Layout";
import { LeftPanel } from "./components/LeftPanel/LeftPanel";
import { useAppStore } from "./store/useAppStore";
import "./App.css";

function RightPanel() {
  const { rightPanelMode } = useAppStore();

  return (
    <div className="right-panel">
      {rightPanelMode === "chat" ? (
        <>
          <ChatList />
          <div className="right-panel-main">
            <Chat />
          </div>
        </>
      ) : (
        <div className="right-panel-main">
          <DocGenerator />
        </div>
      )}
    </div>
  );
}

export default function App() {
  const { rightPanelMode, setRightPanelMode } = useAppStore();

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-brand">
          <span className="app-logo" aria-hidden />
          memo
        </div>
        <nav className="app-tabs">
          <button
            className={`app-tab${rightPanelMode === "chat" ? " active" : ""}`}
            onClick={() => setRightPanelMode("chat")}
          >
            <IconMessage size={14} />
            Чат
          </button>
          <button
            className={`app-tab${rightPanelMode === "generate" ? " active" : ""}`}
            onClick={() => setRightPanelMode("generate")}
          >
            <IconFileText size={14} />
            Создать документ
          </button>
        </nav>
      </header>
      <div className="app-body">
        <Layout left={<LeftPanel />} right={<RightPanel />} />
      </div>
    </div>
  );
}
