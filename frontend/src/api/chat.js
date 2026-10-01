// SSE client for POST /api/chat.
// The browser's EventSource only supports GET, so we POST with fetch and parse the
// "event: <name>\ndata: <json>\n\n" frames from the response stream ourselves.

export async function streamChat(messages, onEvent, signal) {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
    signal,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Server returned ${response.status}: ${detail.slice(0, 200)}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // A frame ends with a blank line; keep any incomplete frame in the buffer.
    const frames = buffer.split("\n\n");
    buffer = frames.pop();
    for (const frame of frames) {
      const parsed = parseFrame(frame);
      if (parsed) onEvent(parsed.event, parsed.data);
    }
  }
}

function parseFrame(frame) {
  let event = "message";
  const dataLines = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event: ")) event = line.slice(7);
    else if (line.startsWith("data: ")) dataLines.push(line.slice(6));
  }
  if (dataLines.length === 0) return null;
  return { event, data: JSON.parse(dataLines.join("\n")) };
}

export async function fetchHealth() {
  const response = await fetch("/api/health");
  if (!response.ok) throw new Error(`health ${response.status}`);
  return response.json();
}
