import { useState } from "react";

export default function SourceList({ sources }) {
  const [open, setOpen] = useState(false);
  if (!sources?.length) return null;

  return (
    <div className="sources">
      <button className="sources-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? "▾" : "▸"} Sources ({sources.length})
      </button>
      {open && (
        <ul>
          {sources.map((s) => (
            <li key={`${s.path}-${s.section}`}>
              <span className="source-path">{s.path}</span> › {s.section}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
