"""The four editors: their prompts and the safety checks on their output.

Editing personas (prose, copyedit, proofread) all work the same way: a batch of
numbered paragraphs goes in, the same numbered paragraphs come out, and every
changed paragraph must pass that persona's guardrails or the edit is rejected
(kept as a suggestion you can apply from the review screen)."""
import re
from dataclasses import dataclass

from .textutil import dialogue, similarity, strip_markup, tag_counts, word_count

# Phrases small models love and human authors rarely wrote. If an edit
# *introduces* one of these it is rejected.
AI_PHRASES = [
    "tapestry", "testament to", "a symphony of", "a dance of", "delve", "palpable",
    "unspoken", "intricate", "the weight of", "couldn't help but", "sent shivers",
    "a stark reminder", "in the grand scheme", "little did", "electric", "visceral",
    "kaleidoscope", "myriad", "ministrations", "barely above a whisper", "eyes sparkling",
    "heart pounding in", "breath she didn't know", "breath he didn't know", "orbs",
    "nestled", "beacon", "realm", "embark", "navigate the", "it's worth noting",
]

FORMAT_RULES = (
    "Text may contain <i>italic</i> and <b>bold</b> tags. Keep them around the same words.\n"
    "Return EVERY paragraph from the EDIT section, in order, each starting with its tag, like:\n"
    "[1] First paragraph text.\n[2] Second paragraph text.\n"
    "If a paragraph needs no changes, return it exactly as it was. "
    "Do not merge, split, add, or drop paragraphs. Output nothing else: no notes, no explanations."
)

PROSE_INTENSITY = {
    "light": "Touch only what a reader would clearly stumble over. When in doubt, leave it alone.",
    "standard": "Clean up anything that reads as amateurish, but keep every sentence recognisably the author's.",
    "heavy": "You may restructure clumsy sentences more freely, but the voice, content and dialogue must stay the author's.",
}

PROSE_SYSTEM = """You are a professional fiction line editor turning a draft into a publishable book.
Your most important rule: the book must still sound exactly like its author. You polish; you do not rewrite.

DO:
- Fix clumsy, run-on, repetitive or confusing sentences.
- Tighten flabby wording and remove accidental repetition of words.
- Smooth awkward transitions and vary monotonous sentence openings.
- Fix grammar, tense slips and obvious errors as you go.

DO NOT:
- Add new content, imagery, metaphors, descriptions or explanations.
- Remove events, details or information.
- Change dialogue, except to fix clear typos. Slang, dialect, profanity and fragments in dialogue are intentional.
- Change point of view, tense, names, tone or humour.
- Make the writing fancier, more formal or more "literary" than the author's own style.
- Use stock phrases such as: {phrases}.

Editing intensity: {intensity}

THE AUTHOR'S VOICE (preserve all of this):
{voice}

{format_rules}"""

COPYEDIT_SYSTEM = """You are a careful, hands-off copyeditor for a novel.
Fix ONLY: spelling, grammar, punctuation, capitalisation, wrong words (their/there, its/it's),
missing or doubled words, and inconsistent spelling of names and terms (use the style sheet).
Do NOT reword sentences, change style, or "improve" anything that is already correct.
Dialogue may be ungrammatical on purpose; only fix clear typos inside quotation marks.

{format_rules}"""

PROOFREAD_SYSTEM = """You are the final proofreader before a novel goes to print.
The text has already been edited and copyedited. Fix ONLY errors that were missed:
typos, doubled or missing words, wrong homophones, missing end punctuation, unbalanced quotation marks.
Change nothing else. Most paragraphs should come back unchanged.

{format_rules}"""

VOICE_SYSTEM = """You analyse an author's writing style so another editor can preserve it.
Describe this author's voice in 8-12 short bullet points covering: point of view and tense;
sentence length and rhythm; vocabulary level; slang, dialect or profanity; how dialogue is written;
deliberate habits (fragments, long sentences, repetition for effect, asides); tone and humour.
Describe, don't judge. No praise, no advice. Output only the bullet points."""

ARCHITECT_NOTES_SYSTEM = """You are a story editor reading a novel one piece at a time and keeping brief notes.
For the excerpt you are given, write compact notes under these headings (skip empty ones):
CHARACTERS: name - role, plus any facts stated (age, looks, relationships, abilities)
PLACES: name - short description
TIMELINE: when this happens, time jumps, dates, durations
EVENTS: the key plot events, one line each
FACTS: rules of the world, important objects, promises or setups that must pay off
PROBLEMS: only MAJOR issues inside this excerpt (contradictions, impossible events, confusing jumps)
Keep it under 200 words. Plain text, no commentary."""

ARCHITECT_REPORT_SYSTEM = """You are a senior developmental editor. You are given chapter-by-chapter notes on a novel.
Write a short report for the author that flags only MAJOR problems: things a reader or agent would notice.
Ignore nitpicks and line-level writing issues.

Use these markdown sections, each a bulleted list with chapter references (skip a section if it has nothing):
## Continuity errors
(contradictions in names, ages, appearance, facts or world rules between chapters)
## Timeline problems
## Plot holes and dropped threads
(setups that never pay off, characters who vanish, unexplained events)
## Character consistency
## Pacing and structure
(chapters where nothing happens, rushed or missing climax, slow opening)
## What's working
(2-4 bullets, brief)

Be specific and concise. If the notes don't show a problem, don't invent one."""

STYLE_SHEET_SYSTEM = """From these notes on a novel, build a style sheet: every character, place, and invented
term with its single correct spelling. One per line, formatted exactly:
Name - few-word description
Pick the most common spelling if the notes disagree. Output only the list."""


@dataclass
class Guard:
    min_similarity: float
    length_range: tuple[float, float]
    check_dialogue: bool = False


GUARDS = {
    ("prose", "light"): Guard(0.80, (0.80, 1.20), True),
    ("prose", "standard"): Guard(0.65, (0.70, 1.25), True),
    ("prose", "heavy"): Guard(0.50, (0.60, 1.30), True),
    ("copyedit", None): Guard(0.85, (0.90, 1.10)),
    ("proofread", None): Guard(0.90, (0.93, 1.07)),
}


def guard_for(stage: str, intensity: str) -> Guard:
    return GUARDS.get((stage, intensity)) or GUARDS[(stage, None)]


def check_edit(stage: str, intensity: str, before: str, after: str) -> str | None:
    """Return a rejection reason, or None if the edit is acceptable."""
    if not after.strip():
        return "empty result"
    g = guard_for(stage, intensity)
    words = word_count(before)
    slack = 0.12 if words < 15 else 0.0  # short paragraphs swing more per word
    sim = similarity(before, after)
    if sim < g.min_similarity - slack:
        return f"changed too much ({sim:.0%} similar, needs {g.min_similarity - slack:.0%})"
    ratio = (word_count(after) + 1) / (words + 1)
    if not (g.length_range[0] - slack <= ratio <= g.length_range[1] + slack):
        return f"length changed too much ({ratio:.0%} of original)"
    if tag_counts(before) != tag_counts(after):
        return "italic/bold formatting was lost or added"
    lower_before, lower_after = strip_markup(before).lower(), strip_markup(after).lower()
    for phrase in AI_PHRASES:
        if phrase in lower_after and phrase not in lower_before:
            return f"introduced stock phrase “{phrase}”"
    if g.check_dialogue:
        d_before, d_after = dialogue(before), dialogue(after)
        if d_before and similarity(d_before, d_after) < 0.8:
            return "rewrote dialogue"
    return None


def system_prompt(stage: str, intensity: str, voice: str) -> str:
    if stage == "prose":
        return PROSE_SYSTEM.format(
            phrases=", ".join(f'"{p}"' for p in AI_PHRASES[:14]),
            intensity=PROSE_INTENSITY.get(intensity, PROSE_INTENSITY["standard"]),
            voice=voice.strip() or "(not analysed yet: infer it from the text and keep it)",
            format_rules=FORMAT_RULES,
        )
    if stage == "copyedit":
        return COPYEDIT_SYSTEM.format(format_rules=FORMAT_RULES)
    return PROOFREAD_SYSTEM.format(format_rules=FORMAT_RULES)


def batch_prompt(batch: list[str], context: list[str], style_sheet: str) -> str:
    parts = []
    if style_sheet.strip():
        parts.append("STYLE SHEET (correct spellings):\n" + style_sheet.strip()[:1500])
    if context:
        parts.append("CONTEXT (earlier text, read-only, do not return it):\n" + "\n\n".join(context))
    parts.append("EDIT:\n" + "\n\n".join(f"[{n}] {text}" for n, text in enumerate(batch, 1)))
    return "\n\n".join(parts)


TAGGED_RE = re.compile(r"^\s*\[(\d+)\]\s?", re.MULTILINE)


def parse_batch(reply: str, expected: int) -> list[str] | None:
    """Parse '[1] ... [2] ...' back into a list. None if it doesn't line up."""
    pieces = TAGGED_RE.split(reply)
    # pieces = [preamble, '1', text1, '2', text2, ...]
    found = {}
    for num, text in zip(pieces[1::2], pieces[2::2]):
        text = re.sub(r"\s*\n\s*", " ", text).strip()
        found.setdefault(int(num), text)
    if sorted(found) != list(range(1, expected + 1)):
        return None
    return [found[n] for n in range(1, expected + 1)]


# --- Outline Doctor ----------------------------------------------------------------------
# Works on an outline instead of a manuscript, in rounds: it re-checks the holes still
# open, and is told which ones the author rejected or explained so it won't raise them again.

OUTLINE_SYSTEM = """You are a book doctor reviewing a novel's OUTLINE before it is written.
Find HOLES: problems that would break the finished story. Look for:
- plot holes and logic gaps (events with no cause, solutions that come from nowhere)
- unmotivated choices (characters acting against their stated goals with no reason)
- setups with no payoff, and payoffs with no setup
- dropped threads and characters who disappear
- timeline and continuity contradictions
- stakes that are unclear, or a climax that the earlier events don't build to
Raise only real holes a reader or agent would notice. Not style, not word choice, not
"add more detail". An outline is a summary: missing detail is not a hole unless the
story can't work without it. If the outline is sound, say so. Don't invent problems.

Reply in exactly this format and nothing else:
CHECK:
[<number>] FIXED or OPEN
(one line for every OPEN HOLE you were given: FIXED if the outline now deals with it, OPEN if not;
skip CHECK if you were given no open holes)
HOLE: <short title>
WHERE: <section, chapter or act>
SEVERITY: <major or minor>
WHY: <1-3 sentences: what's wrong and why it matters>
(repeat HOLE/WHERE/SEVERITY/WHY for each new hole)
Only list holes that are NEW: never repeat an open, fixed or settled hole as a HOLE,
and never use HOLE to say that something was fixed.
If there are no new holes, write NO NEW HOLES."""


def outline_prompt(text: str, open_holes: list[dict], settled: list[dict]) -> str:
    parts = ["OUTLINE:\n" + text.strip()]
    if open_holes:
        parts.append("OPEN HOLES from earlier rounds. Give each one a CHECK line saying whether the outline "
                     "above now fixes it; do not repeat them as new holes:\n" +
                     "\n".join(f"[{h['id']}] {h['title']}: {h['detail']}" for h in open_holes))
    if settled:
        lines = []
        for h in settled:
            if h["status"] == "fixed":
                lines.append(f"- {h['title']} (fixed)")
            else:
                verb = "rejected it" if h["status"] == "rejected" else "explained it"
                why = f': "{h["response"].strip()}"' if h["response"].strip() else ""
                lines.append(f"- {h['title']} (the author {verb}{why})")
        parts.append("SETTLED. The author has dealt with these. Do NOT raise them again in any form, "
                     "and take the author's explanations as true:\n" + "\n".join(lines))
    if open_holes:  # small models follow the end of the prompt best
        ids = ", ".join(str(h["id"]) for h in open_holes)
        parts.append(f"Start your reply with CHECK: and one line for each open hole ({ids}), "
                     "then list any NEW holes.")
    return "\n\n".join(parts)


FIELD_RE = re.compile(r"^\W*(FIXED|HOLE|WHERE|SEVERITY|WHY)\W*?:\s*(.*)$", re.IGNORECASE)
CHECK_RE = re.compile(r"^\W*(?:CHECK\W*)?\[(\d+)\][^\n]*?\b(not fixed|unfixed|still open|open|fixed)\b", re.IGNORECASE)


def parse_outline_review(reply: str, open_ids: list[int]) -> tuple[list[int], list[dict]]:
    """Return (ids of open holes now fixed, new holes). Tolerates markdown and missing fields."""
    fixed: list[int] = []
    holes: list[dict] = []
    field = None
    for raw in reply.splitlines():
        line = raw.strip().strip("*").strip()
        if re.match(r"no new holes", line, re.IGNORECASE):
            field = None
            continue
        if (c := CHECK_RE.match(line)) and field != "WHY":
            if c.group(2).lower() == "fixed" and int(c.group(1)) in open_ids:
                fixed.append(int(c.group(1)))
            continue
        m = FIELD_RE.match(raw.strip())
        if m:
            field, value = m.group(1).upper(), m.group(2).strip().strip("*").strip()
            if field == "FIXED":  # older "FIXED: 1, 2" style, which some models still produce
                fixed += [int(n) for n in re.findall(r"\d+", value) if int(n) in open_ids]
            elif field == "HOLE":
                holes.append({"title": value, "location": "", "severity": "major", "detail": ""})
            elif holes:
                key = {"WHERE": "location", "SEVERITY": "severity", "WHY": "detail"}[field]
                holes[-1][key] = value
            continue
        if line and field == "WHY" and holes:  # WHY ran onto more lines
            holes[-1]["detail"] = f"{holes[-1]['detail']} {line}".strip()
    for h in holes:
        h["severity"] = "minor" if "minor" in h["severity"].lower() else "major"
        h["title"] = h["title"][:200] or h["detail"][:80] or "Untitled hole"
    return sorted(set(fixed)), [h for h in holes if h["title"] or h["detail"]]


def is_repeat(hole: dict, existing: list[dict]) -> bool:
    """Small models often re-raise a hole they just marked fixed (or one the author settled)."""
    return any(similarity(hole["title"], h["title"]) >= 0.75 for h in existing)
