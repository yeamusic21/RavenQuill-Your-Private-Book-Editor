import { Markup } from "./Markup.jsx";

// Trim size and margins in inches; mirrors TRIMS in backend/ravenquill/docx_io.py.
const TRIMS = { "6x9": [6, 0.75], "5.5x8.5": [5.5, 0.7], letter: [8.5, 1] };
const PX_PER_INCH = 96;
const SCALE = 1.4; // a little larger than print so it reads comfortably on screen

// Shows a chapter the way the exported .docx lays it out: same font, trim width,
// first-line indents (none after headings or scene breaks), centred headings and
// scene breaks. It's one continuous page, so page breaks will differ from Word's.
export default function BookPreview({ paragraphs, settings, onSelect }) {
  const [width, margin] = TRIMS[settings.trim] ?? TRIMS["6x9"];
  const inch = PX_PER_INCH * SCALE;
  const pt = (n) => `${(n * PX_PER_INCH * SCALE) / 72}px`;
  const size = Number(settings.font_size) || 11;
  const style = {
    "--page-width": `${width * inch}px`,
    "--page-margin": `${margin * inch}px`,
    "--page-indent": `${0.3 * inch}px`,
    "--page-font-size": pt(size),
    "--page-heading-size": pt(size + 7),
    "--page-heading-after": pt(30),
    "--page-scene-space": pt(size),
    fontFamily: `"${settings.book_font || "Garamond"}", var(--book-font)`,
  };

  let previous = "heading";
  return (
    <div className="book-preview">
      <p className="muted small-text">
        Preview at {settings.trim || "6x9"} trim in {settings.book_font || "Garamond"} {size}pt. Shown as one continuous
        page; click a paragraph to review it.
      </p>
      <article className="book-page" style={style}>
        {paragraphs.map((p) => {
          let node;
          if (p.kind === "heading") {
            node = (
              <h2 key={p.id} className="book-heading" onClick={() => onSelect(p.id)}>
                <Markup text={p.current} />
              </h2>
            );
          } else if (p.kind === "scene_break") {
            node = (
              <p key={p.id} className="book-scene">
                {settings.scene_break || p.current}
              </p>
            );
          } else {
            const first = previous === "heading" || previous === "scene_break";
            node = (
              <p key={p.id} className={`book-para${first ? " first" : ""}`} onClick={() => onSelect(p.id)}>
                <Markup text={p.current} />
              </p>
            );
          }
          previous = p.kind;
          return node;
        })}
      </article>
    </div>
  );
}
