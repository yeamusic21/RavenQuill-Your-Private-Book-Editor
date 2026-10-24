"""Text helpers: inline-formatting markup, word diffs, and book typography.

Paragraph text is stored with a tiny markup so italics/bold survive the trip
through the LLM:  <i>italic</i>  and  <b>bold</b>.  Nothing else is a tag.
"""
import re
from difflib import SequenceMatcher

TAG_RE = re.compile(r"(</?[ib]>)")


# --- markup <-> segments -----------------------------------------------------

def to_segments(text: str) -> list[tuple[str, bool, bool]]:
    """'a <i>b</i>' -> [('a ', False, False), ('b', True, False)]"""
    segments, italic, bold = [], False, False
    for part in TAG_RE.split(text):
        if part == "<i>":
            italic = True
        elif part == "</i>":
            italic = False
        elif part == "<b>":
            bold = True
        elif part == "</b>":
            bold = False
        elif part:
            segments.append((part, italic, bold))
    return segments


def from_segments(segments) -> str:
    out = []
    for text, italic, bold in merge_segments(segments):
        if not text:
            continue
        # Keep surrounding spaces outside the tags: " <i>word</i> " not "<i> word </i>"
        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()):]
        core = text.strip()
        if core and (italic or bold):
            if italic:
                core = f"<i>{core}</i>"
            if bold:
                core = f"<b>{core}</b>"
        out.append(lead + core + trail if core else text)
    return "".join(out)


def merge_segments(segments):
    merged = []
    for text, italic, bold in segments:
        if merged and merged[-1][1] == italic and merged[-1][2] == bold:
            merged[-1] = (merged[-1][0] + text, italic, bold)
        else:
            merged.append((text, italic, bold))
    return merged


def strip_markup(text: str) -> str:
    return TAG_RE.sub("", text)


def tag_counts(text: str) -> tuple[int, int]:
    return text.count("<i>"), text.count("<b>")


def word_count(text: str) -> int:
    return len(strip_markup(text).split())


# --- diffs -------------------------------------------------------------------

def tokens(text: str) -> list[tuple[str, bool, bool]]:
    """Split markup text into word tokens (word + trailing space) with formatting."""
    out = []
    for seg_text, italic, bold in to_segments(text):
        for tok in re.findall(r"\S+\s*|\s+", seg_text):
            out.append((tok, italic, bold))
    return out


def diff_ops(before: str, after: str) -> list[dict]:
    """Word-level diff, used by the review screen and the tracked-changes export."""
    a, b = tokens(before), tokens(after)
    # Compare words without trailing whitespace so "word " == "word".
    ka = [(t.rstrip(), i, bo) for t, i, bo in a]
    kb = [(t.rstrip(), i, bo) for t, i, bo in b]
    ops = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, ka, kb, autojunk=False).get_opcodes():
        if tag == "equal":
            ops += [{"op": "equal", "text": t, "i": i, "b": bo} for t, i, bo in b[j1:j2]]
        else:
            if tag in ("delete", "replace"):
                ops += [{"op": "delete", "text": t, "i": i, "b": bo} for t, i, bo in a[i1:i2]]
            if tag in ("insert", "replace"):
                ops += [{"op": "insert", "text": t, "i": i, "b": bo} for t, i, bo in b[j1:j2]]
    # Merge neighbours with the same op/format to keep payloads small.
    merged = []
    for op in ops:
        last = merged[-1] if merged else None
        if last and (last["op"], last["i"], last["b"]) == (op["op"], op["i"], op["b"]):
            last["text"] += op["text"]
        else:
            merged.append(dict(op))
    return merged


def similarity(before: str, after: str) -> float:
    """0..1 word-level similarity, ignoring formatting tags, case and punctuation."""
    def words(text):
        return [w for w in re.sub(r"[^\w\s']", " ", strip_markup(text).lower()).split()]
    a, b = words(before), words(after)
    if not a and not b:
        return 1.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def dialogue(text: str) -> str:
    """Everything inside quotation marks, joined."""
    plain = strip_markup(text)
    parts = re.findall(r"[\"“]([^\"”]+)[\"”]", plain)
    return " ".join(parts)


# --- typography ----------------------------------------------------------------

SCENE_BREAK_RE = re.compile(r"^\s*(?:[*#~•·⁂—–-]\s*){1,7}$")
ELISIONS = ("tis", "twas", "em", "cause", "til", "n", "round", "bout")


def smart_quotes(text: str) -> str:
    chars = list(text)
    for idx, ch in enumerate(chars):
        if ch not in "\"'":
            continue
        prev = chars[idx - 1] if idx > 0 else " "
        nxt = chars[idx + 1] if idx + 1 < len(chars) else " "
        opening = prev.isspace() or prev in "([{—–-/>" or idx == 0
        if ch == '"':
            chars[idx] = "“" if opening else "”"
        else:
            if not opening:
                chars[idx] = "’"  # apostrophe or closing single quote
            else:
                rest = text[idx + 1: idx + 6].lower()
                if nxt.isdigit() or any(rest.startswith(e) and not rest[len(e):len(e) + 1].isalpha() for e in ELISIONS):
                    chars[idx] = "’"  # ’90s, ’em, ’til
                else:
                    chars[idx] = "‘"
    return "".join(chars)


def typography(text: str) -> str:
    """Deterministic book typography. Safe to run more than once."""
    t = text.replace(" ", " ")
    t = re.sub(r"[ \t]+", " ", t).strip()
    t = re.sub(r"\.\s?\.\s?\.", "…", t)          # ... -> …
    t = re.sub(r"\s*---?\s*", "—", t)             # -- or --- -> em dash
    t = re.sub(r"(?<=\w) - (?=\w)", "—", t)        # spaced hyphen between words -> em dash
    t = re.sub(r"(?<=\d)-(?=\d)", "–", t)          # 1990-1995 -> en dash
    t = smart_quotes(t)
    t = re.sub(r" +([,.;:!?…])", r"\1", t)          # no space before punctuation
    t = re.sub(r"<([ib])>\s+", r" <\1>", t)        # keep spaces outside tags
    t = re.sub(r"\s+</([ib])>", r"</\1> ", t)
    t = re.sub(r" {2,}", " ", t).strip()
    return t
