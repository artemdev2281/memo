import { useEffect, useState } from "react";
import { apiFetch } from "./api/client";
import { Layout } from "./components/Layout/Layout";
import { LeftPanel } from "./components/LeftPanel/LeftPanel";
import "./App.css";

interface HealthStatus {
  status: string;
  ollama: boolean;
}

function RightPanel() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<HealthStatus>("/health")
      .then(setHealth)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <div className="panel-placeholder">
      <h3>AI Ассистент</h3>
      {!health && !error && (
        <span className="health-badge pending">⏳ Подключение к backend…</span>
      )}
      {error && <span className="health-badge err">✗ {error}</span>}
      {health && (
        <span className={`health-badge ${health.ollama ? "ok" : "warn"}`}>
          {health.ollama ? "✓ Ollama доступна" : "⚠ Ollama недоступна"}
        </span>
      )}
      <p style={{ marginTop: 16 }}>Q&A чат появится в Этапе 2.</p>
    </div>
  );
}

export default function App() {
  return <Layout left={<LeftPanel />} right={<RightPanel />} />;
}
