document.addEventListener("DOMContentLoaded", () => {
  // Mobile nav toggle
  const toggle = document.querySelector(".nav-toggle");
  const links = document.querySelector(".nav-links");
  if (toggle && links) {
    toggle.addEventListener("click", () => links.classList.toggle("open"));
  }

  // Transcript language tabs
  document.querySelectorAll(".transcript-tabs").forEach((tabs) => {
    const buttons = tabs.querySelectorAll("button");
    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        buttons.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        const target = btn.dataset.target;
        document.querySelectorAll(".transcript-pane").forEach((p) => p.classList.remove("active"));
        document.getElementById(target).classList.add("active");
      });
    });
  });

  // Upload status polling
  const statusRoot = document.querySelector("[data-status-url]");
  if (statusRoot) {
    const url = statusRoot.dataset.statusUrl;
    const recordUrlBase = statusRoot.dataset.recordUrlBase;
    const steps = ["uploading", "transcribing", "extracting", "indexing"];

    const setStep = (name, state) => {
      const el = document.querySelector(`[data-step="${name}"]`);
      if (!el) return;
      el.classList.remove("done", "active", "failed");
      el.classList.add(state);
    };

    steps.forEach((s, i) => setStep(s, i === 0 ? "done" : "active"));

    const poll = () => {
      fetch(url)
        .then((r) => r.json())
        .then((data) => {
          if (data.status === "processing") {
            setStep("uploading", "done");
            setStep("transcribing", "active");
            setTimeout(poll, 2000);
          } else if (data.status === "ai_extracted" || data.status === "community_verified") {
            steps.forEach((s) => setStep(s, "done"));
            const msg = document.querySelector("[data-status-message]");
            if (msg) {
              msg.textContent = data.is_demo_ai
                ? "Done (demo mode — no live API key configured)."
                : "Your knowledge has been organized. Ready for review.";
            }
            const link = document.querySelector("[data-review-link]");
            if (link && data.knowledge_id) {
              link.href = `${recordUrlBase}${data.knowledge_id}/review`;
              link.classList.remove("btn-disabled-placeholder");
              link.removeAttribute("disabled");
            }
          } else if (data.status === "failed") {
            steps.forEach((s) => setStep(s, "failed"));
            const msg = document.querySelector("[data-status-message]");
            if (msg) msg.textContent = data.error_message || "Something went wrong. Please try again.";
          } else {
            setTimeout(poll, 2000);
          }
        })
        .catch(() => setTimeout(poll, 3000));
    };
    poll();
  }
});
