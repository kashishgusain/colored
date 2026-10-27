// Ask LOKVAANI AI: posts the question as JSON with the CSRF token and renders the answer with its sources.
(() => {
  const form = document.getElementById("chat-form");
  if (!form) return;
  const log = document.getElementById("chat-log"), input = document.getElementById("chat-input");
  const token = document.querySelector("meta[name='csrf-token']").content;
  const MODE = {
    ai_answer: "AI answer from approved records",
    retrieval_only: "Retrieval only (no AI summary)",
    llm_error: "AI unavailable: showing records",
    no_evidence: "Not found in the archive",
  };

  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text) n.textContent = text; return n; };

  function addUser(text) {
    const m = el("div", "msg user"); m.append(el("div", "who", "You"), el("div", "bubble", text)); log.append(m); scroll();
  }
  function addBot(d) {
    const m = el("div", "msg bot");
    m.append(el("div", "who", "LOKVAANI AI"));
    const b = el("div", "bubble");
    b.append(el("span", "mode-tag mode-" + d.mode, MODE[d.mode] || d.mode), el("br"));
    // citations like [1] are highlighted; everything is inserted as text, never as HTML
    d.answer.split(/(\[\d{1,2}\])/).forEach(part => b.append(/^\[\d{1,2}\]$/.test(part) ? el("span", "cite", part) : document.createTextNode(part)));
    m.append(b);
    (d.sources || []).forEach(s => {
      const box = el("div", "source");
      const a = el("a", null, `[${s.n}] ${s.title}`); a.href = s.url;
      box.append(a, el("span", "text-muted-2", ` — ${s.category}, ${s.language}${s.district ? ", " + s.district : ""}`));
      const q = el("q", null, s.excerpt); box.append(q);
      box.append(el("small", "text-muted-2", `Verified by ${s.verified_by}${s.verified_on ? " on " + s.verified_on : ""}. Credit: ${s.attribution}`));
      m.append(box);
    });
    if (d.note) m.append(el("div", "small text-muted-2 mt-1", d.note));
    log.append(m); scroll();
  }
  const scroll = () => { log.scrollTop = log.scrollHeight; };

  async function ask(question) {
    addUser(question);
    const btn = form.querySelector("button[type=submit]"); btn.disabled = true;
    const wait = el("div", "msg bot"); wait.append(el("div", "bubble text-muted-2", "Searching the approved archive…")); log.append(wait); scroll();
    try {
      const r = await fetch(form.dataset.url, {method: "POST", credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-CSRFToken": token}, body: JSON.stringify({question})});
      const d = await r.json();
      wait.remove();
      if (!r.ok) { const m = el("div", "msg bot"); m.append(el("div", "bubble", d.error || d.message || "Something went wrong.")); log.append(m); }
      else addBot(d);
    } catch (e) { wait.remove(); const m = el("div", "msg bot"); m.append(el("div", "bubble", "The server could not be reached. Try again.")); log.append(m); }
    btn.disabled = false; input.focus();
  }
  form.addEventListener("submit", e => { e.preventDefault(); const q = input.value.trim(); if (q.length < 3) return; input.value = ""; ask(q); });
  document.querySelectorAll(".suggest").forEach(b => b.addEventListener("click", () => ask(b.dataset.q)));
  scroll();
})();
