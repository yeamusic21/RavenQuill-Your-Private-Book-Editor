"""Outline Doctor: reviews an outline for holes, one round at a time.

A round is a single LLM request, run in its own thread so the page can poll.
The author answers each hole (fix the outline, reject it, or explain it) and
runs another round; open holes are re-checked and settled ones are never raised again."""
import threading
import traceback

from . import db
from .docx_io import parse_docx
from .llm import LLM, LLMError
from .personas import OUTLINE_SYSTEM, is_repeat, outline_prompt, parse_outline_review
from .textutil import strip_markup

_running: set[int] = set()
_lock = threading.Lock()


def docx_to_text(path) -> str:
    """Flatten a .docx outline to plain text, keeping headings as markdown headings."""
    lines = []
    for chapter in parse_docx(path):
        for par in chapter["paragraphs"]:
            text = strip_markup(par["text"])
            lines.append(f"## {text}" if par["kind"] == "heading" else text)
    return "\n\n".join(lines)


def start_review(outline_id: int) -> bool:
    """Start a round in the background. False if one is already running."""
    with _lock:
        if outline_id in _running:
            return False
        _running.add(outline_id)
    with db.connect() as conn:
        conn.execute("UPDATE outlines SET status='reviewing', error=NULL WHERE id=?", (outline_id,))
    threading.Thread(target=_review, args=(outline_id,), daemon=True, name=f"outline-{outline_id}").start()
    return True


def _review(outline_id: int):
    try:
        run_round(outline_id)
        with db.connect() as conn:
            conn.execute("UPDATE outlines SET status='idle', updated_at=datetime('now') WHERE id=?", (outline_id,))
    except Exception as e:
        if not isinstance(e, LLMError):
            traceback.print_exc()
        with db.connect() as conn:
            conn.execute("UPDATE outlines SET status='error', error=? WHERE id=?", (str(e), outline_id))
    finally:
        with _lock:
            _running.discard(outline_id)


def run_round(outline_id: int):
    with db.connect() as conn:
        outline = dict(conn.execute("SELECT * FROM outlines WHERE id=?", (outline_id,)).fetchone())
        holes = db.rows(conn.execute("SELECT * FROM outline_holes WHERE outline_id=? ORDER BY id", (outline_id,)))
        last = conn.execute("SELECT max(round) AS r FROM outline_rounds WHERE outline_id=?", (outline_id,)).fetchone()
    if not outline["text"].strip():
        raise ValueError("The outline is empty")
    open_holes = [h for h in holes if h["status"] == "open"]
    settled = [h for h in holes if h["status"] != "open"]
    round_no = (last["r"] or 0) + 1

    reply = LLM(db.get_settings()).chat(OUTLINE_SYSTEM, outline_prompt(outline["text"], open_holes, settled), 1500)
    fixed, new = parse_outline_review(reply.text, [h["id"] for h in open_holes])
    new = [h for h in new if not is_repeat(h, holes)]

    with db.connect() as conn:
        for hole_id in fixed:
            conn.execute("UPDATE outline_holes SET status='fixed', resolved_round=? WHERE id=? AND status='open'",
                         (round_no, hole_id))
        for h in new:
            conn.execute("INSERT INTO outline_holes(outline_id, round, title, location, severity, detail) "
                         "VALUES(?,?,?,?,?,?)",
                         (outline_id, round_no, h["title"], h["location"], h["severity"], h["detail"]))
        conn.execute("INSERT INTO outline_rounds(outline_id, round, text, new_holes, fixed_holes) VALUES(?,?,?,?,?)",
                     (outline_id, round_no, outline["text"], len(new), len(fixed)))
