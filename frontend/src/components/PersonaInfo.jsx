import { useEffect, useRef } from "react";
import { stageName } from "../api.js";
import { SimpleMarkdown } from "./Markup.jsx";

// Longer explanations for the "Learn more" dialog on the project page.
// Example parts are plain strings, or {del, ins} for a change.
// The percentages match the guardrails in backend/ravenquill/personas.py.
export const PERSONA_INFO = {
  architect: {
    summary:
      "Reads the whole book like a developmental editor and writes a report on the big-picture problems. It never changes your text.",
    does: [
      "Reads each chapter in chunks and keeps notes on characters, places, timeline, events and world rules.",
      "Writes a Story report flagging continuity errors, timeline problems, plot holes, dropped threads, character inconsistencies and pacing issues, with chapter references.",
      "Builds the style sheet (every name and invented term with one spelling) that the Copyeditor and other editors use for consistency.",
    ],
    doesnt: [
      "Edit any paragraphs.",
      "Comment on line-level writing. That's the Prose Editor's job.",
    ],
    expect: [
      "The report appears on the project page and as a .md download.",
      "It's a starting point, not a verdict. Small local models sometimes miss things or misread a scene, so check each point against the book.",
      "Run it first so the style sheet is ready for the other editors. Fix spellings in the style sheet if it guessed wrong.",
    ],
    examples: [
      {
        title: "From a Story report",
        markdown:
          "## Continuity errors\n- **Ch. 3 vs Ch. 11:** Mara's eyes are grey in chapter 3 and brown in chapter 11.\n## Plot holes and dropped threads\n- **Ch. 5:** The locked chest is set up as important but never opened or mentioned again.",
      },
      { title: "From a style sheet", markdown: "Mara Quill - painter, the narrator's sister\nCentra - attendant at the gallery" },
    ],
  },
  prose: {
    summary:
      "A line editor that polishes clumsy writing into publishable prose while keeping the book sounding like you.",
    does: [
      "Fixes run-on, repetitive or confusing sentences and tightens flabby wording.",
      "Smooths awkward transitions and varies monotonous sentence openings.",
      "Fixes grammar and tense slips it comes across.",
      "Before it starts, builds an author voice profile from your chapters and is told to preserve it. You can edit the profile on the project page.",
    ],
    doesnt: [
      "Add new content, imagery or metaphors, or remove events and details.",
      "Rewrite dialogue. Slang, dialect and fragments in quotes are treated as intentional.",
      "Change point of view, tense, names or tone, or make the style fancier than yours.",
      "Touch layout or indentation. That's applied when you download the book.",
    ],
    expect: [
      "The slowest editor, and the one that changes the most. Review its edits most closely.",
      "Intensity sets how far it may go. A paragraph must stay at least 80% similar on Light, 65% on Standard and 50% on Heavy.",
      "Edits that change too much, change the length a lot, rewrite dialogue, drop italics or add stock AI phrases (“tapestry”, “a testament to”…) are held back and marked ⚑. Open the marker to use one anyway.",
    ],
    examples: [
      {
        title: "Tightening a repetitive sentence",
        parts: [
          "She walked ",
          { del: "slowly " },
          "across the room",
          { del: " and she sat down in the chair slowly, and she", ins: ", sat down and" },
          " looked at the letter.",
        ],
      },
      {
        title: "Dialogue left alone, narration tidied",
        parts: [
          "“I ain’t going nowhere,” Jess said, ",
          { del: "and she crossed her arms over her chest and she glared", ins: "crossing her arms and glaring" },
          " at him.",
        ],
      },
      {
        title: "Held back ⚑ (stock phrase added)",
        parts: ["The market was ", { del: "loud and crowded", ins: "a tapestry of sound and colour" }, "."],
        note: "Rejected automatically. You'll see it in the paragraph's history.",
      },
    ],
  },
  copyedit: {
    summary: "A hands-off copyeditor that fixes errors and leaves your sentences alone.",
    does: [
      "Fixes spelling, grammar, punctuation and capitalisation.",
      "Fixes wrong words (their/there, its/it’s) and missing or doubled words.",
      "Makes names and terms match the style sheet.",
    ],
    doesnt: [
      "Reword sentences or “improve” anything that's already correct.",
      "Correct deliberately ungrammatical dialogue, apart from clear typos.",
      "Touch layout or indentation. That's applied when you download the book.",
    ],
    expect: [
      "Small, scattered changes. Most paragraphs come back untouched.",
      "An edit is held back ⚑ if the paragraph ends up less than 85% similar or more than 10% longer or shorter.",
      "Small local models do miss things. Running the Proofreader afterwards catches some of them.",
    ],
    examples: [
      {
        title: "Wrong words and punctuation",
        parts: [{ del: "Their", ins: "They’re" }, " going to be late", { del: ",", ins: ";" }, " ", { del: "its", ins: "it’s" }, " already past ten."],
      },
      {
        title: "Punctuating a dialogue tag",
        parts: ["“I don’t mean to ", { del: "offend”", ins: "offend,”" }, " she said."],
      },
      {
        title: "Style sheet consistency",
        parts: [{ del: "Katheryn", ins: "Kathryn" }, " grabbed ", { del: "the the", ins: "the" }, " map."],
      },
      {
        title: "Left alone",
        parts: ["Cold. Dark. Nobody home."],
        note: "Fragments are a style choice, not an error.",
      },
    ],
  },
  proofread: {
    summary: "The final pass before print: book typography plus a last sweep for errors the other editors missed.",
    does: [
      "Applies book typography without using the model: curly quotes and apostrophes, em dashes, en dashes in number ranges, real ellipses (…), and no stray spaces before punctuation.",
      "Then the model sweeps for typos, doubled or missing words, wrong homophones, missing end punctuation and unbalanced quotes. You can turn this sweep off in Settings.",
    ],
    doesnt: [
      "Reword anything, or change style or grammar that isn't clearly wrong.",
      "Touch layout or indentation. That's applied when you download the book.",
    ],
    expect: [
      "The strictest guardrails: an edit is held back ⚑ if the paragraph ends up less than 90% similar or more than 7% longer or shorter.",
      "Typography changes show up in many paragraphs, since every straight quote becomes a curly one.",
      "Safe to run more than once.",
    ],
    examples: [
      {
        title: "Typography",
        parts: [
          { del: "\"Wait...\"", ins: "“Wait…”" },
          " she said",
          { del: " -- ", ins: "—" },
          "then stopped. It was the summer of ",
          { del: "'92", ins: "’92" },
          ".",
        ],
      },
      { title: "Number ranges", parts: ["Read pages ", { del: "10-12", ins: "10–12" }, " tonight."] },
      { title: "A missed error", parts: ["He picked up the cup and ", { del: "drunk", ins: "drank" }, "."] },
    ],
  },
  outline: {
    summary:
      "Reads your outline before you write the book and reports the holes: anything that would break the finished story. It works in rounds until no holes are left open.",
    does: [
      "Looks for plot holes, logic gaps, unmotivated choices, setups with no payoff (and payoffs with no setup), dropped threads, timeline contradictions, unclear stakes and climaxes the story doesn't build to.",
      "On every later round, re-reads your updated outline and marks open holes as fixed when the outline now covers them.",
      "Is told which holes you rejected or explained, and takes your explanations as true, so it won't keep raising them.",
    ],
    doesnt: [
      "Change your outline. You edit it; it only reports.",
      "Comment on wording, or ask for more detail just because an outline is a summary.",
    ],
    expect: [
      "Answer each hole: fix the outline, Reject it (with an optional reason), or Explain it (say how it works). Then press Check again.",
      "You're done when a round finds no new holes and none are left open.",
      "Each round is one request, so it reads the whole outline at once. Very long outlines need a bigger context length in LM Studio.",
      "Small local models can misread an outline. Rejecting a hole you disagree with is normal.",
    ],
    examples: [
      {
        title: "A hole it might raise",
        markdown:
          "### Sword from nowhere (Act 3, major)\nMara defeats the Duke with a sword that's never mentioned before. The climax depends on it, so it needs a setup.",
      },
      {
        title: "Explained, so it won't come up again",
        markdown: "### Why the locksmith? (Act 2, minor)\n**You:** Her mother's letter in Act 1 names him.",
      },
    ],
  },
};

export function PersonaModal({ stageId, onClose }) {
  const dialog = useRef(null);
  const info = PERSONA_INFO[stageId];

  useEffect(() => {
    dialog.current?.showModal();
  }, []);

  return (
    <dialog
      ref={dialog}
      className="persona-modal"
      onClose={onClose}
      onClick={(e) => e.target === dialog.current && dialog.current.close()}
    >
      <div className="persona-modal-body">
        <div className="persona-modal-head">
          <h2>{stageName(stageId)}</h2>
          <button className="small" onClick={() => dialog.current.close()} aria-label="Close">
            ✕
          </button>
        </div>
        <p>{info.summary}</p>

        <h3>What it does</h3>
        <ul>{info.does.map((t) => <li key={t}>{t}</li>)}</ul>
        <h3>What it won't do</h3>
        <ul>{info.doesnt.map((t) => <li key={t}>{t}</li>)}</ul>
        <h3>What to expect</h3>
        <ul>{info.expect.map((t) => <li key={t}>{t}</li>)}</ul>

        <h3>Examples</h3>
        {info.examples.map((ex) => (
          <div key={ex.title} className="persona-example">
            <div className="muted small-text">{ex.title}</div>
            {ex.markdown ? (
              <SimpleMarkdown text={ex.markdown} />
            ) : (
              <p className="persona-example-text">
                {ex.parts.map((part, n) =>
                  typeof part === "string" ? (
                    <span key={n}>{part}</span>
                  ) : (
                    <span key={n}>
                      {part.del && <span className="delete">{part.del}</span>}
                      {part.ins && <span className="insert">{part.ins}</span>}
                    </span>
                  )
                )}
              </p>
            )}
            {ex.note && <div className="muted small-text">{ex.note}</div>}
          </div>
        ))}
      </div>
    </dialog>
  );
}
