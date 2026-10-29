# RavenQuill - Your Private Book Editor
An AI book editor that only uses locally deployed models so your data stays private.

Upload a manuscript (.docx), let four AI editors work through it with a model running on
your own computer in [LM Studio](https://lmstudio.ai), review every change side by side, and
download a properly formatted book (.docx) that opens in Word or Google Docs.

## The editors

| Editor | What it does | Changes text? |
|---|---|---|
| **Story Architect** | Reads the book once, keeps short notes per chapter, then reports *major* problems: continuity errors, timeline slips, plot holes, dropped threads, pacing. Also builds a style sheet of names and terms. Deliberately light. | No |
| **Prose Editor** | The main event. Turns draft prose into publishable prose while preserving the author's voice above all else. | Yes |
| **Copyeditor** | Grammar, punctuation, spelling, name consistency. Hands-off. | Yes (small) |
| **Proofreader** | Book typography (curly quotes, em dashes, ellipses, spacing) done in code, plus a final LLM sweep for missed typos. | Yes (tiny) |

They run in that order, and everything merges into **one living document**.

### How your voice is protected
- Before the Prose Editor starts, RavenQuill builds an **author voice profile** (POV, rhythm,
  vocabulary, dialogue style, deliberate quirks). Every request includes it, and you can edit it.
- The model edits a few paragraphs at a time and never sees the job of restructuring the book:
  it cannot merge, split, reorder, add or drop paragraphs.
- Every edit passes **guardrails** before it's applied. An edit is held back (and flagged ⚑ for you)
  if it changes too much, changes the length too much, rewrites dialogue, loses italics, or
  introduces stock AI phrases ("tapestry", "testament to", "a dance of"…).
- Nothing is lost: each paragraph keeps its original text and a full edit history.

## Outlines
Before you write (or rewrite), the **Outline Doctor** can check your outline for holes: plot holes,
unmotivated choices, setups with no payoff, dropped threads, timeline contradictions, unclear stakes.
Open **Outlines**, upload a .docx/.txt/.md or paste the outline, and press **Check for holes**.

Answer each hole one of three ways, then press **Check again**:
- **Fix it** in the outline (edit it right there). The next round confirms the fix.
- **Reject** it, with an optional reason.
- **Explain** it: say how it works. The Outline Doctor takes your explanation as true.

Rejected and explained holes are never raised again. You're done when a round finds no new holes
and none are left open. **Download report** gives every hole, your answers, and the outline as .md.

## Reviewing
The review screen shows **Original | Edited** side by side, chapter by chapter.

- **●** a paragraph was changed and needs review · **✓** you've reviewed it · **⚑** an editor suggested something that was held back.
- Click the marker to see which editor changed what and to use any version from the history.
- Click the edited text to change it yourself (Ctrl+Enter saves). "Use original" reverts.
- Filter to *Changed*, *Needs review* or *Flagged*; **Next to review ↓** jumps to the next one.

The edited .docx in `data/projects/<id>/output/` is rewritten after every chapter during a run
and a few seconds after each save in review. A few **checkpoints** (original upload, before each
run, after each editor) let you roll back if something goes badly.

## Downloads
- **Edited book**: clean and book formatted (6×9 trim, Garamond, chapter headings on new pages, indented paragraphs, no indent after headings or scene breaks, centred scene breaks).
- **Edited book with tracked changes**: Google Docs shows these as Suggestions.
- **Original, book formatted**, the **original upload**, and the **Story report** (.md).

For Google Docs: upload the .docx to Google Drive, then *Open with → Google Docs*.

---

## Setup

### 1. LM Studio
1. Install [LM Studio](https://lmstudio.ai) and download a model (see below).
2. Open the **Developer** tab, load the model, and **Start Server** (default `http://localhost:1234`).
3. Give the model a context length of at least 4096 (8192 is better).

### 2. Backend (Python 3.10+)
```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
```

### 3. Frontend (Node.js 18+)
Install Node from [nodejs.org](https://nodejs.org) or with nvm, then:
```bash
cd frontend && npm install && npm run build
```

### 4. Run
```bash
cd backend && ../.venv/bin/python run.py
```
Open http://localhost:8000. Go to **Settings → Test connection & speed** first.

### Developing
Run the backend with auto-reload and the Vite dev server (hot reload on :5173, proxies `/api` to :8000):
```bash
cd backend && ../.venv/bin/python run.py --reload
cd frontend && npm run dev
```
Tests (use a fake model, so no LM Studio needed): `cd backend && ../.venv/bin/python -m pytest`

---

## Choosing a model and hardware

Speed matters: a 90,000-word novel is about 125,000 tokens per editing pass.

| tokens/sec | One pass of a 90k-word novel |
|---|---|
| 3 (CPU only) | ~12 hours |
| 15 | ~2.5 hours |
| 40 (decent GPU) | ~1 hour |

Use **Settings → Test connection & speed** to see your number. Jobs run in the background,
save progress after every batch, and can be stopped and resumed, so overnight runs are fine.

**Prefer a regular instruct model over a "thinking" model.** Reasoning models (DeepSeek-R1,
QwQ, Qwen3 in thinking mode) write hundreds of hidden tokens before each answer. That can make
a pass 5–10× slower, and they don't edit prose any better. RavenQuill strips the thinking out
if you use one (raise *Reasoning budget* in Settings), but for books choose a non-thinking model:

- **6–8 GB VRAM:** a 7–9B instruct model at Q4_K_M (e.g. Qwen2.5 7B Instruct, Llama 3.1 8B Instruct, Gemma 2 9B)
- **4 GB VRAM or CPU only:** a 3–4B instruct model (e.g. Qwen3 4B Instruct 2507, Llama 3.2 3B Instruct, Gemma 3 4B), and lower *Words per editing request* to ~150
- **12 GB+ VRAM:** 12–14B models (e.g. Gemma 3 12B, Qwen2.5 14B Instruct) edit noticeably better

If speed is very low on a machine with an NVIDIA GPU, check in LM Studio (*Settings → Runtime*,
hardware panel) that the GPU is detected and layers are offloaded. On Linux this needs a working
NVIDIA driver (`nvidia-smi` should list your GPU).

---

## How it's built (a tour for learners)

```
backend/ravenquill/
  api.py        FastAPI routes: the HTTP API the React app calls (try http://localhost:8000/docs)
  pipeline.py   Background worker: runs the editors chapter by chapter, saves progress, writes the .docx
  personas.py   The four editors' prompts and the guardrails that accept or hold back edits
  llm.py        Tiny client for LM Studio's OpenAI-compatible API; strips <think> output
  docx_io.py    Reads the manuscript (keeping italics/bold) and writes book-formatted / tracked-changes .docx
  textutil.py   Inline markup, word diffs, similarity scores, smart typography
  db.py         SQLite schema. The database *is* the living document.
frontend/src/
  pages/        ProjectsPage, ProjectPage (run, progress, downloads), ReviewPage (side by side), SettingsPage
  components/   Markup.jsx renders text, diffs and the report safely (no innerHTML)
  api.js        fetch() wrapper for the backend
```

**FastAPI vs Flask:** routes look much the same (`@app.get("/path")`), but FastAPI reads type
hints. A parameter typed `project_id: int` is parsed and validated for you, and a Pydantic model
(`class RunRequest(BaseModel)`) validates the JSON body. You also get free interactive docs at `/docs`.

**React vs plain JS:** instead of finding DOM elements and changing them, each component is a
function that returns what the UI should look like for the current state (`useState`). When state
changes, React re-renders. `useEffect` runs side effects such as fetching data or polling the job.

All data lives in `data/` (git-ignored): the SQLite database, uploaded manuscripts, and exports.
The server only listens on 127.0.0.1, so other computers on your network can't reach it.
