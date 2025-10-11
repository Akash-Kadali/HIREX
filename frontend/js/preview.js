/* ============================================================
   HIREX • preview.js (Final LaTeX Viewer)
   Displays optimized LaTeX output from backend for copy or download.
   Includes render safety + bright text for guaranteed visibility.
   Author: Sri Akash Kadali
   ============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  const texOutput = document.getElementById("tex-output");
  const toast = document.getElementById("toast");
  const btnDownloadTex = document.getElementById("download-tex");

  /* ============================================================
     🧠 Toast Utility
     ============================================================ */
  function showToast(message, timeout = 2500) {
    if (!toast) return alert(message);
    toast.textContent = message;
    toast.classList.add("show");
    toast.style.display = "block";
    setTimeout(() => {
      toast.classList.remove("show");
      setTimeout(() => (toast.style.display = "none"), 300);
    }, timeout);
  }

  /* ============================================================
     💾 Load Optimized LaTeX from localStorage
     ============================================================ */
  const texString = localStorage.getItem("hirex_tex") || "";
  const texLen = texString.length;

  HIREX?.debugLog?.("PREVIEW INIT", {
    hasTex: !!texString.trim(),
    texLen,
    keys: Object.keys(localStorage),
    origin: window.location.origin,
  });

  if (texOutput) {
    // Style safety to guarantee visibility
    texOutput.style.whiteSpace = "pre-wrap";
    texOutput.style.color = "#ffffff";
    texOutput.style.lineHeight = "1.55";
    texOutput.style.fontFamily = '"Fira Code", monospace';

    if (texString.trim()) {
      texOutput.innerText = texString;
      console.log(
        "%c[HIREX] Loaded optimized LaTeX (first 200 chars):",
        "color:#6a4fff"
      );
      console.log(texString.slice(0, 200) + (texLen > 200 ? "..." : ""));
      showToast("✅ Optimized LaTeX loaded successfully.");
      HIREX?.debugLog?.("LATEX LOADED OK", { texLen });
    } else {
      texOutput.innerText =
        "% ⚠️ No optimized LaTeX found.\n% Please return to the Home page and re-run optimization.";
      showToast("⚠️ No LaTeX data found.");
      HIREX?.debugLog?.("NO LATEX IN STORAGE");
    }
  }

  /* ============================================================
     📋 Copy to Clipboard Button
     ============================================================ */
  const copyButton = document.createElement("button");
  copyButton.textContent = "📋 Copy LaTeX";
  copyButton.className = "cta-primary";
  copyButton.style.marginTop = "1rem";

  copyButton.addEventListener("click", async () => {
    if (!texString.trim()) {
      showToast("⚠️ No LaTeX data to copy!");
      HIREX?.debugLog?.("COPY FAIL — no texString");
      return;
    }
    try {
      await navigator.clipboard.writeText(texString);
      showToast("✅ LaTeX copied to clipboard!");
      HIREX?.debugLog?.("LATEX COPIED", { len: texLen });
    } catch (err) {
      console.error("[HIREX] Clipboard error:", err);
      showToast("⚠️ Unable to copy to clipboard.");
      HIREX?.debugLog?.("COPY ERROR", { err: err.message });
    }
  });

  texOutput?.parentElement?.appendChild(copyButton);

  /* ============================================================
     ⬇️ Download LaTeX File
     ============================================================ */
  btnDownloadTex?.addEventListener("click", () => {
    if (!texString.trim()) {
      showToast("⚠️ No LaTeX data found!");
      HIREX?.debugLog?.("DOWNLOAD FAIL — empty texString");
      return;
    }

    try {
      const blob = new Blob([texString], { type: "text/plain" });
      const link = document.createElement("a");
      const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
      link.href = URL.createObjectURL(blob);
      link.download = `HIREX_Resume_${ts}.tex`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(link.href);
      showToast("⬇️ Downloading LaTeX file...");
      HIREX?.debugLog?.("DOWNLOAD SUCCESS", { bytes: texLen });
    } catch (err) {
      console.error("[HIREX] TEX download error:", err);
      showToast("❌ Unable to download LaTeX file.");
      HIREX?.debugLog?.("DOWNLOAD ERROR", { err: err.message });
    }
  });

  /* ============================================================
     🧹 Cache Expiry Control (12h)
     ============================================================ */
  const now = Date.now();
  const lastUpdate = Number(localStorage.getItem("hirex_timestamp") || 0);
  if (!lastUpdate || now - lastUpdate > 1000 * 60 * 60 * 12) {
    localStorage.setItem("hirex_timestamp", now.toString());
    showToast("🕒 Cache refreshed.");
    HIREX?.debugLog?.("CACHE REFRESHED");
  }

  /* ============================================================
     ⌨️ Keyboard Shortcuts
     ============================================================ */
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key.toLowerCase() === "t") {
      e.preventDefault();
      btnDownloadTex?.click();
      HIREX?.debugLog?.("SHORTCUT CTRL+T → download");
    }
    if (e.ctrlKey && e.key.toLowerCase() === "c") {
      e.preventDefault();
      copyButton?.click();
      HIREX?.debugLog?.("SHORTCUT CTRL+C → copy");
    }
  });

  /* ============================================================
     ✅ Initialization Confirmation
     ============================================================ */
  console.log(
    "%c[HIREX] preview.js (Final LaTeX Viewer) initialized.",
    "color:#4f8cff;font-weight:bold;"
  );
  HIREX?.debugLog?.("PREVIEW READY", {
    texLen,
    hasTex: !!texString.trim(),
    timestamp: localStorage.getItem("hirex_timestamp"),
  });
});
