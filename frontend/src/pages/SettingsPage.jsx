import { useEffect, useState } from "react";
import { api, formatDuration } from "../api.js";

const FIELDS = [
  { key: "base_url", label: "LM Studio server URL", help: "LM Studio → Developer tab → Start server. Default http://localhost:1234/v1" },
  { key: "temperature", label: "Temperature", type: "number", step: 0.05, help: "Lower = more conservative edits. 0.2–0.4 works well." },
  { key: "batch_words", label: "Words per editing request", type: "number", help: "Smaller is safer for small models and slow computers. 150–400." },
  { key: "context_paragraphs", label: "Context paragraphs", type: "number", help: "Earlier paragraphs shown (read-only) for continuity." },
  { key: "architect_chunk_words", label: "Story Architect chunk size (words)", type: "number", help: "How much the Architect reads per request. Lower for small context windows." },
  { key: "reasoning_budget", label: "Reasoning budget (tokens)", type: "number", help: "Extra room for “thinking” models like DeepSeek-R1. Use 0 for regular instruct models." },
  { key: "request_timeout", label: "Request timeout (seconds)", type: "number", help: "Raise this on slow (CPU-only) machines." },
  { key: "book_font", label: "Book font", help: "Garamond, Georgia, Times New Roman… (Google Docs has EB Garamond)" },
  { key: "font_size", label: "Font size (pt)", type: "number" },
  { key: "scene_break", label: "Scene break marker", help: "Printed centred between scenes." },
];

export default function SettingsPage() {
  const [settings, setSettings] = useState(null);
  const [models, setModels] = useState([]);
  const [modelError, setModelError] = useState("");
  const [test, setTest] = useState(null);
  const [testing, setTesting] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.get("/settings").then(setSettings);
    api
      .get("/llm/models")
      .then((r) => setModels(r.models))
      .catch((e) => setModelError(e.message));
  }, []);

  if (!settings) return <main className="page narrow"><p className="muted">Loading…</p></main>;

  const set = (key, value) => {
    setSaved(false);
    setSettings({ ...settings, [key]: value });
  };

  async function save() {
    setSettings(await api.put("/settings", settings));
    setSaved(true);
  }

  async function runTest() {
    await save();
    setTesting(true);
    setTest(null);
    try {
      setTest(await api.post("/llm/test"));
    } catch (e) {
      setTest({ error: e.message });
    } finally {
      setTesting(false);
    }
  }

  // Rough per-pass estimate for a 90k-word novel: ~1.4 tokens/word of output.
  const estimate = test?.tokens_per_second ? (90000 * 1.4) / test.tokens_per_second : null;

  return (
    <main className="page narrow">
      <h1>Settings</h1>
      <section className="card">
        <h2>Model</h2>
        <label className="field">
          Model
          <select value={settings.model} onChange={(e) => set("model", e.target.value)}>
            <option value="">Whatever LM Studio has loaded</option>
            {models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          {modelError && <small className="error">{modelError}</small>}
        </label>
        <div className="actions">
          <button onClick={runTest} disabled={testing}>
            {testing ? "Testing… (slow machines can take a few minutes)" : "Test connection & speed"}
          </button>
        </div>
        {test?.error && <p className="error">{test.error}</p>}
        {test && !test.error && (
          <div className="test-result">
            <p>
              Reply: <em>{test.reply}</em>
            </p>
            <p>
              {test.tokens} tokens in {test.seconds}s → <strong>{test.tokens_per_second} tokens/s</strong>
            </p>
            {estimate && (
              <p className="muted">
                A 90,000-word novel would take roughly <strong>{formatDuration(estimate)}</strong> per editing pass
                (more with a thinking model). Under ~10 tokens/s, check that LM Studio is using your GPU.
              </p>
            )}
          </div>
        )}
      </section>

      <section className="card">
        <h2>Editing & formatting</h2>
        {FIELDS.map((f) => (
          <label key={f.key} className="field">
            {f.label}
            <input
              type={f.type ?? "text"}
              step={f.step}
              value={settings[f.key]}
              onChange={(e) => set(f.key, f.type === "number" ? Number(e.target.value) : e.target.value)}
            />
            {f.help && <small className="muted">{f.help}</small>}
          </label>
        ))}
        <label className="field">
          Page size
          <select value={settings.trim} onChange={(e) => set("trim", e.target.value)}>
            <option value="6x9">6 × 9 in (trade paperback)</option>
            <option value="5.5x8.5">5.5 × 8.5 in (digest)</option>
            <option value="letter">US Letter (manuscript)</option>
          </select>
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={settings.proofread_llm} onChange={(e) => set("proofread_llm", e.target.checked)} />
          Proofreader also does an LLM error sweep (typography always runs)
        </label>
        <div className="actions">
          <button className="primary" onClick={save}>
            Save settings
          </button>
          {saved && <span className="muted">Saved.</span>}
        </div>
      </section>
    </main>
  );
}
