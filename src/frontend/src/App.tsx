import { Chat } from "./components/Chat/Chat";
import { ChatList } from "./components/ChatList/ChatList";
import { DocGenerator } from "./components/DocGenerator/DocGenerator";
import { Layout } from "./components/Layout/Layout";
import { LeftPanel } from "./components/LeftPanel/LeftPanel";
import { useAppStore } from "./store/useAppStore";
import "./App.css";

function RightPanel() {
  const { rightPanelMode, setRightPanelMode } = useAppStore();

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <div className="right-panel-mode-bar">
        <button
          className={`right-panel-mode-btn${rightPanelMode === "chat" ? " active" : ""}`}
          onClick={() => setRightPanelMode("chat")}
        >
          💬 Чат
        </button>
        <button
          className={`right-panel-mode-btn${rightPanelMode === "generate" ? " active" : ""}`}
          onClick={() => setRightPanelMode("generate")}
        >
          📝 Создать документ
        </button>
      </div>
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {rightPanelMode === "chat" ? (
          <>
            <ChatList />
            <div style={{ flex: 1, overflow: "hidden" }}>
              <Chat />
            </div>
          </>
        ) : (
          <div style={{ flex: 1, overflow: "hidden" }}>
            <DocGenerator />
          </div>
        )}
      </div>
    </div>
  );
}

export default function App() {
  return <Layout left={<LeftPanel />} right={<RightPanel />} />;
}
