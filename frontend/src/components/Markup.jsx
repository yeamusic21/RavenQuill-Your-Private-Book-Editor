// Renders paragraph text that uses RavenQuill's tiny markup: <i>…</i> and <b>…</b>.
// We parse it into React elements instead of using innerHTML, so manuscript
// text can never inject HTML into the page.

export function toSegments(text) {
  const segments = [];
  let italic = false;
  let bold = false;
  for (const part of text.split(/(<\/?[ib]>)/)) {
    if (part === "<i>") italic = true;
    else if (part === "</i>") italic = false;
    else if (part === "<b>") bold = true;
    else if (part === "</b>") bold = false;
    else if (part) segments.push({ text: part, i: italic, b: bold });
  }
  return segments;
}

function styled(seg, key, className) {
  let node = seg.text;
  if (seg.i) node = <em>{node}</em>;
  if (seg.b) node = <strong>{node}</strong>;
  return (
    <span key={key} className={className}>
      {node}
    </span>
  );
}

export function Markup({ text }) {
  return <>{toSegments(text).map((seg, n) => styled(seg, n))}</>;
}

// ops come from the backend: [{op: "equal"|"insert"|"delete", text, i, b}]
export function Diff({ ops }) {
  return <>{ops.map((op, n) => styled(op, n, op.op === "equal" ? undefined : op.op))}</>;
}

// Very small markdown renderer for the Story Architect report.
export function SimpleMarkdown({ text }) {
  const inline = (line) =>
    line.split(/(\*\*[^*]+\*\*)/).map((part, n) =>
      part.startsWith("**") && part.endsWith("**") ? <strong key={n}>{part.slice(2, -2)}</strong> : part
    );
  const blocks = [];
  let list = [];
  const flush = () => {
    if (list.length) blocks.push(<ul key={blocks.length}>{list}</ul>);
    list = [];
  };
  text.split("\n").forEach((raw, n) => {
    const line = raw.trim();
    if (/^#{1,4}\s/.test(line)) {
      flush();
      blocks.push(<h3 key={`h${n}`}>{inline(line.replace(/^#+\s*/, ""))}</h3>);
    } else if (/^([-*•]|\d+\.)\s/.test(line)) {
      list.push(<li key={n}>{inline(line.replace(/^([-*•]|\d+\.)\s*/, ""))}</li>);
    } else if (line) {
      flush();
      blocks.push(<p key={`p${n}`}>{inline(line)}</p>);
    }
  });
  flush();
  return <div className="markdown">{blocks}</div>;
}
