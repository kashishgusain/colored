// Small progressive enhancements. No inline scripts are used anywhere (strict CSP).
document.addEventListener("DOMContentLoaded", () => {
  // confirm dialogs on destructive forms
  document.querySelectorAll("form[data-confirm]").forEach(f => {
    f.addEventListener("submit", e => { if (!window.confirm(f.dataset.confirm)) e.preventDefault(); });
  });
  // show only the relevant part of the contribution form
  const radios = document.querySelectorAll("input[name='submission_type']");
  const apply = () => {
    const val = (document.querySelector("input[name='submission_type']:checked") || {}).value || "text";
    document.querySelectorAll("[data-show-for]").forEach(el => { el.hidden = el.dataset.showFor !== val; });
  };
  radios.forEach(r => r.addEventListener("change", apply));
  if (radios.length) apply();
  document.addEventListener("click", event => {
    const button = event.target.closest("[data-ai-action]");
    if (!button) return;
    const value = button.dataset.aiValue || "";
    if (button.dataset.aiAction === "use-summary") {
      const field = document.querySelector("[name='summary']");
      if (field) field.value = value;
    } else if (button.dataset.aiAction === "append-tags") {
      const field = document.querySelector("[name='tags']");
      if (field) {
        const tags = [...new Set(`${field.value},${value}`.split(",").map(tag => tag.trim().toLowerCase()).filter(Boolean))];
        field.value = tags.join(", ");
      }
    } else if (button.dataset.aiAction === "use-category") {
      const field = document.querySelector("[name='category_id']");
      const option = field && [...field.options].find(item => item.textContent.trim() === value);
      if (option) {
        field.value = option.value;
        field.dispatchEvent(new Event("change", {bubbles: true}));
      }
    }
  });
  const extractButton = document.getElementById("youtube-extract");
  if (extractButton) {
    extractButton.addEventListener("click", async () => {
      const url = document.getElementById("youtube-url").value.trim();
      const error = document.getElementById("youtube-error");
      const result = document.getElementById("youtube-result");
      error.hidden = true;
      result.hidden = true;
      extractButton.disabled = true;
      extractButton.textContent = "Extracting…";
      try {
        const response = await fetch("/api/youtube-transcript", {
          method: "POST",
          headers: {"Content-Type": "application/json", "Accept": "application/json"},
          credentials: "same-origin",
          body: JSON.stringify({url})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "The transcript could not be extracted.");
        const list = document.getElementById("youtube-steps");
        list.replaceChildren(...data.steps.map(step => {
          const item = document.createElement("li");
          item.textContent = step;
          return item;
        }));
        result.hidden = false;
      } catch (e) {
        error.textContent = e.message;
        error.hidden = false;
      } finally {
        extractButton.disabled = false;
        extractButton.textContent = "Extract steps";
      }
    });
  }
  // disable submit buttons after click so large uploads are not sent twice
  document.querySelectorAll("form[data-busy]").forEach(f => {
    f.addEventListener("submit", () => {
      const b = f.querySelector("button[type=submit]");
      if (b) { b.disabled = true; b.textContent = f.dataset.busy; }
    });
  });
  // poll processing status
  const poll = document.getElementById("job-poll");
  if (poll) {
    const url = poll.dataset.url, bar = document.getElementById("job-bar"), stage = document.getElementById("job-stage");
    const tick = async () => {
      try {
        const r = await fetch(url, {headers: {"Accept": "application/json"}, credentials: "same-origin"});
        if (!r.ok) return;
        const d = await r.json();
        if (d.job) { bar.style.width = d.job.progress + "%"; stage.textContent = d.job.stage.replace(/_/g, " "); }
        if (d.status !== "processing") { window.location.reload(); return; }
      } catch (e) { /* ignore and retry */ }
      setTimeout(tick, 2500);
    };
    setTimeout(tick, 1500);
  }
});
