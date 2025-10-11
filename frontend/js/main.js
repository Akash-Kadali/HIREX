/* ============================================================
   HIREX • main.js (LaTeX-only version, with extended timeout)
   Handles resume upload, JD submission, and backend optimization API call.
   Optimized for long-running AI/Humanize operations (up to 3 minutes).
   Author: Sri Akash Kadali
   ============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("optimize-form");
  const toast = document.getElementById("toast");

  // Detect backend endpoint (local FastAPI vs packaged PyWebview app)
  const API_BASE =
    window.location.hostname === "127.0.0.1" ||
    window.location.hostname === "localhost"
      ? "http://127.0.0.1:8000"
      : window.location.origin;

  /* ============================================================
     🧠 Toast Notification System
     ============================================================ */
  function showToast(message, timeout = 2500) {
    if (!toast) return alert(message);
    toast.textContent = message;
    toast.classList.add("show");
    toast.style.display = "block";
    setTimeout(() => {
      toast.classList.remove("show");
      setTimeout(() => (toast.style.display = "none"), 250);
    }, timeout);
  }

  /* ============================================================
     🧩 Utility Helpers
     ============================================================ */
  function isValidFile(file) {
    return file && file.name.toLowerCase().endsWith(".tex");
  }

  function disableForm(disabled = true) {
    if (!form) return;
    for (const el of form.elements) el.disabled = disabled;
  }

  function persistResults(data) {
    try {
      localStorage.setItem("hirex_tex", data.tex_string || "");
      localStorage.setItem("hirex_timestamp", Date.now().toString());
      console.log("%c[HIREX] Saved optimized LaTeX to localStorage ✅", "color:#6a4fff");
    } catch (err) {
      console.error("[HIREX] Failed to persist results:", err);
      showToast("⚠️ Unable to cache output in browser.");
    }
  }

  /* ============================================================
     🚀 Form Submission — Main Handler
     ============================================================ */
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();

    HIREX?.debugLog?.("FORM SUBMIT triggered");

    const resumeFile = document.getElementById("resume")?.files?.[0];
    const jdText = document.getElementById("jd")?.value?.trim();

    if (!isValidFile(resumeFile) || !jdText) {
      showToast("⚠️ Please upload a valid .tex file and paste a job description.");
      HIREX?.debugLog?.("FORM INVALID", {
        hasFile: !!resumeFile,
        jdLen: jdText?.length || 0,
      });
      return;
    }

    disableForm(true);
    showToast("⏳ Optimizing your resume... (may take 2–3 minutes)");
    HIREX?.debugLog?.("FORM VALID", {
      file: resumeFile.name,
      jdLen: jdText.length,
    });

    try {
      const formData = new FormData();
      formData.append("base_resume_tex", resumeFile);
      formData.append("jd_text", jdText);

      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 180000); // ⏰ 3 min timeout

      HIREX?.debugLog?.("FETCH /api/optimize → start", {
        apiBase: API_BASE,
        timeoutMs: 180000,
      });

      const response = await fetch(`${API_BASE}/api/optimize`, {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });

      clearTimeout(timeout);
      HIREX?.debugLog?.("FETCH /api/optimize → complete", { status: response.status });

      if (!response.ok) {
        const errText = await response.text();
        HIREX?.debugLog?.("FETCH ERROR", { status: response.status, errText });
        throw new Error(`Server error (${response.status}): ${errText || "Unknown error"}`);
      }

      const data = await response.json();
      HIREX?.debugLog?.("FETCH JSON parsed", {
        hasTex: !!data.tex_string,
        texLen: (data.tex_string || "").length,
      });

      if (!data || !data.tex_string) {
        HIREX?.debugLog?.("FETCH INVALID DATA", data);
        throw new Error("Invalid response from backend.");
      }

      // 💾 Save for Preview
      persistResults(data);
      HIREX?.debugLog?.("LOCALSTORAGE SAVED", {
        texLen: (data.tex_string || "").length,
        keys: Object.keys(localStorage),
      });

      // 🔍 Verify saved data immediately
      console.log("[HIREX] Cached LaTeX sample:", (data.tex_string || "").slice(0, 200));

      showToast("✅ Resume optimized successfully! Redirecting...");
      console.log("[HIREX] Optimization complete:", data);

      HIREX?.debugLog?.("REDIRECT → preview.html");
      setTimeout(() => (window.location.href = "/preview.html"), 1200);
    } catch (err) {
      HIREX?.debugLog?.("FORM ERROR", { msg: err.message, name: err.name });
      if (err.name === "AbortError") {
        showToast("⚠️ Request timed out. The optimization took longer than expected.");
      } else if (err.name === "TypeError") {
        showToast("🌐 Network error. Check backend connection.");
      } else {
        console.error("[HIREX] Optimization Error:", err);
        showToast(`❌ ${err.message || "Unexpected error occurred."}`);
      }
    } finally {
      disableForm(false);
    }
  });

  /* ============================================================
     🔄 Reset Handler
     ============================================================ */
  form?.addEventListener("reset", () => {
    ["hirex_tex", "hirex_timestamp"].forEach((k) => localStorage.removeItem(k));
    showToast("🧹 Cleared form and cache.");
    HIREX?.debugLog?.("FORM RESET + CACHE CLEARED");
  });

  /* ============================================================
     🖋️ UX Enhancements
     ============================================================ */
  const jdBox = document.getElementById("jd");
  if (jdBox) {
    jdBox.addEventListener("focus", () => {
      jdBox.scrollIntoView({ behavior: "smooth", block: "center" });
      HIREX?.debugLog?.("JD BOX FOCUSED");
    });
  }

  // Ctrl+Enter quick submit
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key === "Enter") {
      e.preventDefault();
      HIREX?.debugLog?.("CTRL+ENTER SUBMIT");
      form?.requestSubmit();
    }
  });

  // Drag & Drop file upload
  form?.addEventListener("dragover", (e) => e.preventDefault());
  form?.addEventListener("drop", (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (isValidFile(file)) {
      document.getElementById("resume").files = e.dataTransfer.files;
      showToast(`📄 File selected: ${file.name}`);
      HIREX?.debugLog?.("FILE DROPPED", { name: file.name });
    } else {
      showToast("⚠️ Only .tex files are supported.");
      HIREX?.debugLog?.("INVALID FILE DROP", { name: file?.name });
    }
  });

  /* ============================================================
     ✅ Initialization Log
     ============================================================ */
  console.log("%c[HIREX] main.js initialized (extended timeout mode).", "color:#4f8cff;font-weight:bold;");
  HIREX?.debugLog?.("MAIN INIT COMPLETE", {
    api: API_BASE,
    hasForm: !!form,
    origin: window.location.origin,
    timeoutMs: 180000,
  });
});
