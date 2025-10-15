/* ============================================================
   HIREX • preview.js (v1.2.0 — Adaptive PDF + LaTeX Viewer)
   ------------------------------------------------------------
   Features:
   • Displays Optimized + Humanized PDFs dynamically
   • Updates JD Fit Score gauge + tier + rounds
   • Copy / download LaTeX with safe filenames
   • Theme-aware styling + cache version check
   • Uses global HIREX utilities (ui.js + util.js)
   Author: Sri Akash Kadali
   ============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  const PREVIEW_VERSION = "v1.2.0";

  // ----------------- Elements -----------------
  const texOutput = document.getElementById("tex-output");
  const pdfContainer = document.getElementById("pdf-container");
  const btnDownloadTex = document.getElementById("download-tex");
  const copyBtn = document.getElementById("copy-tex");

  const fitCircle = document.getElementById("fitCircle");
  const fitTierEl = document.getElementById("fit-tier");
  const fitRoundsEl = document.getElementById("fit-rounds");

  // ----------------- Helpers -----------------
  const toast = (msg, t = 2800) => (window.HIREX?.toast ? HIREX.toast(msg, t) : alert(msg));
  const debug = (msg, data) => window.HIREX?.debugLog?.(msg, data);

  const getTS = () => (window.HIREX?.getTimestamp ? HIREX.getTimestamp() : new Date().toISOString().replace(/[:.]/g, "-"));
  const sanitize = (name) => (window.HIREX?.sanitizeFilename ? HIREX.sanitizeFilename(name) : String(name || "file").replace(/[\\/:*?"<>|]+/g, "_"));
  const b64ToBlob = (b64, mime) => (window.HIREX?.base64ToBlob ? HIREX.base64ToBlob(b64, mime) :
    new Blob([Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))], { type: mime || "application/octet-stream" }));
  const downloadText = (name, text) => (window.HIREX?.downloadTextFile ? HIREX.downloadTextFile(name, text) : downloadFallback(name, new Blob([text], { type: "text/plain" })));
  const downloadBlob = (name, blob) => (window.HIREX?.downloadFile ? HIREX.downloadFile(name, blob) : downloadFallback(name, blob));
  function downloadFallback(filename, blob) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 500);
  }

  // ----------------- Load cached data -----------------
  const texString = localStorage.getItem("hirex_tex") || "";
  const pdfB64 = localStorage.getItem("hirex_pdf") || "";
  const pdfB64Humanized = localStorage.getItem("hirex_pdf_humanized") || "";
  const companyRaw = localStorage.getItem("hirex_company") || "Company";
  const roleRaw = localStorage.getItem("hirex_role") || "Role";
  const appCacheVersion = localStorage.getItem("hirex_version") || "v1.0.0";

  // filename parts
  const company = sanitize(companyRaw).replace(/\s+/g, "_");
  const role = sanitize(roleRaw).replace(/\s+/g, "_");

  // Cache version check
  if (appCacheVersion !== PREVIEW_VERSION) {
    console.warn("[HIREX] Cache version mismatch:", appCacheVersion, "≠", PREVIEW_VERSION);
    toast("⚠️ Old cache detected. Consider re-optimizing.");
  }

  // ----------------- Rating / Fit Gauge -----------------
  let ratingScore = Number.parseInt(localStorage.getItem("hirex_rating_score") || "", 10);
  let ratingRounds = 0;
  try {
    const hist = JSON.parse(localStorage.getItem("hirex_rating_history") || "[]");
    ratingRounds = Array.isArray(hist) ? hist.length : 0;
    if ((!ratingScore || Number.isNaN(ratingScore)) && hist.length && typeof hist.at(-1)?.coverage === "number") {
      ratingScore = Math.round(hist.at(-1).coverage * 100);
    }
  } catch { /* ignore */ }

  if (fitCircle) {
    const tier =
      (ratingScore ?? 0) >= 90 ? "Excellent" :
      (ratingScore ?? 0) >= 75 ? "Strong" :
      (ratingScore ?? 0) >= 60 ? "Moderate" :
      (ratingScore ?? 0) > 0 ? "Low" : "Awaiting Analysis…";

    fitCircle.setAttribute("data-score", Number.isFinite(ratingScore) ? ratingScore : "--");
    if (fitTierEl) fitTierEl.textContent = tier;
    if (fitRoundsEl) fitRoundsEl.textContent = ratingRounds || 1;
  }

  // ----------------- Render LaTeX -----------------
  if (texOutput) {
    Object.assign(texOutput.style, {
      whiteSpace: "pre-wrap",
      color: "var(--text-100)",
      lineHeight: "1.6",
      fontFamily: '"Fira Code", ui-monospace, SFMono-Regular, Menlo, monospace',
      fontSize: "0.9rem",
      padding: "1rem",
      borderRadius: "8px",
      background: "rgba(255,255,255,0.03)",
      border: "1px solid rgba(255,255,255,0.08)",
      boxShadow: "0 0 20px rgba(110,168,254,0.1)",
    });

    if (texString.trim()) {
      texOutput.textContent = texString;
      toast("✅ Optimized LaTeX loaded.");
    } else {
      texOutput.textContent = "% ⚠️ No optimized LaTeX found.\n% Re-run optimization from Home page.";
      toast("⚠️ No LaTeX found in cache.");
    }
  }

  // Copy LaTeX
  copyBtn?.addEventListener("click", async () => {
    if (!texString.trim()) return toast("⚠️ No LaTeX to copy!");
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(texString);
        toast("✅ LaTeX copied to clipboard!");
      } else {
        // fallback: create hidden textarea
        const ta = document.createElement("textarea");
        ta.value = texString; document.body.appendChild(ta);
        ta.select(); document.execCommand("copy"); ta.remove();
        toast("✅ LaTeX copied to clipboard!");
      }
    } catch (e) {
      console.error("Clipboard error:", e);
      toast("❌ Clipboard permission denied.");
    }
  });

  // Download .tex
  btnDownloadTex?.addEventListener("click", () => {
    if (!texString.trim()) return toast("⚠️ No LaTeX data found!");
    const filename = sanitize(`HIREX_Resume_${company}_${role}_${getTS()}.tex`);
    downloadText(filename, texString);
    toast("⬇️ Downloading .tex file…");
  });

  // ----------------- Render PDFs -----------------
  const objectUrls = [];

  function objectURLFromBase64PDF(b64) {
    const blob = b64ToBlob(b64, "application/pdf");
    const url = URL.createObjectURL(blob);
    objectUrls.push(url);
    return url;
  }

  function createPDFCard(title, b64, suffix = "") {
    if (!b64) return "";
    const url = objectURLFromBase64PDF(b64);
    const filename = sanitize(`HIREX_Resume_${company}_${role}${suffix}_${getTS()}.pdf`);
    return `
      <div class="pdf-card anim fade">
        <h3>${title}</h3>
        <div class="pdf-frame">
          <iframe src="${url}#view=FitH" loading="lazy" title="${title}"></iframe>
        </div>
        <div class="pdf-download">
          <button data-url="${url}" data-filename="${filename}" class="cta-primary">
            ⬇️ Download PDF
          </button>
        </div>
      </div>
    `;
  }

  let pdfHTML = "";
  if (pdfB64) pdfHTML += createPDFCard("Original Optimized Resume", pdfB64);
  if (pdfB64Humanized) pdfHTML += createPDFCard("Humanized Resume (Tone-Refined)", pdfB64Humanized, "_Humanized");
  if (!pdfHTML) {
    pdfHTML = `<p class="muted" style="text-align:center;margin-top:2rem;">
      ⚠️ No PDF found. Please optimize a resume first.</p>`;
  }
  if (pdfContainer) pdfContainer.innerHTML = pdfHTML;

  // PDF Download click handler
  pdfContainer?.addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-filename]");
    if (!btn) return;
    const { filename, url } = btn.dataset;
    try {
      const blob = await fetch(url).then((r) => r.blob());
      downloadBlob(filename, blob);
      toast(`⬇️ Downloading ${filename.includes("Humanized") ? "Humanized" : "Optimized"} PDF…`);
    } catch (err) {
      console.error("[HIREX] PDF download error:", err);
      toast("❌ Failed to download PDF.");
    }
  });

  // ----------------- Humanize state awareness -----------------
  // If the user flips Humanize ON/OFF on another tab / page, hint which card to prefer
  const highlightActiveMode = (on) => {
    const cards = pdfContainer?.querySelectorAll(".pdf-card") || [];
    cards.forEach((c) => c.classList.remove("preferred"));
    // prefer humanized card when on==true, else the optimized card
    const selector = on ? "h3:contains('Humanized')" : "h3:contains('Original Optimized')";
    // :contains is not standard -> manual scan:
    cards.forEach((c) => {
      const h3 = c.querySelector("h3");
      const isHuman = /Humanized/i.test(h3?.textContent || "");
      const prefer = on ? isHuman : !isHuman;
      if (prefer) c.classList.add("preferred");
    });
  };

  const initialHumanizeOn = window.HIREX?.getHumanizeState ? HIREX.getHumanizeState() : (localStorage.getItem("hirex-use-humanize") === "on");
  highlightActiveMode(initialHumanizeOn);
  window.HIREX?.onHumanizeChange?.(highlightActiveMode);
  window.addEventListener("hirex:humanize-change", (e) => highlightActiveMode(!!e.detail?.on));

  // ----------------- Theme reactivity (optional polish) -----------------
  window.addEventListener("hirex:theme-change", () => {
    // if you need to force a repaint of iframes or adjust borders, do it here
    // (current CSS variables should already handle colors)
  });

  // ----------------- Cleanup -----------------
  window.addEventListener("beforeunload", () => {
    objectUrls.forEach((u) => URL.revokeObjectURL(u));
  });

  // ----------------- Init Log -----------------
  console.log(
    `%c[HIREX] preview.js initialized — ${PREVIEW_VERSION} (Adaptive Viewer)`,
    "color:#6ea8fe;font-weight:bold;"
  );

  debug("PREVIEW PAGE LOADED", {
    version: PREVIEW_VERSION,
    company: companyRaw,
    role: roleRaw,
    ratingScore,
    ratingRounds,
    hasTex: !!texString.trim(),
    hasPdf: !!pdfB64,
    hasPdfHumanized: !!pdfB64Humanized,
  });
});
