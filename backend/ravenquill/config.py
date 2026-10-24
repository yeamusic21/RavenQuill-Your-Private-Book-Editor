"""Paths and default settings."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("RAVENQUILL_DATA", ROOT / "data"))
DB_PATH = DATA_DIR / "ravenquill.db"
PROJECTS_DIR = DATA_DIR / "projects"
FRONTEND_DIST = ROOT / "frontend" / "dist"

STAGES = ["architect", "prose", "copyedit", "proofread"]

# Every value here can be changed from the Settings page.
DEFAULT_SETTINGS = {
    # LM Studio's local server (Developer tab -> Start Server).
    "base_url": "http://localhost:1234/v1",
    "model": "",  # empty = whatever model LM Studio has loaded
    "temperature": 0.3,
    # How many words of manuscript go into one editing request.
    # Smaller = safer on slow machines and small context windows.
    "batch_words": 250,
    # Paragraphs before the batch that the model sees (read-only) for continuity.
    "context_paragraphs": 2,
    # Words per chunk when the Story Architect reads a chapter.
    "architect_chunk_words": 1500,
    # Extra output tokens allowed for "thinking" models (DeepSeek-R1, Qwen3...).
    # Set to 0 for regular instruct models.
    "reasoning_budget": 2048,
    "request_timeout": 900,
    # Run an LLM sweep in the proofread stage (typography always runs).
    "proofread_llm": True,
    # Book formatting for exported .docx files.
    "book_font": "Garamond",
    "font_size": 11,
    "trim": "6x9",  # "6x9", "5.5x8.5" or "letter"
    "scene_break": "* * *",
}
