import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api.js";
import { PersonaModal } from "../components/PersonaInfo.jsx";

const SETTLED_LABEL = { fixed: "Fixed", rejected: "Rejected", explained: "Explained" };

export default function OutlinePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [outline, setOutline] = useState(null);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [learnMore, setLearnMore] = useState(false);

  const receive = useCallback((o, keepText) => {
    setOutline(o);
    if (!keepText) setText(o.text);
  }, []);

  useEffect(() => {
    setError("");
    api.get(`/outlines/${id}`).then((o) => receive(o)).catch((e) => setError(e.message));
  }, [id, receive]);

  // Poll while the Outline Doctor is reading. Keep the author's unsaved typing.
  const reviewing = outline?.status === "reviewing";
  useEffect(() => {
    if (!reviewing) return;
    const timer = setInterval(() => api.get(`/outlines/${id}`).then((o) => receive(o, true)), 2000);
    return () => clearInterval(timer);
  }, [reviewing, id, receive]);

  if (!outline) return <main className="page">{error ? <p className="error">{error}</p> : <p className="muted">Loading…</p>}</main>;

  const dirty = text.trim() !== outline.text;
  const open = outline.holes.filter((h) => h.status === "open");
  const settled = outline.holes.filter((h) => h.status !== "open");
  const last = outline.rounds.at(-1);

  async function save() {
    receive(await api.patch(`/outlines/${id}`, { text }), true);
  }

  async function check() {
    setError("");
    try {
      if (dirty) await save();
      receive(await api.post(`/outlines/${id}/review`), true);
    } catch (e) {
      setError(e.message);
    }
  }

  async function answer(hole, status, response = "") {
    setError("");
    try {
      receive(await api.patch(`/holes/${hole.id}`, { status, response }), true);
    } catch (e) {
      setError(e.message);
    }
  }

  async function rename() {
    const name = prompt("Outline name", outline.name);
    if (name?.trim()) receive(await api.patch(`/outlines/${id}`, { name }), true);
  }

  async function remove() {
    if (!confirm(`Delete “${outline.name}” and all its rounds? This cannot be undone.`)) return;
    await api.del(`/outlines/${id}`);
    navigate("/outlines");
  }

  return (
    <main className="page">
      <div className="page-header">
        <div>
          <h1>
            {outline.name}{" "}
            <button className="link rename" onClick={rename}>
              rename
            </button>
          </h1>
          <p className="muted">
            {outline.words.toLocaleString()} words · {outline.rounds.length} round{outline.rounds.length === 1 ? "" : "s"} ·{" "}
            {open.length} hole{open.length === 1 ? "" : "s"} open
          </p>
        </div>
        <a className="button" href={`/api/outlines/${id}/export`}>
          Download report (.md)
        </a>
      </div>

      <div className="outline-layout">
        <section className="card outline-editor">
          <div className="outline-head">
            <h2>Outline</h2>
            {dirty && <span className="muted small-text">Unsaved changes</span>}
            <button className="small" disabled={!dirty} onClick={save}>
              Save
            </button>
          </div>
          <textarea value={text} onChange={(e) => setText(e.target.value)} spellCheck />
          <p className="muted small-text">Fix holes here, then press Check again. Your changes are saved before each check.</p>
        </section>

        <section className="card">
          <div className="outline-head">
            <h2>Holes</h2>
            <button className="link small-text" onClick={() => setLearnMore(true)}>
              About the Outline Doctor
            </button>
          </div>
          <div className="actions">
            <button className="primary" disabled={reviewing || !text.trim()} onClick={check}>
              {reviewing ? "Outline Doctor is reading…" : outline.rounds.length ? "Check again" : "Check for holes"}
            </button>
            {last && !reviewing && (
              <span className="muted small-text">
                Round {last.round}: {last.new_holes} new, {last.fixed_holes} fixed
              </span>
            )}
          </div>
          {reviewing && <div className="progress indeterminate"><div /></div>}
          {outline.status === "error" && <p className="error">{outline.error}</p>}
          {error && <p className="error">{error}</p>}

          <Verdict outline={outline} open={open} last={last} dirty={dirty} reviewing={reviewing} />

          {open.map((h) => (
            <HoleCard key={h.id} hole={h} onAnswer={answer} disabled={reviewing} />
          ))}

          {settled.length > 0 && (
            <details className="settled">
              <summary>Settled ({settled.length})</summary>
              {settled.map((h) => (
                <div key={h.id} className="hole settled-hole">
                  <div className="hole-head">
                    <span className={`status status-${h.status}`}>{SETTLED_LABEL[h.status]}</span>
                    <strong>{h.title}</strong>
                    <button className="small" disabled={reviewing} onClick={() => answer(h, "open")}>
                      Reopen
                    </button>
                  </div>
                  {h.response && <p className="small-text"><span className="muted">You:</span> {h.response}</p>}
                  {h.resolved_round && <p className="muted small-text">Outline Doctor confirmed the fix in round {h.resolved_round}.</p>}
                </div>
              ))}
            </details>
          )}
        </section>
      </div>

      <div className="danger-zone">
        <button className="danger" onClick={remove}>
          Delete outline
        </button>
      </div>
      {learnMore && <PersonaModal stageId="outline" onClose={() => setLearnMore(false)} />}
    </main>
  );
}

function Verdict({ outline, open, last, dirty, reviewing }) {
  if (!last || reviewing || open.length) return null;
  const changed = dirty || !last.same_text;
  if (last.new_holes === 0)
    return (
      <p className="verdict">
        ✓ No holes left. {changed ? "You've changed the outline since, so check again to be sure." : "The outline holds together."}
      </p>
    );
  return (
    <p className="verdict">
      ✓ Every hole is fixed, rejected or explained.{" "}
      {changed ? "Check again to confirm your changes didn't open new ones." : "Check again if you'd like a fresh look."}
    </p>
  );
}

function HoleCard({ hole, onAnswer, disabled }) {
  const [mode, setMode] = useState(null); // null | "explained" | "rejected"
  const [response, setResponse] = useState("");

  return (
    <div className={`hole hole-${hole.severity}`}>
      <div className="hole-head">
        <strong>{hole.title}</strong>
        <span className="muted small-text">
          {[hole.location, hole.severity, `round ${hole.round}`].filter(Boolean).join(" · ")}
        </span>
      </div>
      {hole.detail && <p>{hole.detail}</p>}
      {mode ? (
        <div>
          <textarea
            rows={3}
            autoFocus
            value={response}
            onChange={(e) => setResponse(e.target.value)}
            placeholder={mode === "explained" ? "How does it work? The Outline Doctor will take this as true." : "Why isn't this a hole? (optional)"}
          />
          <div className="actions">
            <button
              className="primary small"
              disabled={disabled || (mode === "explained" && !response.trim())}
              onClick={() => onAnswer(hole, mode, response)}
            >
              {mode === "explained" ? "Save explanation" : "Reject hole"}
            </button>
            <button className="small" onClick={() => setMode(null)}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="actions">
          <button className="small" disabled={disabled} onClick={() => setMode("explained")}>
            Explain
          </button>
          <button className="small" disabled={disabled} onClick={() => setMode("rejected")}>
            Reject
          </button>
          <button className="small" disabled={disabled} onClick={() => onAnswer(hole, "fixed")} title="Mark fixed without waiting for the next check">
            Mark fixed
          </button>
        </div>
      )}
    </div>
  );
}
