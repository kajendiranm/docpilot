import { useEffect, useRef, useState } from "react";
import { streamChat } from "../api/chat.js";
import Message from "./Message.jsx";

const EXAMPLES = [
  "How do I run the order service locally?",
  "Which service had the most incidents last month?",
  "The setup guide says Python 3.8 but we use 3.11, flag it.",
  "What's the office Wi-Fi password?",
  "Delete all incidents.",
  "How do we deploy payments, and how many deployments failed this week?",
];

function newAssistantMessage() {
  return { role: "assistant", content: "", tools: [], sources: [], pending: true };
}

export default function ChatWindow() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Apply a change to the last (streaming) assistant message.
  function updateLast(change) {
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      return [...prev.slice(0, -1), { ...last, ...change(last) }];
    });
  }

  function handleEvent(event, data) {
    switch (event) {
      case "token":
        updateLast((m) => ({ content: m.content + data.text }));
        break;
      case "tool_call":
        updateLast((m) => ({ tools: [...m.tools, { ...data, status: "running" }] }));
        break;
      case "tool_result":
        updateLast((m) => {
          // Results arrive in call order: fill in the oldest still-running call of this tool.
          const tools = [...m.tools];
          const idx = tools.findIndex((t) => t.tool === data.tool && t.status === "running");
          if (idx !== -1) {
            tools[idx] = { ...tools[idx], ...data, status: data.error ? "error" : "done" };
          }
          return { tools };
        });
        break;
      case "sources":
        updateLast(() => ({ sources: data }));
        break;
      case "done":
        updateLast(() => ({ pending: false, stats: data }));
        break;
      case "error":
        updateLast(() => ({ pending: false, error: data.message }));
        break;
      default:
        break;
    }
  }

  async function send(text) {
    const content = text.trim();
    if (!content || busy) return;

    // History is kept here on the client and sent with every request (no server sessions).
    // Failed or empty assistant turns are left out.
    const history = [...messages, { role: "user", content }]
      .filter((m) => m.role === "user" || (m.content && !m.error))
      .map(({ role, content }) => ({ role, content }));

    setMessages((prev) => [...prev, { role: "user", content }, newAssistantMessage()]);
    setInput("");
    setBusy(true);
    abortRef.current = new AbortController();
    try {
      await streamChat(history, handleEvent, abortRef.current.signal);
    } catch (err) {
      if (err.name !== "AbortError") {
        updateLast(() => ({ pending: false, error: `Could not reach DocPilot: ${err.message}` }));
      }
    } finally {
      updateLast(() => ({ pending: false }));
      setBusy(false);
    }
  }

  function onSubmit(e) {
    e.preventDefault();
    send(input);
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  }

  return (
    <div className="chat">
      <div className="messages">
        {messages.length === 0 && (
          <div className="empty">
            <h2>Ask about ShopFlow&apos;s docs, data or flag a problem</h2>
            <div className="examples">
              {EXAMPLES.map((q) => (
                <button key={q} onClick={() => send(q)}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <Message key={i} message={m} />
        ))}
        <div ref={bottomRef} />
      </div>

      <form className="composer" onSubmit={onSubmit}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask a question…  (Enter to send, Shift+Enter for a new line)"
          rows={2}
          disabled={busy}
        />
        {busy ? (
          <button type="button" onClick={() => abortRef.current?.abort()}>
            Stop
          </button>
        ) : (
          <button type="submit" disabled={!input.trim()}>
            Send
          </button>
        )}
      </form>
    </div>
  );
}
