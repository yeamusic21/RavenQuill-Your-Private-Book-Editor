"""Background job runner: walks the book through the selected editors.

One job runs at a time (the local model is a single shared resource).
Progress is saved after every batch, so a crash or restart loses at most one
batch of work; pressing Resume picks up where it stopped. The edited .docx in
the project's output folder is rewritten after every chapter."""
import json
import threading
import time
import traceback

from . import db
from .config import STAGES
from .docx_io import build_docx
from .llm import LLM, LLMError
from .personas import (ARCHITECT_NOTES_SYSTEM, ARCHITECT_REPORT_SYSTEM, STYLE_SHEET_SYSTEM, VOICE_SYSTEM,
                       batch_prompt, check_edit, parse_batch, system_prompt)
from .textutil import SCENE_BREAK_RE, strip_markup, typography, word_count

TOKENS_PER_WORD = 1.4

_wake = threading.Event()
_cancel = set()
_lock = threading.Lock()
_export_timers: dict[int, threading.Timer] = {}


class Cancelled(Exception):
    pass


# --- public API ----------------------------------------------------------------------

def start_worker():
    threading.Thread(target=_worker, daemon=True, name="ravenquill-worker").start()


def enqueue(project_id: int, stages: list[str], restart: bool) -> int:
    stages = [s for s in STAGES if s in stages]
    with db.connect() as conn:
        active = conn.execute("SELECT id FROM jobs WHERE project_id=? AND status IN ('queued','running')",
                              (project_id,)).fetchone()
        if active:
            return active["id"]
        if restart:
            for stage in stages:
                conn.execute("UPDATE paragraphs SET done_stages=replace(done_stages, ?, ',') WHERE project_id=?",
                             (f",{stage},", project_id))
            if "architect" in stages:
                conn.execute("UPDATE chapters SET notes=NULL WHERE project_id=?", (project_id,))
        cur = conn.execute("INSERT INTO jobs(project_id, stages, status, message) VALUES(?,?, 'queued', 'Waiting…')",
                           (project_id, json.dumps(stages)))
        job_id = cur.lastrowid
    _wake.set()
    return job_id


def cancel(project_id: int):
    with db.connect() as conn:
        conn.execute("UPDATE jobs SET status='cancelled', message='Cancelled' WHERE project_id=? AND status='queued'",
                     (project_id,))
        running = conn.execute("SELECT id FROM jobs WHERE project_id=? AND status='running'", (project_id,)).fetchone()
    if running:
        _cancel.add(running["id"])


def export_paths(project_id: int) -> dict:
    out = db.project_dir(project_id) / "output"
    out.mkdir(exist_ok=True)
    with db.connect() as conn:
        name = conn.execute("SELECT name FROM projects WHERE id=?", (project_id,)).fetchone()["name"]
    safe = "".join(c for c in name if c.isalnum() or c in " -_").strip() or f"project-{project_id}"
    return {
        "edited": out / f"{safe} - edited.docx",
        "tracked": out / f"{safe} - tracked changes.docx",
        "original": out / f"{safe} - original (formatted).docx",
    }


def write_exports(project_id: int, kinds=("edited",)) -> dict:
    settings = db.get_settings()
    paths = export_paths(project_id)
    with db.connect() as conn:
        name = conn.execute("SELECT name FROM projects WHERE id=?", (project_id,)).fetchone()["name"]
        pars = db.rows(conn.execute("SELECT kind, original, current FROM paragraphs WHERE project_id=? ORDER BY idx",
                                    (project_id,)))
    mode = {"edited": "clean", "tracked": "tracked", "original": "original"}
    for kind in kinds:
        tmp = paths[kind].with_suffix(".tmp")
        build_docx(tmp, name, pars, settings, mode[kind])
        tmp.replace(paths[kind])  # atomic: the file on disk is never half-written
    return paths


def schedule_export(project_id: int, delay: float = 3.0):
    """Rewrite the living .docx shortly after the author edits in the review screen."""
    with _lock:
        if timer := _export_timers.get(project_id):
            timer.cancel()
        timer = threading.Timer(delay, _safe_export, args=(project_id,))
        timer.daemon = True
        _export_timers[project_id] = timer
        timer.start()


def save_checkpoint(project_id: int, label: str):
    with db.connect() as conn:
        data = {r["id"]: r["current"] for r in conn.execute(
            "SELECT id, current FROM paragraphs WHERE project_id=?", (project_id,))}
        conn.execute("INSERT INTO checkpoints(project_id, label, data) VALUES(?,?,?) "
                     "ON CONFLICT(project_id, label) DO UPDATE SET data=excluded.data, created_at=datetime('now')",
                     (project_id, label, json.dumps(data)))


# --- worker ------------------------------------------------------------------------------

def _safe_export(project_id: int):
    try:
        write_exports(project_id)
    except Exception:
        traceback.print_exc()


def _worker():
    while True:
        with db.connect() as conn:
            job = conn.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
        if not job:
            _wake.wait(timeout=5)
            _wake.clear()
            continue
        _run_job(dict(job))


def _update_job(job_id: int, **fields):
    fields["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    cols = ", ".join(f"{k}=?" for k in fields)
    with db.connect() as conn:
        conn.execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), job_id))


def _run_job(job: dict):
    job_id, project_id = job["id"], job["project_id"]
    stages = json.loads(job["stages"])
    runner = _JobRunner(job_id, project_id, stages)
    _update_job(job_id, status="running", message="Starting…", error=None)
    try:
        save_checkpoint(project_id, "Before last run")
        runner.run()
        write_exports(project_id, ("edited", "tracked"))
        _update_job(job_id, status="done", message="Finished", current_stage=None)
    except Cancelled:
        _update_job(job_id, status="paused", message="Stopped. Press Resume to continue where it left off.")
        _safe_export(project_id)
    except LLMError as e:
        _update_job(job_id, status="error", message="Stopped: problem talking to LM Studio", error=str(e))
        _safe_export(project_id)
    except Exception as e:
        traceback.print_exc()
        _update_job(job_id, status="error", message="Stopped by an unexpected error", error=f"{e}")
        _safe_export(project_id)
    finally:
        _cancel.discard(job_id)


class _JobRunner:
    def __init__(self, job_id: int, project_id: int, stages: list[str]):
        self.job_id, self.project_id, self.stages = job_id, project_id, stages
        self.settings = db.get_settings()
        self.llm = LLM(self.settings)
        self.done, self.llm_seconds, self.llm_tokens = 0, 0.0, 0
        with db.connect() as conn:
            self.project = dict(conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone())
            self.chapters = db.rows(conn.execute("SELECT * FROM chapters WHERE project_id=? ORDER BY idx",
                                                 (project_id,)))

    # helpers
    def check_cancel(self):
        if self.job_id in _cancel:
            raise Cancelled()

    def ask(self, system: str, user: str, max_tokens: int, temperature=None) -> str:
        self.check_cancel()
        reply = self.llm.chat(system, user, max_tokens, temperature)
        self.llm_seconds += reply.seconds
        self.llm_tokens += reply.tokens
        return reply.text

    def progress(self, stage: str, message: str, step: int = 1):
        self.done += step
        _update_job(self.job_id, current_stage=stage, done=self.done, message=message,
                    llm_seconds=round(self.llm_seconds, 1), llm_tokens=self.llm_tokens)

    def paragraphs(self, chapter_id: int) -> list[dict]:
        with db.connect() as conn:
            return db.rows(conn.execute("SELECT * FROM paragraphs WHERE chapter_id=? ORDER BY idx", (chapter_id,)))

    def architect_chunks(self, chapter: dict) -> list[str]:
        limit = int(self.settings["architect_chunk_words"])
        chunks, current, words = [], [], 0
        for p in self.paragraphs(chapter["id"]):
            if p["kind"] != "body":
                continue
            current.append(strip_markup(p["current"]))
            words += word_count(p["current"])
            if words >= limit:
                chunks.append("\n\n".join(current))
                current, words = [], 0
        if current:
            chunks.append("\n\n".join(current))
        return chunks

    # main
    def run(self):
        total = 0
        with db.connect() as conn:
            for stage in self.stages:
                if stage == "architect":
                    total += sum(len(self.architect_chunks(c)) for c in self.chapters) + 2
                else:
                    total += conn.execute(
                        "SELECT count(*) FROM paragraphs WHERE project_id=? AND kind!='scene_break'",
                        (self.project_id,)).fetchone()[0]
            # Count what's already done so a resumed job shows the right progress.
            done = 0
            for stage in self.stages:
                if stage == "architect":
                    done += sum(len(self.architect_chunks(c)) for c in self.chapters if c["notes"] is not None)
                else:
                    done += conn.execute(
                        "SELECT count(*) FROM paragraphs WHERE project_id=? AND kind!='scene_break' "
                        "AND done_stages LIKE ?", (self.project_id, f"%,{stage},%")).fetchone()[0]
        self.done = done
        _update_job(self.job_id, total=total, done=done)

        for stage in self.stages:
            if stage == "architect":
                self.run_architect()
            else:
                self.run_editor(stage)
            save_checkpoint(self.project_id, f"After {stage}")

    # --- Story Architect --------------------------------------------------------------
    def run_architect(self):
        for chapter in self.chapters:
            if chapter["notes"] is not None:
                continue
            chunks = self.architect_chunks(chapter)
            notes = []
            for n, chunk in enumerate(chunks, 1):
                label = chapter["title"] + (f" (part {n})" if len(chunks) > 1 else "")
                text = self.ask(ARCHITECT_NOTES_SYSTEM, f"EXCERPT from {label}:\n\n{chunk}", 450, temperature=0.2)
                notes.append(text)
                self.progress("architect", f"Story Architect read {label}")
            chapter["notes"] = "\n".join(notes)
            with db.connect() as conn:
                conn.execute("UPDATE chapters SET notes=? WHERE id=?", (chapter["notes"], chapter["id"]))

        all_notes = [f"### {c['title']}\n{c['notes']}" for c in self.chapters if c["notes"]]
        notes_text = self.condense(all_notes)

        sheet = self.ask(STYLE_SHEET_SYSTEM, notes_text, 700, temperature=0.1)
        self.progress("architect", "Story Architect built the style sheet")
        report = self.ask(ARCHITECT_REPORT_SYSTEM, notes_text, 1200, temperature=0.2)
        self.progress("architect", "Story Architect wrote the report")
        with db.connect() as conn:
            conn.execute("UPDATE projects SET report=?, style_sheet=?, updated_at=datetime('now') WHERE id=?",
                         (report, sheet, self.project_id))
        self.project.update(report=report, style_sheet=sheet)

    def condense(self, notes: list[str]) -> str:
        """Shrink chapter notes until they fit in one request (keeps the Architect light)."""
        budget = int(self.settings["architect_chunk_words"]) * 2
        while sum(word_count(n) for n in notes) > budget and len(notes) > 1:
            grouped, group, words = [], [], 0
            for note in notes:
                if group and words + word_count(note) > budget // 2:
                    grouped.append(group)
                    group, words = [], 0
                group.append(note)
                words += word_count(note)
            grouped.append(group)
            if len(grouped) == len(notes):  # can't shrink by grouping; summarise individually
                grouped = [[n] for n in notes]
            notes = [self.ask("Merge these story notes into one shorter set of notes with the same headings. "
                              "Keep every name, date, fact and problem; drop repetition. Keep chapter references.",
                              "\n\n".join(g), 600, temperature=0.1) for g in grouped]
        return "\n\n".join(notes)

    # --- Prose / Copyedit / Proofread ----------------------------------------------------------
    def ensure_voice_profile(self):
        if self.project["voice_profile"].strip():
            return
        with db.connect() as conn:
            bodies = [r["current"] for r in conn.execute(
                "SELECT current FROM paragraphs WHERE project_id=? AND kind='body' ORDER BY idx", (self.project_id,))]
        if not bodies:
            return
        # Sample from the start, middle and later part of the book.
        sample, limit = [], int(self.settings["architect_chunk_words"])
        for start in (0, len(bodies) // 2, (len(bodies) * 3) // 4):
            words = 0
            for text in bodies[start:]:
                sample.append(strip_markup(text))
                words += word_count(text)
                if words > limit // 3:
                    break
        _update_job(self.job_id, current_stage="prose", message="Analysing the author's voice…")
        voice = self.ask(VOICE_SYSTEM, "\n\n".join(sample), 500, temperature=0.2)
        with db.connect() as conn:
            conn.execute("UPDATE projects SET voice_profile=? WHERE id=?", (voice, self.project_id))
        self.project["voice_profile"] = voice
        _update_job(self.job_id, message="Built the author voice profile")

    def run_editor(self, stage: str):
        if stage == "prose":
            self.ensure_voice_profile()
        intensity = self.project["intensity"]
        system = system_prompt(stage, intensity, self.project["voice_profile"])
        use_llm = stage != "proofread" or self.settings.get("proofread_llm", True)
        batch_words = int(self.settings["batch_words"])

        for chapter in self.chapters:
            pars = self.paragraphs(chapter["id"])
            todo = [p for p in pars if f",{stage}," not in p["done_stages"] and p["kind"] != "scene_break"]
            if not todo:
                continue

            # Headings and (in proofread) typography are handled without the model.
            for p in todo:
                if stage == "proofread":
                    fixed = typography(p["current"])
                    if fixed != p["current"]:
                        self.apply(p, stage, fixed, "typography")
                if p["kind"] == "heading":
                    self.mark_done([p], stage)
                    self.progress(stage, f"{chapter['title']}: heading")

            bodies = [p for p in todo if p["kind"] == "body"]
            if not use_llm:
                self.mark_done(bodies, stage)
                self.progress(stage, f"{chapter['title']}: typography done", len(bodies))
            else:
                for batch in self.batches(bodies, batch_words):
                    self.edit_batch(stage, intensity, system, pars, batch)
                    self.progress(stage, f"{chapter['title']}: {stage} ¶{batch[-1]['idx'] + 1}", len(batch))
            _safe_export(self.project_id)

    @staticmethod
    def batches(pars: list[dict], batch_words: int):
        batch, words = [], 0
        for p in pars:
            w = word_count(p["current"])
            if batch and words + w > batch_words:
                yield batch
                batch, words = [], 0
            batch.append(p)
            words += w
        if batch:
            yield batch

    def edit_batch(self, stage: str, intensity: str, system: str, chapter_pars: list[dict], batch: list[dict]):
        first_idx = batch[0]["idx"]
        earlier = [p for p in chapter_pars if p["idx"] < first_idx and p["kind"] == "body"]
        context = [p["current"] for p in earlier[-int(self.settings["context_paragraphs"]):]]
        texts = [p["current"] for p in batch]
        out_tokens = int(sum(word_count(t) for t in texts) * TOKENS_PER_WORD * 1.3) + 100

        reply = self.ask(system, batch_prompt(texts, context, self.project["style_sheet"]), out_tokens)
        results = parse_batch(reply, len(batch))
        if results is None and len(batch) > 1:
            # Model lost track of the numbering; fall back to one paragraph at a time.
            for p in batch:
                self.edit_batch(stage, intensity, system, chapter_pars, [p])
            return
        if results is None:
            # Single paragraph: accept an untagged reply as the paragraph itself.
            results = [reply.strip()] if reply.strip() and "\n\n" not in reply.strip() else [batch[0]["current"]]

        for p, new in zip(batch, results):
            new = new.strip()
            if new and new != p["current"] and not SCENE_BREAK_RE.match(strip_markup(new)):
                reason = check_edit(stage, intensity, p["current"], new)
                if reason:
                    self.record_rejected(p, stage, new, reason)
                else:
                    self.apply(p, stage, new)
        self.mark_done(batch, stage)

    def apply(self, p: dict, stage: str, new: str, note: str = ""):
        with db.connect() as conn:
            conn.execute("INSERT INTO edits(project_id, paragraph_id, stage, before, after, status, note) "
                         "VALUES(?,?,?,?,?, 'applied', ?)", (self.project_id, p["id"], stage, p["current"], new, note))
            edited_by = p["edited_by"] if f",{stage}," in p["edited_by"] else p["edited_by"] + f"{stage},"
            conn.execute("UPDATE paragraphs SET current=?, edited_by=?, reviewed=0 WHERE id=?",
                         (new, edited_by, p["id"]))
        p["current"], p["edited_by"] = new, edited_by

    def record_rejected(self, p: dict, stage: str, new: str, reason: str):
        with db.connect() as conn:
            conn.execute("INSERT INTO edits(project_id, paragraph_id, stage, before, after, status, note) "
                         "VALUES(?,?,?,?,?, 'rejected', ?)", (self.project_id, p["id"], stage, p["current"], new, reason))
            conn.execute("UPDATE paragraphs SET flagged=1 WHERE id=?", (p["id"],))

    def mark_done(self, pars: list[dict], stage: str):
        with db.connect() as conn:
            for p in pars:
                if f",{stage}," not in p["done_stages"]:
                    p["done_stages"] += f"{stage},"
                    conn.execute("UPDATE paragraphs SET done_stages=? WHERE id=?", (p["done_stages"], p["id"]))
