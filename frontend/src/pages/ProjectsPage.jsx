import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";

export default function ProjectsPage() {
  const [projects, setProjects] = useState(null);
  const [name, setName] = useState("");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/projects").then(setProjects).catch((e) => setError(e.message));
  }, []);

  async function create(event) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    const form = new FormData();
    form.append("name", name || file.name.replace(/\.docx$/i, ""));
    form.append("file", file);
    try {
      const project = await api.post("/projects", form);
      navigate(`/projects/${project.id}`);
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  return (
    <main className="page">
      <section className="card">
        <h2>New project</h2>
        <p className="muted">Upload your manuscript as a .docx. Chapters are detected from headings or “Chapter …” lines.</p>
        <form className="new-project" onSubmit={create}>
          <input placeholder="Book title" value={name} onChange={(e) => setName(e.target.value)} />
          <input type="file" accept=".docx" onChange={(e) => setFile(e.target.files[0] ?? null)} />
          <button className="primary" disabled={!file || busy}>
            {busy ? "Reading manuscript…" : "Create project"}
          </button>
        </form>
        {error && <p className="error">{error}</p>}
      </section>

      <h2>Your projects</h2>
      {projects === null && !error && <p className="muted">Loading…</p>}
      {projects?.length === 0 && <p className="muted">No projects yet.</p>}
      <div className="project-list">
        {projects?.map((p) => (
          <Link key={p.id} to={`/projects/${p.id}`} className="card project-card">
            <h3>{p.name}</h3>
            <p className="muted">
              {p.chapters} chapters · {p.changed} paragraphs edited
            </p>
            {p.job && <span className={`status status-${p.job.status}`}>{p.job.status}</span>}
          </Link>
        ))}
      </div>
    </main>
  );
}
