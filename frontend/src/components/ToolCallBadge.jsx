const LABELS = {
  search_docs: { icon: "🔍", running: "Searching docs…", done: "Searched docs" },
  run_sql: { icon: "🗄️", running: "Running SQL…", done: "Ran SQL" },
  create_github_issue: { icon: "🐙", running: "Creating GitHub issue…", done: "GitHub issue" },
};

export default function ToolCallBadge({ call }) {
  const label = LABELS[call.tool] ?? { icon: "🛠️", running: `${call.tool}…`, done: call.tool };
  const running = call.status === "running";
  // Show the SQL that actually ran (after validation + LIMIT), else what the model asked for.
  const sql = call.tool === "run_sql" ? (call.query ?? call.input?.query) : null;

  return (
    <div className={`tool-badge ${call.status}`}>
      <div className="tool-badge-row">
        <span className="tool-icon" aria-hidden="true">
          {label.icon}
        </span>
        <span>{running ? label.running : label.done}</span>
        {running && <span className="spinner" aria-label="working" />}
        {!running && call.summary && <span className="tool-summary">· {call.summary}</span>}
      </div>

      {call.tool === "search_docs" && call.input?.query && (
        <div className="tool-detail">query: “{call.input.query}”</div>
      )}

      {sql && (
        <details className="tool-sql">
          <summary>Show SQL</summary>
          <pre>
            <code>{sql}</code>
          </pre>
        </details>
      )}

      {call.tool === "create_github_issue" && call.url && !call.dry_run && (
        <a className="issue-link" href={call.url} target="_blank" rel="noreferrer">
          Open issue on GitHub ↗
        </a>
      )}
      {call.tool === "create_github_issue" && call.dry_run && (
        <div className="tool-detail">Dry run: no real issue was created (DRY_RUN=true).</div>
      )}
    </div>
  );
}
