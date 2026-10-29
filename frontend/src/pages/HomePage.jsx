import { useState } from "react";
import { Link } from "react-router-dom";
import { OUTLINE_DOCTOR, STAGES } from "../api.js";
import { PersonaModal } from "../components/PersonaInfo.jsx";

const HELPS = [
  {
    title: "Find the big problems",
    text: "Plot holes, continuity slips, dropped threads and pacing, in your outline before you write and in your manuscript after.",
  },
  {
    title: "Polish the prose, keep your voice",
    text: "Clumsy sentences get tightened while your style, dialogue and quirks stay yours. Every change is shown for you to accept or undo.",
  },
  {
    title: "Get a print-ready book",
    text: "Grammar, typos and book typography fixed, then exported as a properly formatted .docx for Word or Google Docs.",
  },
];

const STEPS = [
  <>
    <strong>Set up once.</strong> Install <a href="https://lmstudio.ai" target="_blank" rel="noreferrer">LM Studio</a>,
    download a model, and start its server (Developer tab). Then open <Link to="/settings">Settings</Link> and press{" "}
    <em>Test connection &amp; speed</em>.
  </>,
  <>
    <strong>Plan (optional).</strong> Paste or upload your outline in <Link to="/outlines">Outlines</Link> and let the
    Outline Doctor point out holes. Fix, reject or explain each one until none are left.
  </>,
  <>
    <strong>Upload your manuscript.</strong> Add it as a .docx on the <Link to="/projects">Projects</Link> tab. Chapters are found from headings or “Chapter …” lines.
  </>,
  <>
    <strong>Pick your editors and run them.</strong> Use the full edit, or just a copy-edit or proofread. A local model
    can take a while on a long book. You can stop and resume at any time.
  </>,
  <>
    <strong>Review side by side.</strong> See your original next to the edited text, change by change. Keep it, use your
    original, or type your own fix.
  </>,
  <>
    <strong>Download your book.</strong> Get it clean or with tracked changes, plus the Story report.
  </>,
];

export default function HomePage() {
  const [learnMore, setLearnMore] = useState(null);
  const editors = [OUTLINE_DOCTOR, ...STAGES]; // in the order you meet them

  return (
    <main className="page welcome">
      <div className="welcome-hero">
        <h1>Your private book editor</h1>
        <p className="welcome-lead">
          RavenQuill is a team of AI editors that help you take a draft to a finished, publishable book. It runs on a
          model on <em>your own computer</em>, so your manuscript is never uploaded anywhere.
        </p>
      </div>

      <div className="welcome-helps">
        {HELPS.map((h) => (
          <div key={h.title}>
            <h3>{h.title}</h3>
            <p className="muted">{h.text}</p>
          </div>
        ))}
      </div>

      <h2>How it works</h2>
      <ol className="welcome-steps">
        {STEPS.map((step, n) => (
          <li key={n}>{step}</li>
        ))}
      </ol>

      <h2>Meet the editors</h2>
      <div className="welcome-editors">
        {editors.map((e) => (
          <div key={e.id} className="welcome-editor">
            <strong>{e.name}</strong>
            <p className="muted small-text">{e.blurb}</p>
            <button className="link small-text" onClick={() => setLearnMore(e.id)}>
              Learn more
            </button>
          </div>
        ))}
      </div>

      <h2>Your book stays yours</h2>
      <ul className="welcome-promises">
        <li>
          <strong>Private.</strong> Everything runs through LM Studio on this computer. No accounts, no cloud, no
          training on your work.
        </li>
        <li>
          <strong>Your voice first.</strong> RavenQuill learns your style before editing and checks every edit. Changes
          that go too far, rewrite dialogue or add stock AI phrases are held back for you to decide on.
        </li>
        <li>
          <strong>Nothing is lost.</strong> Your original text, every edit and checkpoints are kept, so you can undo
          anything.
        </li>
        <li>
          <strong>You're the author.</strong> The editors suggest; you have the final say on every change. AI can be
          wrong, especially small local models, so treat their notes as a second opinion.
        </li>
      </ul>
      <div className="welcome-start">
        <Link className="button primary" to="/projects">
          Get started →
        </Link>
      </div>
      {learnMore && <PersonaModal stageId={learnMore} onClose={() => setLearnMore(null)} />}
    </main>
  );
}
