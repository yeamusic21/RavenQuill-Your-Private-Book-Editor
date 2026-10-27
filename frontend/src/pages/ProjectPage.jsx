import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, formatDuration, PRESETS, STAGES, stageName } from "../api.js";
import { SimpleMarkdown } from "../components/Markup.jsx";
import { PersonaModal } from "../components/PersonaInfo.jsx";

const INTENSITY = {
  light: "Only fixes what a reader would stumble over.",
  standard: "Draft → professional book. Clean prose, your voice.",
  heavy: "Restructures clumsy sentences more freely. Review closely.",
};

export default function ProjectPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState(null);
  const [stages, setStagesState] = useState(() => loadStages(id));
  const setStages = (next) => {
    // Keep pipeline order no matter which order boxes were ticked in.
    const ordered = STAGES.map((s) => s.id).filter((s) => next.includes(s));
    setStagesState(ordered);
    try {
      localStorage.setItem(stagesKey(id), JSON.stringify(ordered));
    } catch {}
  };
  const [error, setError] = useState("");
  const [learnMore, setLearnMore] = useState(null);
  const lastStatus = useRef(null);

  const load = useCallback(() => api.get(`/projects/${id}`).then(setProject).catch((e) => setError(e.message)), [id]);
  useEffect(() => {
    load();
  }, [load]);

  // Poll the job while it's running.
  const job = project?.job;
  const active = job && ["queued", "running"].includes(job.status);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(async () => {
      const latest = await api.get(`/projects/${id}/job`);
      setProject((p) => ({ ...p, job: latest }));
      if (latest.status !== lastStatus.current && !["queued", "running"].includes(latest.status)) load();
      lastStatus.current = latest.status;
    }, 2000);
    return () => clearInterval(timer);
  }, [active, id, load]);

  if (error) return <main className="page"><p className="error">{error}</p></main>;
  if (!project) return <main className="page"><p className="muted">Loading…</p></main>;

  const canResume = job && ["paused", "error"].includes(job.status);
  const s = project.stats;

  async function run(restart) {
    setError("");
    try {
      setProject(await api.post(`/projects/${id}/run`, { stages: restart ? stages : job.stages, restart }));
    } catch (e) {
      setError(e.message);
    }
  }

  async function patch(values) {
    setProject(await api.patch(`/projects/${id}`, values));
  }

  async function restore(cp) {
    if (!confirm(`Restore “${cp.label}”? Current text is saved as a “Before restore” checkpoint first.`)) return;
    try {
      setProject(await api.post(`/projects/${id}/checkpoints/${cp.id}/restore`));
    } catch (e) {
      alert(e.message);
    }
  }

  async function remove() {
    if (!confirm(`Delete “${project.name}” and all its edits? This cannot be undone.`)) return;
    await api.del(`/projects/${id}`);
    navigate("/");
  }

  return (
    <main className="page">
      <div className="page-header">
        <div>
          <h1>{project.name}</h1>
          <p className="muted">
            {s.words.toLocaleString()} words · {s.changed ?? 0} paragraphs edited · {s.reviewed ?? 0} reviewed ·{" "}
            {s.flagged ?? 0} flagged
          </p>
        </div>
        <Link className="button primary" to={`/projects/${id}/review`}>
          Review side by side →
        </Link>
      </div>

      <div className="grid-2">
        <section className="card">
          <h2>Run the editors</h2>
          <div className="presets">
            {PRESETS.map((preset) => {
              const selected = preset.stages.join() === stages.join();
              return (
                <button
                  key={preset.name}
                  className={`small${selected ? " selected" : ""}`}
                  aria-pressed={selected}
                  title={preset.blurb}
                  disabled={active}
                  onClick={() => setStages(preset.stages)}
                >
                  {preset.name}
                </button>
              );
            })}
          </div>
          <div className="stage-list">
            {STAGES.map((stage) => (
              <label key={stage.id} className="stage-option">
                <input
                  type="checkbox"
                  checked={stages.includes(stage.id)}
                  disabled={active}
                  onChange={(e) =>
                    setStages(e.target.checked ? [...stages, stage.id] : stages.filter((x) => x !== stage.id))
                  }
                />
                <span>
                  <strong>{stage.name}</strong>
                  <small className="muted">
                    {stage.blurb}{" "}
                    <button
                      className="link"
                      onClick={(e) => {
                        e.preventDefault();
                        setLearnMore(stage.id);
                      }}
                    >
                      Learn more
                    </button>
                  </small>
                </span>
              </label>
            ))}
          </div>

          {stages.includes("prose") && (
            <label className="field">
              Prose Editor intensity
              <select value={project.intensity} disabled={active} onChange={(e) => patch({ intensity: e.target.value })}>
                {Object.keys(INTENSITY).map((k) => (
                  <option key={k} value={k}>
                    {k[0].toUpperCase() + k.slice(1)}: {INTENSITY[k]}
                  </option>
                ))}
              </select>
            </label>
          )}

          <div className="actions">
            {active ? (
              <button onClick={() => api.post(`/projects/${id}/cancel`)}>Stop</button>
            ) : (
              <>
                {canResume && (
                  <button className="primary" onClick={() => run(false)}>
                    Resume
                  </button>
                )}
                <button className={canResume ? "" : "primary"} disabled={!stages.length} onClick={() => run(true)}>
                  {canResume ? "Start over" : "Start"}
                </button>
              </>
            )}
          </div>
          <JobStatus job={job} />
        </section>

        <section className="card">
          <h2>Download</h2>
          <p className="muted">
            The edited book is rewritten as work progresses and whenever you save in review. To use Google Docs: upload the
            .docx to Google Drive, then <em>Open with → Google Docs</em>.
          </p>
          <ul className="downloads">
            <li><a href={api.exportUrl(id, "edited")}>Edited book (.docx)</a> <span className="muted">clean, book formatted</span></li>
            <li><a href={api.exportUrl(id, "tracked")}>Edited book with tracked changes (.docx)</a> <span className="muted">shows as suggestions in Google Docs</span></li>
            <li><a href={api.exportUrl(id, "original")}>Original, book formatted (.docx)</a></li>
            <li><a href={api.exportUrl(id, "source")}>Original upload</a></li>
            {project.report && <li><a href={api.exportUrl(id, "report")}>Story report (.md)</a></li>}
          </ul>

          <h3>Checkpoints</h3>
          <p className="muted">Snapshots to roll back to if a run goes badly.</p>
          <ul className="checkpoints">
            {project.checkpoints.map((cp) => (
              <li key={cp.id}>
                <span>{cp.label}</span>
                <span className="muted">{cp.created_at} UTC</span>
                <button className="small" disabled={active} onClick={() => restore(cp)}>
                  Restore
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>

      {project.report && (
        <section className="card">
          <h2>Story Architect report</h2>
          <SimpleMarkdown text={project.report} />
        </section>
      )}

      <div className="grid-2">
        <EditableText
          title="Author voice profile"
          help="Built automatically before the Prose Editor runs. The editor is told to preserve everything here. Edit it if it got your voice wrong."
          value={project.voice_profile}
          onSave={(v) => patch({ voice_profile: v })}
        />
        <EditableText
          title="Style sheet"
          help="Names and terms with their correct spelling. Built by the Story Architect; used by the editors for consistency."
          value={project.style_sheet}
          onSave={(v) => patch({ style_sheet: v })}
        />
      </div>

      {learnMore && <PersonaModal stageId={learnMore} onClose={() => setLearnMore(null)} />}

      <p className="danger-zone">
        <button className="link danger" onClick={remove}>
          Delete project
        </button>
      </p>
    </main>
  );
}

const stagesKey = (id) => `ravenquill.stages.${id}`;

function loadStages(id) {
  try {
    const saved = JSON.parse(localStorage.getItem(stagesKey(id)));
    if (Array.isArray(saved)) return STAGES.map((s) => s.id).filter((s) => saved.includes(s));
  } catch {}
  return STAGES.map((s) => s.id);
}

function JobStatus({ job }) {
  if (!job) return <p className="muted">Not run yet.</p>;
  const pct = job.total ? Math.round((job.done / job.total) * 100) : 0;
  return (
    <div className="job">
      <div className="job-line">
        <span className={`status status-${job.status}`}>{job.status}</span>
        {job.current_stage && <span>{stageName(job.current_stage)}</span>}
        <span className="muted">{job.message}</span>
      </div>
      {job.total > 0 && (
        <div className="progress" title={`${job.done} / ${job.total}`}>
          <div style={{ width: `${pct}%` }} />
        </div>
      )}
      <div className="muted small-text">
        {job.total > 0 && `${job.done} / ${job.total} · `}
        {job.tokens_per_second && `${job.tokens_per_second} tokens/s · `}
        {job.eta_seconds != null && `about ${formatDuration(job.eta_seconds)} left`}
      </div>
      {job.error && <p className="error">{job.error}</p>}
    </div>
  );
}

function EditableText({ title, help, value, onSave }) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  return (
    <section className="card">
      <h2>{title}</h2>
      <p className="muted">{help}</p>
      <textarea rows={10} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="(empty)" />
      <div className="actions">
        <button disabled={draft === value} onClick={() => onSave(draft)}>
          Save
        </button>
      </div>
    </section>
  );
}
