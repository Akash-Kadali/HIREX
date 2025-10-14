/* ============================================================
   HIREX • preview.js (Final LaTeX + PDF Viewer)
   Displays optimized LaTeX output and both original + humanized PDFs.
   Allows copy, download, and inline PDF preview.
   Author: Sri Akash Kadali
   ============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  const texOutput = document.getElementById("tex-output");
  const toast = document.getElementById("toast");
  const btnDownloadTex = document.getElementById("download-tex");
  const pdfContainer = document.getElementById("pdf-container");

  /* ============================================================
     🧠 Toast Utility
     ============================================================ */
  function showToast(message, timeout = 2500) {
    if (!toast) return alert(message);
    toast.textContent = message;
    toast.style.display = "block";
    toast.style.opacity = "1";
    setTimeout(() => {
      toast.style.opacity = "0";
      setTimeout(() => (toast.style.display = "none"), 300);
    }, timeout);
  }

  /* ============================================================
     💾 Load from localStorage
     ============================================================ */
  const texString = localStorage.getItem("hirex_tex") || "";
  const pdfB64 = localStorage.getItem("hirex_pdf") || "";
  const pdfB64Humanized = localStorage.getItem("hirex_pdf_humanized") || "";
  const company = (localStorage.getItem("hirex_company") || "Company").replace(/\s+/g, "_");
  const role = (localStorage.getItem("hirex_role") || "Role").replace(/\s+/g, "_");
  const texLen = texString.length;

  HIREX?.debugLog?.("PREVIEW INIT", {
    hasTex: !!texString.trim(),
    hasPdf: !!pdfB64,
    hasPdfHumanized: !!pdfB64Humanized,
    texLen,
    company,
    role,
  });

  /* ============================================================
     📄 Render LaTeX
     ============================================================ */
  if (texOutput) {
    texOutput.style.whiteSpace = "pre-wrap";
    texOutput.style.color = "#fff";
    texOutput.style.lineHeight = "1.55";
    texOutput.style.fontFamily = '"Fira Code", monospace';
    texOutput.style.fontSize = "0.9rem";

    if (texString.trim()) {
      texOutput.innerText = texString;
      showToast("✅ Optimized LaTeX loaded successfully.");
    } else {
      texOutput.innerText =
        "% ⚠️ No optimized LaTeX found.\n% Return to Home and re-run optimization.";
      showToast("⚠️ No LaTeX found in cache.");
    }
  }

  /* ============================================================
     📋 Copy LaTeX to Clipboard
     ============================================================ */
  const copyButton = document.createElement("button");
  copyButton.textContent = "📋 Copy LaTeX";
  copyButton.className = "cta-primary";
  copyButton.style.marginTop = "1rem";

  copyButton.addEventListener("click", async () => {
    if (!texString.trim()) return showToast("⚠️ No LaTeX data to copy!");
    try {
      await navigator.clipboard.writeText(texString);
      showToast("✅ LaTeX copied to clipboard!");
    } catch (err) {
      console.error("[HIREX] Clipboard error:", err);
      showToast("⚠️ Unable to copy to clipboard.");
    }
  });

  texOutput?.parentElement?.appendChild(copyButton);

  /* ============================================================
     ⬇️ Download .tex File
     ============================================================ */
  btnDownloadTex?.addEventListener("click", () => {
    if (!texString.trim()) return showToast("⚠️ No LaTeX data found!");
    try {
      const blob = new Blob([texString], { type: "text/plain" });
      const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
      const filename = `HIREX_Resume_${company}_${role}_${ts}.tex`;
      HIREX.downloadFile(filename, blob, "text/plain");
      showToast("⬇️ Downloading .tex file...");
    } catch (err) {
      console.error("[HIREX] TEX download error:", err);
      showToast("❌ Unable to download LaTeX file.");
    }
  });

  /* ============================================================
     🧾 Render PDF Previews (Original + Humanized)
     ============================================================ */
  function renderPDFSection(label, base64, suffix = "") {
    if (!base64) return "";
    const blob = HIREX.base64ToBlob(base64, "application/pdf");
    const url = URL.createObjectURL(blob);
    const filename = `HIREX_Resume_${company}_${role}${suffix}_${HIREX.getTimestamp()}.pdf`;

    return `
      <div class="card">
        <h2>${label}</h2>
        <object data="${url}" type="application/pdf" width="100%" height="750px"></object>
        <div style="margin-top:1rem;display:flex;gap:.8rem;">
          <button class="cta-primary" data-url="${url}" data-filename="${filename}">⬇️ Download PDF</button>
        </div>
      </div>
    `;
  }

  let pdfHtml = "";
  if (pdfB64) pdfHtml += renderPDFSection("Original Optimized Resume", pdfB64, "");
  if (pdfB64Humanized)
    pdfHtml += renderPDFSection("Humanized Resume", pdfB64Humanized, "_");

  if (!pdfHtml)
    pdfHtml = "<p class='muted'>⚠️ No PDF available. Please run optimization first.</p>";

  pdfContainer.innerHTML = pdfHtml;

  pdfContainer.addEventListener("click", (e) => {
    if (e.target.matches("button[data-filename]")) {
      const filename = e.target.dataset.filename;
      const url = e.target.dataset.url;
      fetch(url)
        .then((r) => r.blob())
        .then((blob) => {
          HIREX.downloadFile(filename, blob, "application/pdf");
          showToast(`⬇️ Downloading ${filename.includes("_") ? "Humanized" : "Original"} Resume...`);
          setTimeout(() => URL.revokeObjectURL(url), 1500);
        })
        .catch((err) => {
          console.error("[HIREX] PDF download error:", err);
          showToast("❌ Unable to download PDF.");
        });
    }
  });

  /* ============================================================
     ✅ Initialization Log
     ============================================================ */
  console.log(
    "%c[HIREX] preview.js (Final Viewer with Dual PDF + Humanize Support) initialized.",
    "color:#4f8cff;font-weight:bold;"
  );

  HIREX?.debugLog?.("PREVIEW READY", {
    texLen,
    hasTex: !!texString.trim(),
    hasPdf: !!pdfB64,
    hasPdfHumanized: !!pdfB64Humanized,
    company,
    role,
  });
});
