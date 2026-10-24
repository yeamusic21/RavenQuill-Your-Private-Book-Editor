import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, stageName } from "../api.js";
import { Diff, Markup } from "../components/Markup.jsx";

const FILTERS = {
  all: { label: "All", test: () => true },
  changed: { label: "Changed", test: (p) => p.changed },
  unreviewed: { label: "Needs review", test: (p) => p.changed && !p.reviewed },
  flagged: { label: "Flagged", test: (p) => p.flagged },
};

export default function ReviewPage() {
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const [chapters, setChapters] = useState([]);
  const [paragraphs, setParagraphs] = useState(null);
  const [filter, setFilter] = useState("all");
  const [showChanges, setShowChanges] = useState(true);
  const [error, setError] = useState("");
  const chapterId = Number(params.get("chapter")) || chapters[0]?.id;

  const loadChapters = useCallback(
    () => api.get(`/projects/${id}/chapters`).then(setChapters).catch((e) => setError(e.message)),
    [id]
  );
  useEffect(() => {
    loadChapters();
  }, [loadChapters]);

  useEffect(() => {
    if (!chapterId) return;
    setParagraphs(null);
    api.get(`/chapters/${chapterId}/paragraphs`).then(setParagraphs).catch((e) => setError(e.message));
  }, [chapterId]);

  const replace = useCallback(
    (updated) => {
      setParagraphs((list) => list.map((p) => (p.id === updated.id ? updated : p)));
      loadChapters();
    },
    [loadChapters]
  );

  const visible = paragraphs?.filter(FILTERS[filter].test) ?? [];
  const chapterIndex = chapters.findIndex((c) => c.id === chapterId);

  function nextNeedingReview() {
    const el = document.querySelector(".row.needs-review");
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    const next = chapters.find((c, n) => n > chapterIndex && c.unreviewed > 0) ?? chapters.find((c) => c.unreviewed > 0);
    if (next && next.id !== chapterId) setParams({ chapter: next.id });
  }

  return (
    <div className="review">
      <aside className="chapters">
        <Link to={`/projects/${id}`} className="back">
          ← Project
        </Link>
        <h3>Chapters</h3>
        <ol>
          {chapters.map((c) => (
            <li key={c.id}>
              <button className={c.id === chapterId ? "active" : ""} onClick={() => setParams({ chapter: c.id })}>
                <span className="chapter-title">{c.title}</span>
                {c.unreviewed > 0 ? (
                  <span className="badge" title="Changed paragraphs not yet reviewed">
                    {c.unreviewed}
                  </span>
                ) : c.changed > 0 ? (
                  <span className="badge done" title="All changes reviewed">
                    ✓
                  </span>
                ) : null}
              </button>
            </li>
          ))}
        </ol>
      </aside>

      <main className="review-main">
        <div className="review-toolbar">
          <div className="segmented">
            {Object.entries(FILTERS).map(([key, f]) => (
              <button key={key} className={filter === key ? "active" : ""} onClick={() => setFilter(key)}>
                {f.label}
              </button>
            ))}
          </div>
          <label className="toggle">
            <input type="checkbox" checked={showChanges} onChange={(e) => setShowChanges(e.target.checked)} /> Highlight
            changes
          </label>
          <button onClick={nextNeedingReview}>Next to review ↓</button>
          <span className="muted hint">Click edited text to change it · Ctrl+Enter saves</span>
        </div>

        {error && <p className="error">{error}</p>}

        <div className="columns-header">
          <div>Original</div>
          <div />
          <div>Edited</div>
        </div>

        {paragraphs === null && <p className="muted pad">Loading…</p>}
        {paragraphs && visible.length === 0 && <p className="muted pad">Nothing matches this filter in this chapter.</p>}
        {visible.map((p) => (
          <Row key={p.id} p={p} showChanges={showChanges} onUpdate={replace} />
        ))}

        {chapterIndex >= 0 && chapterIndex < chapters.length - 1 && (
          <div className="pad">
            <button onClick={() => { setParams({ chapter: chapters[chapterIndex + 1].id }); window.scrollTo(0, 0); }}>
              Next chapter: {chapters[chapterIndex + 1].title} →
            </button>
          </div>
        )}
      </main>
    </div>
  );
}

function Row({ p, showChanges, onUpdate }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(p.current);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const textarea = useRef(null);

  useEffect(() => {
    if (editing && textarea.current) {
      textarea.current.focus();
      autosize(textarea.current);
    }
  }, [editing]);

  async function call(promise) {
    setSaving(true);
    try {
      onUpdate(await promise);
      setEditing(false);
    } catch (e) {
      alert(e.message);
    } finally {
      setSaving(false);
    }
  }

  const save = () => call(api.patch(`/paragraphs/${p.id}`, { current: draft }));
  const startEdit = () => {
    setDraft(p.current);
    setEditing(true);
  };

  const className = ["row", p.kind, p.changed && !p.reviewed ? "needs-review" : "", p.flagged ? "flagged" : ""]
    .filter(Boolean)
    .join(" ");
  const marker = p.flagged ? "⚑" : p.changed ? (p.reviewed ? "✓" : "●") : "";
  const markerTitle = p.flagged
    ? "An editor suggested a change that failed the safety checks. Click to see it."
    : p.changed
      ? `Changed by ${p.edited_by.map(stageName).join(", ")}${p.reviewed ? " · reviewed" : ""}. Click for history.`
      : "Unchanged";

  if (p.kind === "scene_break") {
    return (
      <div className={className}>
        <div className="cell scene">* * *</div>
        <div className="gutter" />
        <div className="cell scene">* * *</div>
      </div>
    );
  }

  return (
    <>
      <div className={className}>
        <div className="cell original">
          <Markup text={p.original} />
        </div>
        <div className="gutter">
          {marker && (
            <button className={`marker ${p.reviewed ? "reviewed" : ""}`} title={markerTitle} onClick={() => setOpen(!open)}>
              {marker}
            </button>
          )}
        </div>
        <div className="cell edited">
          {editing ? (
            <div className="editor">
              <textarea
                ref={textarea}
                value={draft}
                onChange={(e) => {
                  setDraft(e.target.value);
                  autosize(e.target);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) save();
                  if (e.key === "Escape") setEditing(false);
                }}
              />
              <div className="editor-actions">
                <button className="primary small" disabled={saving} onClick={save}>
                  Save
                </button>
                <button className="small" onClick={() => setEditing(false)}>
                  Cancel
                </button>
                <span className="muted small-text">Use &lt;i&gt;…&lt;/i&gt; for italics</span>
              </div>
            </div>
          ) : (
            <div className="text" onClick={startEdit} title="Click to edit">
              {p.changed && showChanges ? <Diff ops={p.diff} /> : <Markup text={p.current} />}
            </div>
          )}
          {!editing && (p.changed || Boolean(p.flagged)) && (
            <div className="row-actions">
              <button
                className="small"
                onClick={() => call(api.patch(`/paragraphs/${p.id}`, { reviewed: !p.reviewed, flagged: false }))}
              >
                {p.reviewed ? "Mark unreviewed" : "✓ Looks good"}
              </button>
              {p.changed && (
                <button className="small" onClick={() => call(api.post(`/paragraphs/${p.id}/revert`))}>
                  Use original
                </button>
              )}
            </div>
          )}
        </div>
      </div>
      {open && <History p={p} onApply={(edit) => call(api.post(`/edits/${edit.id}/apply`))} />}
    </>
  );
}

function History({ p, onApply }) {
  return (
    <div className="history">
      {p.edits.length === 0 && <p className="muted">No edits.</p>}
      {p.edits.map((e) => (
        <div key={e.id} className={`history-item ${e.status}`}>
          <div className="history-head">
            <strong>{stageName(e.stage)}</strong>
            <span className={`status status-${e.status === "applied" ? "done" : "error"}`}>
              {e.status === "applied" ? "applied" : "held back"}
            </span>
            {e.note && <span className="muted">{e.note}</span>}
            {e.status === "rejected" && (
              <button className="small" onClick={() => onApply(e)}>
                Use this version
              </button>
            )}
          </div>
          <div className="history-text">
            <Markup text={e.after} />
          </div>
        </div>
      ))}
    </div>
  );
}

function autosize(el) {
  el.style.height = "auto";
  el.style.height = `${el.scrollHeight + 2}px`;
}
