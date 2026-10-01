// A tiny markdown renderer for chat answers: code blocks, lists, paragraphs, **bold**, links
// and `code`. It builds React elements (never raw HTML), so model output can't inject
// scripts. Enough for our answers without adding a markdown dependency.

const LINK_RE = /^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/;

function renderInline(text, keyPrefix) {
  // Split on `code`, **bold** and [links](https://...), keeping them as their own pieces.
  return text.split(/(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\(https?:\/\/[^)\s]+\))/g).map((piece, i) => {
    const key = `${keyPrefix}-${i}`;
    const link = piece.match(LINK_RE);
    if (link) {
      // Only http(s) URLs match the regex, so javascript: links can't get through.
      return (
        <a key={key} href={link[2]} target="_blank" rel="noreferrer">
          {link[1]}
        </a>
      );
    }
    if (piece.startsWith("`") && piece.endsWith("`") && piece.length > 1) {
      return <code key={key}>{piece.slice(1, -1)}</code>;
    }
    if (piece.startsWith("**") && piece.endsWith("**") && piece.length > 3) {
      return <strong key={key}>{piece.slice(2, -2)}</strong>;
    }
    return piece;
  });
}

export function Markdown({ text }) {
  const blocks = [];
  const lines = text.split("\n");
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim().startsWith("```")) {
      const code = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        code.push(lines[i]);
        i += 1;
      }
      i += 1; // closing fence (or end of a still-streaming answer)
      blocks.push(
        <pre key={blocks.length}>
          <code>{code.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    const listMatch = line.match(/^\s*(\d+\.|[-*])\s+/);
    if (listMatch) {
      const ordered = /\d/.test(listMatch[1]);
      // Keep the real number: a code block inside a list splits it into several <ol>s.
      const start = ordered ? parseInt(listMatch[1], 10) : undefined;
      const items = [];
      while (i < lines.length && /^\s*(\d+\.|[-*])\s+/.test(lines[i])) {
        const itemLines = [lines[i].replace(/^\s*(\d+\.|[-*])\s+/, "")];
        i += 1;
        // Indented continuation lines (but not code fences) belong to the same item.
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !lines[i].trim().startsWith("```")) {
          itemLines.push(lines[i].trim());
          i += 1;
        }
        items.push(
          <li key={items.length}>{renderInline(itemLines.join(" "), `li${items.length}`)}</li>,
        );
        // Let an indented code block inside a list item render, then continue the list.
        if (i < lines.length && lines[i].trim().startsWith("```")) break;
      }
      const List = ordered ? "ol" : "ul";
      blocks.push(
        <List key={blocks.length} start={start}>
          {items}
        </List>,
      );
      continue;
    }

    if (line.trim() === "") {
      i += 1;
      continue;
    }

    const para = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !lines[i].trim().startsWith("```") &&
      !/^\s*(\d+\.|[-*])\s+/.test(lines[i])
    ) {
      para.push(lines[i]);
      i += 1;
    }
    blocks.push(<p key={blocks.length}>{renderInline(para.join(" "), `p${blocks.length}`)}</p>);
  }

  return <div className="markdown">{blocks}</div>;
}
