"""HTTP API (FastAPI). The React app in /frontend talks to these endpoints.

Interactive API docs: http://localhost:8000/docs"""
import json
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, pipeline
from .config import FRONTEND_DIST, STAGES
from .docx_io import parse_docx
from .llm import LLM, LLMError
from .textutil import diff_ops, word_count


@asynccontextmanager
async def lifespan(_app):
    db.init()
    pipeline.start_worker()
    yield


app = FastAPI(title="RavenQuill", lifespan=lifespan)


def _project_or_404(conn, project_id: int) -> dict:
    row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Project not found")
    return dict(row)


def _latest_job(conn, project_id: int):
    row = conn.execute("SELECT * FROM jobs WHERE project_id=? ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
    if not row:
        return None
    job = dict(row)
    job["stages"] = json.loads(job["stages"])
    # Rough ETA from the average time per unit of work so far.
    remaining = job["total"] - job["done"]
    job["tokens_per_second"] = round(job["llm_tokens"] / job["llm_seconds"], 1) if job["llm_seconds"] else None
    job["eta_seconds"] = None
    if job["status"] == "running" and job["done"] and job["llm_seconds"] and remaining > 0:
        job["eta_seconds"] = round(job["llm_seconds"] / max(job["done"], 1) * remaining)
    return job


# --- settings & LM Studio -------------------------------------------------------------

@app.get("/api/settings")
def get_settings():
    return db.get_settings()


@app.put("/api/settings")
def put_settings(values: dict):
    return db.save_settings(values)


@app.get("/api/llm/models")
def llm_models():
    try:
        return {"models": LLM(db.get_settings()).list_models()}
    except LLMError as e:
        raise HTTPException(502, str(e))


@app.post("/api/llm/test")
def llm_test():
    """Send one tiny edit and report speed, so users know what to expect."""
    llm = LLM(db.get_settings())
    try:
        reply = llm.chat("You are a copyeditor. Return only the corrected sentence.",
                         "Their going too the store tomorow.", 60)
    except LLMError as e:
        raise HTTPException(502, str(e))
    tps = reply.tokens / reply.seconds if reply.seconds else 0
    return {"reply": reply.text, "seconds": round(reply.seconds, 1), "tokens": reply.tokens,
            "tokens_per_second": round(tps, 1)}


# --- projects ---------------------------------------------------------------------------

@app.get("/api/projects")
def list_projects():
    with db.connect() as conn:
        projects = db.rows(conn.execute("""
            SELECT p.id, p.name, p.source_filename, p.created_at, p.updated_at,
                   (SELECT count(*) FROM chapters c WHERE c.project_id=p.id) AS chapters,
                   (SELECT count(*) FROM paragraphs x WHERE x.project_id=p.id AND x.original != x.current) AS changed
            FROM projects p ORDER BY p.updated_at DESC"""))
        for p in projects:
            p["job"] = _latest_job(conn, p["id"])
    return projects


@app.post("/api/projects")
def create_project(name: str = Form(...), file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".docx"):
        raise HTTPException(400, "Please upload a .docx file")
    with db.connect() as conn:
        project_id = conn.execute("INSERT INTO projects(name, source_filename) VALUES(?,?)",
                                  (name.strip() or Path(file.filename).stem, file.filename)).lastrowid
    source = db.project_dir(project_id) / "source.docx"
    with source.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    try:
        chapters = parse_docx(source)
    except Exception as e:
        with db.connect() as conn:
            conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
        shutil.rmtree(db.project_dir(project_id), ignore_errors=True)
        raise HTTPException(400, f"Couldn't read that .docx: {e}")

    with db.connect() as conn:
        idx = 0
        for c_idx, chapter in enumerate(chapters):
            chapter_id = conn.execute("INSERT INTO chapters(project_id, idx, title) VALUES(?,?,?)",
                                      (project_id, c_idx, chapter["title"][:200])).lastrowid
            for par in chapter["paragraphs"]:
                conn.execute("INSERT INTO paragraphs(project_id, chapter_id, idx, kind, original, current) "
                             "VALUES(?,?,?,?,?,?)", (project_id, chapter_id, idx, par["kind"], par["text"], par["text"]))
                idx += 1
    pipeline.save_checkpoint(project_id, "Original upload")
    pipeline.write_exports(project_id, ("edited",))
    return get_project(project_id)


@app.get("/api/projects/{project_id}")
def get_project(project_id: int):
    with db.connect() as conn:
        project = _project_or_404(conn, project_id)
        stats = conn.execute("""
            SELECT count(*) AS paragraphs,
                   sum(original != current) AS changed,
                   sum(flagged) AS flagged,
                   sum(reviewed AND original != current) AS reviewed
            FROM paragraphs WHERE project_id=?""", (project_id,)).fetchone()
        words = sum(word_count(r["original"]) for r in conn.execute(
            "SELECT original FROM paragraphs WHERE project_id=? AND kind='body'", (project_id,)))
        project["stats"] = {**dict(stats), "words": words}
        project["job"] = _latest_job(conn, project_id)
        project["checkpoints"] = db.rows(conn.execute(
            "SELECT id, label, created_at FROM checkpoints WHERE project_id=? ORDER BY created_at DESC", (project_id,)))
    return project


class ProjectPatch(BaseModel):
    name: str | None = None
    intensity: str | None = None
    voice_profile: str | None = None
    style_sheet: str | None = None


@app.patch("/api/projects/{project_id}")
def patch_project(project_id: int, patch: ProjectPatch):
    values = patch.model_dump(exclude_none=True)
    if "intensity" in values and values["intensity"] not in ("light", "standard", "heavy"):
        raise HTTPException(400, "intensity must be light, standard or heavy")
    with db.connect() as conn:
        _project_or_404(conn, project_id)
        for key, value in values.items():
            conn.execute(f"UPDATE projects SET {key}=?, updated_at=datetime('now') WHERE id=?", (value, project_id))
    return get_project(project_id)


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: int):
    pipeline.cancel(project_id)
    with db.connect() as conn:
        _project_or_404(conn, project_id)
        conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
    shutil.rmtree(db.project_dir(project_id), ignore_errors=True)
    return {"ok": True}


# --- running the editors -----------------------------------------------------------------

class RunRequest(BaseModel):
    stages: list[str]
    restart: bool = True


@app.post("/api/projects/{project_id}/run")
def run(project_id: int, req: RunRequest):
    stages = [s for s in req.stages if s in STAGES]
    if not stages:
        raise HTTPException(400, "Pick at least one editor")
    with db.connect() as conn:
        _project_or_404(conn, project_id)
    pipeline.enqueue(project_id, stages, req.restart)
    return get_project(project_id)


@app.post("/api/projects/{project_id}/cancel")
def cancel(project_id: int):
    pipeline.cancel(project_id)
    return {"ok": True}


@app.get("/api/projects/{project_id}/job")
def job(project_id: int):
    with db.connect() as conn:
        return _latest_job(conn, project_id)


# --- review ------------------------------------------------------------------------------

@app.get("/api/projects/{project_id}/chapters")
def chapters(project_id: int):
    with db.connect() as conn:
        _project_or_404(conn, project_id)
        return db.rows(conn.execute("""
            SELECT c.id, c.idx, c.title,
                   count(p.id) AS paragraphs,
                   sum(p.original != p.current) AS changed,
                   sum(p.flagged) AS flagged,
                   sum(p.original != p.current AND p.reviewed = 0) AS unreviewed
            FROM chapters c LEFT JOIN paragraphs p ON p.chapter_id = c.id
            WHERE c.project_id=? GROUP BY c.id ORDER BY c.idx""", (project_id,)))


def _paragraph_view(conn, p: dict) -> dict:
    p["changed"] = p["original"] != p["current"]
    p["diff"] = diff_ops(p["original"], p["current"]) if p["changed"] else None
    p["edited_by"] = [s for s in p["edited_by"].split(",") if s]
    p["edits"] = db.rows(conn.execute(
        "SELECT id, stage, before, after, status, note, created_at FROM edits WHERE paragraph_id=? ORDER BY id",
        (p["id"],)))
    del p["done_stages"]
    return p


@app.get("/api/chapters/{chapter_id}/paragraphs")
def chapter_paragraphs(chapter_id: int):
    with db.connect() as conn:
        pars = db.rows(conn.execute("SELECT * FROM paragraphs WHERE chapter_id=? ORDER BY idx", (chapter_id,)))
        return [_paragraph_view(conn, p) for p in pars]


class ParagraphPatch(BaseModel):
    current: str | None = None
    reviewed: bool | None = None
    flagged: bool | None = None


@app.patch("/api/paragraphs/{paragraph_id}")
def patch_paragraph(paragraph_id: int, patch: ParagraphPatch):
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM paragraphs WHERE id=?", (paragraph_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Paragraph not found")
        p = dict(row)
        if patch.current is not None and patch.current.strip() != p["current"]:
            new = " ".join(patch.current.split())
            conn.execute("INSERT INTO edits(project_id, paragraph_id, stage, before, after, status, note) "
                         "VALUES(?,?, 'author', ?,?, 'applied', 'edited in review')",
                         (p["project_id"], paragraph_id, p["current"], new))
            conn.execute("UPDATE paragraphs SET current=?, reviewed=1 WHERE id=?", (new, paragraph_id))
        if patch.reviewed is not None:
            conn.execute("UPDATE paragraphs SET reviewed=? WHERE id=?", (int(patch.reviewed), paragraph_id))
        if patch.flagged is not None:
            conn.execute("UPDATE paragraphs SET flagged=? WHERE id=?", (int(patch.flagged), paragraph_id))
        p = dict(conn.execute("SELECT * FROM paragraphs WHERE id=?", (paragraph_id,)).fetchone())
        view = _paragraph_view(conn, p)
    pipeline.schedule_export(p["project_id"])
    return view


@app.post("/api/paragraphs/{paragraph_id}/revert")
def revert_paragraph(paragraph_id: int):
    """Put the author's original text back."""
    with db.connect() as conn:
        row = conn.execute("SELECT original FROM paragraphs WHERE id=?", (paragraph_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Paragraph not found")
    return patch_paragraph(paragraph_id, ParagraphPatch(current=row["original"], reviewed=True))


@app.post("/api/edits/{edit_id}/apply")
def apply_edit(edit_id: int):
    """Use a specific version from the history (e.g. a rejected suggestion)."""
    with db.connect() as conn:
        edit = conn.execute("SELECT paragraph_id, after FROM edits WHERE id=?", (edit_id,)).fetchone()
        if not edit:
            raise HTTPException(404, "Edit not found")
    return patch_paragraph(edit["paragraph_id"], ParagraphPatch(current=edit["after"], reviewed=True, flagged=False))


# --- checkpoints & exports ---------------------------------------------------------------

@app.post("/api/projects/{project_id}/checkpoints/{checkpoint_id}/restore")
def restore_checkpoint(project_id: int, checkpoint_id: int):
    with db.connect() as conn:
        _project_or_404(conn, project_id)
        if conn.execute("SELECT 1 FROM jobs WHERE project_id=? AND status IN ('queued','running')",
                        (project_id,)).fetchone():
            raise HTTPException(409, "Stop the running job before restoring a checkpoint")
        cp = conn.execute("SELECT data FROM checkpoints WHERE id=? AND project_id=?",
                          (checkpoint_id, project_id)).fetchone()
        if not cp:
            raise HTTPException(404, "Checkpoint not found")
    pipeline.save_checkpoint(project_id, "Before restore")
    with db.connect() as conn:
        for par_id, text in json.loads(cp["data"]).items():
            conn.execute("UPDATE paragraphs SET current=? WHERE id=? AND project_id=?", (text, int(par_id), project_id))
    pipeline.write_exports(project_id)
    return get_project(project_id)


@app.get("/api/projects/{project_id}/export/{kind}")
def export(project_id: int, kind: str):
    with db.connect() as conn:
        project = _project_or_404(conn, project_id)
    if kind == "report":
        body = f"# Story Architect report — {project['name']}\n\n{project['report']}\n\n" \
               f"## Style sheet\n\n{project['style_sheet']}\n"
        return PlainTextResponse(body, headers={
            "Content-Disposition": f'attachment; filename="{project["name"]} - story report.md"'})
    if kind == "source":
        return FileResponse(db.project_dir(project_id) / "source.docx", filename=project["source_filename"])
    if kind not in ("edited", "tracked", "original"):
        raise HTTPException(404, "Unknown export")
    path = pipeline.write_exports(project_id, (kind,))[kind]
    return FileResponse(path, filename=path.name,
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


# Serve the built React app (npm run build) from the same server.
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
