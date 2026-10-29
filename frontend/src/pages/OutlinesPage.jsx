import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { PersonaModal } from "../components/PersonaInfo.jsx";

export default function OutlinesPage() {
  const [outlines, setOutlines] = useState(null);
  const [name, setName] = useState("");
  const [file, setFile] = useState(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [learnMore, setLearnMore] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/outlines").then(setOutlines).catch((e) => setError(e.message));
  }, []);

  async function create(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData();
    form.append("name", name);
    if (file) form.append("file", file);
    else form.append("text", text);
    try {
      const outline = await api.post("/outlines", form);
      navigate(`/outlines/${outline.id}`);
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  return (
    <main className="page narrow">
      <section className="card">
        <h2>New outline</h2>
        <p className="muted">
          Upload an outline (.docx, .txt or .md) or paste it in. The Outline Doctor reads it and reports the holes, and
          you iterate until none are left.{" "}
          <button type="button" className="link" onClick={() => setLearnMore(true)}>
            Learn more
          </button>
        </p>
        <form onSubmit={create}>
          <div className="new-project">
            <input placeholder="Book title" value={name} onChange={(e) => setName(e.target.value)} />
            <input type="file" accept=".docx,.txt,.md,.markdown" onChange={(e) => setFile(e.target.files[0] ?? null)} />
            <button className="primary" disabled={(!file && !text.trim()) || busy}>
              {busy ? "Reading outline…" : "Create outline"}
            </button>
          </div>
          {!file && (
            <textarea
              className="outline-paste"
              rows={5}
              placeholder="…or paste your outline here"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          )}
        </form>
        {error && <p className="error">{error}</p>}
      </section>

      <h2>Your outlines</h2>
      {outlines === null && !error && <p className="muted">Loading…</p>}
      {outlines?.length === 0 && <p className="muted">No outlines yet.</p>}
      <div className="project-list">
        {outlines?.map((o) => (
          <Link key={o.id} to={`/outlines/${o.id}`} className="card project-card">
            <h3>{o.name}</h3>
            <p className="muted">
              {o.rounds === 0
                ? "Not checked yet"
                : `${o.rounds} round${o.rounds === 1 ? "" : "s"} · ${o.open_holes} hole${o.open_holes === 1 ? "" : "s"} open`}
            </p>
            {o.status === "reviewing" && <span className="status status-running">reviewing</span>}
            {o.rounds > 0 && o.open_holes === 0 && o.status === "idle" && <span className="status status-done">no open holes</span>}
          </Link>
        ))}
      </div>
      {learnMore && <PersonaModal stageId="outline" onClose={() => setLearnMore(false)} />}
    </main>
  );
}
