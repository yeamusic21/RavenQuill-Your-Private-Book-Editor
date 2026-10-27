// Small wrapper around fetch for the FastAPI backend.
async function request(method, path, body) {
  const options = { method, headers: {} };
  if (body instanceof FormData) {
    options.body = body;
  } else if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const res = await fetch(`/api${path}`, options);
  if (!res.ok) {
    let message = res.statusText;
    try {
      message = (await res.json()).detail || message;
    } catch {}
    throw new Error(message);
  }
  return res.json();
}

export const api = {
  get: (path) => request("GET", path),
  post: (path, body) => request("POST", path, body),
  put: (path, body) => request("PUT", path, body),
  patch: (path, body) => request("PATCH", path, body),
  del: (path) => request("DELETE", path),
  exportUrl: (projectId, kind) => `/api/projects/${projectId}/export/${kind}`,
};

export const STAGES = [
  { id: "architect", name: "Story Architect", blurb: "Reads the book, reports major plot, character and continuity problems. Changes nothing." },
  { id: "prose", name: "Prose Editor", blurb: "Polishes the writing into publishable prose while keeping your voice." },
  { id: "copyedit", name: "Copyeditor", blurb: "Grammar, punctuation, spelling and consistency. Hands-off." },
  { id: "proofread", name: "Proofreader", blurb: "Book typography (quotes, dashes, ellipses) and a final error sweep." },
];

// One-click choices for the project page; the checkboxes below them still allow any mix.
export const PRESETS = [
  { name: "Full edit", stages: ["architect", "prose", "copyedit", "proofread"] },
  { name: "Copy-edit only", stages: ["copyedit", "proofread"], blurb: "Grammar, typos and typography. Leaves your sentences alone." },
  { name: "Proofread only", stages: ["proofread"] },
  { name: "Story report only", stages: ["architect"] },
];

export const stageName = (id) => STAGES.find((s) => s.id === id)?.name ?? (id === "author" ? "You" : id);

export function formatDuration(seconds) {
  if (seconds == null) return "";
  if (seconds < 90) return `${Math.round(seconds)}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return `${minutes} min`;
  return `${(minutes / 60).toFixed(1)} h`;
}
