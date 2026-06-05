import { Chat } from "./components/Chat/Chat";
import { ChatList } from "./components/ChatList/ChatList";
import { Layout } from "./components/Layout/Layout";
import { LeftPanel } from "./components/LeftPanel/LeftPanel";
import "./App.css";

function RightPanel() {
  return (
    <div style={{ display: "flex", height: "100%", overflow: "hidden" }}>
      <ChatList />
      <div style={{ flex: 1, overflow: "hidden" }}>
        <Chat />
      </div>
    </div>
  );
}

export default function App() {
  return <Layout left={<LeftPanel />} right={<RightPanel />} />;
}
