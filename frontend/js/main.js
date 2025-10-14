/* ============================================================
   HIREX • main.js (Auto Company/Role Extraction + PDF Ready)
   Handles resume upload, JD submission, and backend optimization API call.
   Automatically extracts Company & Role from JD via backend OpenAI call.
   Stores both Original and Humanized PDFs if available.
   Author: Sri Akash Kadali
   ============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("optimize-form");
  const toast = document.getElementById("toast");

  const API_BASE =
    ["127.0.0.1", "localhost"].includes(window.location.hostname)
      ? "http://127.0.0.1:8000"
      : window.location.origin;

  /* ============================================================
     🧠 Toast Utility
     ============================================================ */
  function showToast(msg, timeout = 2500) {
    if (!toast) return alert(msg);
    toast.textContent = msg;
    toast.style.display = "block";
    toast.style.opacity = "1";
    setTimeout(() => {
      toast.style.opacity = "0";
      setTimeout(() => (toast.style.display = "none"), 300);
    }, timeout);
  }

  /* ============================================================
     🧩 Helpers
     ============================================================ */
  const isValidFile = (f) => f && f.name.toLowerCase().endsWith(".tex");
  const disableForm = (state) =>
    form && [...form.elements].forEach((el) => (el.disabled = state));

  const persistResults = (data, useHumanize) => {
    try {
      localStorage.setItem("hirex_tex", data.tex_string || "");
      localStorage.setItem("hirex_pdf", data.pdf_base64 || "");
      localStorage.setItem("hirex_pdf_humanized", data.pdf_base64_humanized || "");
      localStorage.setItem("hirex_timestamp", Date.now().toString());
      localStorage.setItem("hirex_company", data.company_name || "UnknownCompany");
      localStorage.setItem("hirex_role", data.role || "UnknownRole");
      localStorage.setItem("hirex_use_humanize", useHumanize ? "true" : "false");

      console.log("%c[HIREX] Cached optimization results ✅", "color:#6a4fff");
      console.table({
        Company: data.company_name,
        Role: data.role,
        "Has PDF": !!data.pdf_base64,
        "Has Humanized": !!data.pdf_base64_humanized,
      });
    } catch (e) {
      console.error("[HIREX] Cache error:", e);
    }
  };

  /* ============================================================
     🚀 Submit Handler
     ============================================================ */
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();

    const file = document.getElementById("resume")?.files?.[0];
    const jd = document.getElementById("jd")?.value?.trim();
    const useHumanize = document.getElementById("use_humanize")?.checked;

    if (!isValidFile(file) || !jd) {
      showToast("⚠️ Upload a valid .tex file and paste job description.");
      return;
    }

    disableForm(true);
    showToast("⏳ Optimizing and extracting role/company... (2–3 min)");

    const formData = new FormData();
    formData.append("base_resume_tex", file);
    formData.append("jd_text", jd);
    formData.append("use_humanize", useHumanize ? "true" : "false");

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 180000); // 3-min timeout

    try {
      const res = await fetch(`${API_BASE}/api/optimize`, {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      if (!data?.tex_string) throw new Error("Empty LaTeX output.");

      persistResults(data, useHumanize);

      const company = data.company_name || "Company";
      const role = data.role || "Role";
      showToast(`✅ Optimized for ${company} (${role})! Opening preview...`);
      setTimeout(() => (window.location.href = "/preview.html"), 1500);
    } catch (err) {
      console.error("[HIREX] Error:", err);
      if (err.name === "AbortError") showToast("⚠️ Timeout: optimization took too long.");
      else showToast("❌ " + (err.message || "Unexpected error."));
    } finally {
      disableForm(false);
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
    ].forEach((k) => localStorage.removeItem(k));
    showToast("🧹 Form cleared.");
  });

  /* ============================================================
     🖋️ UX Enhancements
     ============================================================ */
  const jdBox = document.getElementById("jd");
  jdBox?.addEventListener("focus", () =>
    jdBox.scrollIntoView({ behavior: "smooth", block: "center" })
  );

  // Ctrl + Enter quick submit
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key === "Enter") form?.requestSubmit();
  });

  // Drag & Drop file upload
  form?.addEventListener("dragover", (e) => e.preventDefault());
  form?.addEventListener("drop", (e) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (isValidFile(f)) {
      document.getElementById("resume").files = e.dataTransfer.files;
      showToast(`📄 File selected: ${f.name}`);
    } else showToast("⚠️ Only .tex files supported.");
  });

  /* ============================================================
     ✅ Init Log
     ============================================================ */
  console.log(
    "%c[HIREX] main.js initialized (Auto Company/Role + Dual PDF + Humanize ready)",
    "color:#4f8cff;font-weight:bold;"
  );
});
