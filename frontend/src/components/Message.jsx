import { Markdown } from "../markdown.jsx";
import SourceList from "./SourceList.jsx";
import ToolCallBadge from "./ToolCallBadge.jsx";

export default function Message({ message }) {
  if (message.role === "user") {
    return (
      <div className="message user">
        <div className="bubble">{message.content}</div>
      </div>
    );
  }

  const thinking = message.pending && !message.content && message.tools.length === 0;
  return (
    <div className="message assistant">
      <div className="bubble">
        {message.tools.length > 0 && (
          <div className="tools">
            {message.tools.map((call, i) => (
              <ToolCallBadge key={i} call={call} />
            ))}
          </div>
        )}
        {thinking && <div className="thinking">Thinking…</div>}
        {message.content && <Markdown text={message.content} />}
        {message.error && <div className="error">⚠️ {message.error}</div>}
        <SourceList sources={message.sources} />
        {message.stats && (
          <div className="stats">
            {(message.stats.latency_ms / 1000).toFixed(1)}s · first token{" "}
            {message.stats.first_token_ms != null
              ? `${(message.stats.first_token_ms / 1000).toFixed(1)}s`
              : "–"}{" "}
            · {message.stats.tool_calls} tool call{message.stats.tool_calls === 1 ? "" : "s"}
          </div>
        )}
      </div>
    </div>
  );
}
