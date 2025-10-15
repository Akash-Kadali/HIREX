/* ============================================================
   HIREX • main.js (v1.1.0 — Unified Frontend Integration)
   ------------------------------------------------------------
   Handles:
   • Resume upload + JD submission
   • Company & role extraction (OpenAI)
   • FastAPI /api/optimize call
   • Caches PDFs, LaTeX, JD Fit Score in localStorage
   • Smooth animated toasts + abort-safe API handling
   Author: Sri Akash Kadali
   ============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("optimize-form");
  const toast = document.getElementById("toast");
  const resumeInput = document.getElementById("resume");
  const jdInput = document.getElementById("jd");
  const humanizeToggle = document.getElementById("use_humanize");

  const API_BASE =
    ["127.0.0.1", "localhost"].includes(window.location.hostname)
      ? "http://127.0.0.1:8000"
      : window.location.origin;

  /* ============================================================
     🧠 Toast Utility
     ============================================================ */
  const showToast = (msg, timeout = 3000) => {
    if (!toast) return alert(msg);
    toast.textContent = msg;
    toast.classList.add("visible");
    clearTimeout(toast._timeout);
    toast._timeout = setTimeout(() => toast.classList.remove("visible"), timeout);
  };

  /* ============================================================
     🧩 Helper Utilities
     ============================================================ */
  const isValidFile = (f) => f && f.name.toLowerCase().endsWith(".tex");

  const disableForm = (state) => {
    if (!form) return;
    [...form.elements].forEach((el) => (el.disabled = state));
    form.style.opacity = state ? 0.6 : 1;
  };

  const persistResults = (data, useHumanize) => {
    try {
      const kv = {
        hirex_tex: data.tex_string || "",
        hirex_pdf: data.pdf_base64 || "",
        hirex_pdf_humanized: data.pdf_base64_humanized || "",
        hirex_timestamp: Date.now(),
        hirex_company: data.company_name || "UnknownCompany",
        hirex_role: data.role || "UnknownRole",
        hirex_use_humanize: useHumanize ? "true" : "false",
        hirex_version: "v1.1.0",
      };
      for (const [k, v] of Object.entries(kv)) localStorage.setItem(k, String(v));

      if (Array.isArray(data.saved_paths))
        localStorage.setItem("hirex_saved_paths", JSON.stringify(data.saved_paths));

      // JD Fit Score
      const score =
        typeof data.rating_score === "number"
          ? data.rating_score
          : typeof data.coverage_ratio === "number"
          ? Math.round(data.coverage_ratio * 100)
          : null;
      if (score !== null) localStorage.setItem("hirex_rating_score", String(score));

      const history = data.rating_history || data.coverage_history || [];
      localStorage.setItem("hirex_rating_history", JSON.stringify(history));

      console.groupCollapsed("%c[HIREX] ✅ Cached optimization results", "color:#6ea8fe;font-weight:bold;");
      console.table({
        Company: data.company_name,
        Role: data.role,
        "Has PDF": !!data.pdf_base64,
        "Humanized": !!data.pdf_base64_humanized,
        "JD Fit": score ?? "n/a",
        Rounds: Array.isArray(history) ? history.length : "n/a",
      });
      console.groupEnd();
    } catch (err) {
      console.error("[HIREX] Cache error:", err);
    }
  };

  /* ============================================================
     🚀 Submit Handler
     ============================================================ */
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = resumeInput?.files?.[0];
    const jd = jdInput?.value?.trim();
    const useHumanize = humanizeToggle?.checked;

    if (!isValidFile(file) || !jd) {
      showToast("⚠️ Please upload a valid .tex file and paste the job description.");
      return;
    }

    disableForm(true);
    showToast("⏳ Optimizing your resume... This may take up to 2–3 minutes.");

    const formData = new FormData();
    formData.append("base_resume_tex", file);
    formData.append("jd_text", jd);
    formData.append("use_humanize", useHumanize ? "true" : "false");

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 180000);

    // Add temporary cancel button (UX)
    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "❌ Cancel";
    cancelBtn.className = "cta-secondary";
    cancelBtn.style.marginTop = "1rem";
    form.appendChild(cancelBtn);
    cancelBtn.onclick = () => {
      controller.abort();
      showToast("🛑 Optimization canceled by user.");
      cancelBtn.remove();
    };

    try {
      const res = await fetch(`${API_BASE}/api/optimize`, {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });
      clearTimeout(timeout);
      cancelBtn.remove();

      if (!res.ok) {
        const errText = await res.text().catch(() => "");
        throw new Error(errText || `HTTP ${res.status}`);
      }

      const data = await res.json();
      if (!data?.tex_string) throw new Error("Empty LaTeX output from backend.");

      persistResults(data, useHumanize);

      const company = data.company_name || "Company";
      const role = data.role || "Role";
      const score =
        typeof data.rating_score === "number"
          ? `${data.rating_score}/100`
          : typeof data.coverage_ratio === "number"
          ? `${Math.round((data.coverage_ratio || 0) * 100)}/100`
          : "n/a";

      showToast(`✅ Optimized for ${company} (${role}) — JD Fit ${score}`);
      setTimeout(() => (window.location.href = "/preview.html"), 1500);
    } catch (err) {
      console.error("[HIREX] Optimization error:", err);
      if (err.name === "AbortError")
        showToast("⚠️ Optimization canceled or timed out (3 min limit).");
      else if (err.message?.includes("Failed to fetch"))
        showToast("🌐 Network error — check FastAPI connection.");
      else showToast("❌ " + (err.message || "Unexpected error occurred."));
    } finally {
      clearTimeout(timeout);
      disableForm(false);
      cancelBtn.remove?.();
    }
  });

  /* ============================================================
     🔄 Reset Handler
     ============================================================ */
  form?.addEventListener("reset", () => {
    [
      "hirex_tex",
      "hirex_timestamp",
      "hirex_company",
      "hirex_role",
      "hirex_use_humanize",
      "hirex_pdf",
      "hirex_pdf_humanized",
      "hirex_saved_paths",
      "hirex_rating_score",
      "hirex_rating_history",
      "hirex_version",
    ].forEach((k) => localStorage.removeItem(k));
    showToast("🧹 Cleared form and local cache.");
  });

  /* ============================================================
     🖋️ UX Enhancements
     ============================================================ */
  jdInput?.addEventListener("focus", () =>
    jdInput.scrollIntoView({ behavior: "smooth", block: "center" })
  );

  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key === "Enter") form?.requestSubmit();
  });

  // Drag-drop for .tex file
  form?.addEventListener("dragover", (e) => e.preventDefault());
  form?.addEventListener("drop", (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (isValidFile(file)) {
      resumeInput.files = e.dataTransfer.files;
      showToast(`📄 Selected file: ${file.name}`);
    } else {
      showToast("⚠️ Only .tex files supported.");
    }
  });

  /* ============================================================
     ✅ Init Log
     ============================================================ */
  console.log(
    "%c[HIREX] main.js initialized — v1.1.0 (Unified Frontend)",
    "color:#6ea8fe;font-weight:bold;"
  );

  HIREX?.debugLog?.("MAIN JS LOADED", {
    version: "v1.1.0",
    page: "index.html",
    origin: window.location.origin,
  });
});
