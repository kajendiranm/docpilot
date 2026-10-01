import { useEffect, useState } from "react";
import { fetchHealth } from "./api/chat.js";
import ChatWindow from "./components/ChatWindow.jsx";

export default function App() {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth({ status: "down", checks: {} }));
  }, []);

  const title = health
    ? Object.entries(health.checks)
        .map(([name, state]) => `${name}: ${state}`)
        .join("\n") || "backend unreachable"
    : "checking…";

  return (
    <div className="app">
      <header>
        <h1>
          DocPilot <span className="tagline">engineering docs, data and actions</span>
        </h1>
        <span className={`health ${health?.status ?? "checking"}`} title={title}>
          ● {health ? health.status : "checking"}
        </span>
      </header>
      <ChatWindow />
    </div>
  );
}
