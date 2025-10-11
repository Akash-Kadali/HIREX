/* ============================================================
   HIREX • util.js (Debug-Ready)
   Shared helper utilities used across main.js, preview.js, etc.
   Optimized for consistency, safety, and modern browser support.
   Author: Sri Akash Kadali
   ============================================================ */

/* ---------- Safe JSON Fetch Helper ---------- */
async function fetchJSON(url, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.timeout || 20000); // 20s default timeout

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(options.headers || {}),
      },
    });

    clearTimeout(timeout);

    if (!response.ok) {
      const errText = await response.text();
      const msg = `HTTP ${response.status}: ${errText || "Unknown error"}`;
      console.error("[HIREX] fetchJSON failed:", msg);
      HIREX?.debugLog?.("fetchJSON ERROR", { url, status: response.status, msg });
      throw new Error(msg);
    }

    const json = await response.json();
    HIREX?.debugLog?.("fetchJSON SUCCESS", { url, keys: Object.keys(json) });
    return json;
  } catch (err) {
    clearTimeout(timeout);
    console.error("[HIREX] fetchJSON error:", err);
    HIREX?.toast?.(`⚠️ Network error: ${err.message}`);
    HIREX?.debugLog?.("fetchJSON FAIL", { url, err: err.message });
    throw err;
  }
}

/* ---------- Convert Base64 → Blob ---------- */
function base64ToBlob(base64, mime = "application/octet-stream") {
  try {
    const binary = atob(base64);
    const len = binary.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) bytes[i] = binary.charCodeAt(i);
    const blob = new Blob([bytes], { type: mime });
    HIREX?.debugLog?.("base64ToBlob OK", { size: blob.size, mime });
    return blob;
  } catch (err) {
    console.error("[HIREX] base64ToBlob error:", err);
    HIREX?.toast?.("⚠️ Failed to convert file from Base64.");
    HIREX?.debugLog?.("base64ToBlob ERROR", { err: err.message });
    return null;
  }
}

/* ---------- Convert Blob → Base64 ---------- */
function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      try {
        const result = reader.result?.split(",")[1] || "";
        HIREX?.debugLog?.("blobToBase64 OK", { size: result.length });
        resolve(result);
      } catch (err) {
        console.error("[HIREX] blobToBase64 error:", err);
        HIREX?.debugLog?.("blobToBase64 ERROR", { err: err.message });
        reject(err);
      }
    };
    reader.onerror = (e) => {
      HIREX?.debugLog?.("blobToBase64 READER ERROR", { err: e });
      reject(e);
    };
    reader.readAsDataURL(blob);
  });
}

/* ---------- File Download (String / Blob / Base64) ---------- */
function downloadFile(filename, data, mime = "application/octet-stream") {
  try {
    let blob;

    if (typeof data === "string" && !data.startsWith("data:")) {
      blob = new Blob([data], { type: mime });
    } else if (typeof data === "string" && data.startsWith("data:")) {
      const base64 = data.split(",")[1];
      blob = base64ToBlob(base64, mime);
    } else if (data instanceof Blob) {
      blob = data;
    } else {
      throw new Error("Unsupported data type for download.");
    }

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    HIREX?.toast?.(`⬇️ Downloading ${filename}...`);
    HIREX?.debugLog?.("downloadFile OK", { name: filename, size: blob.size });
  } catch (err) {
    console.error("[HIREX] downloadFile error:", err);
    HIREX?.toast?.("❌ Unable to download file.");
    HIREX?.debugLog?.("downloadFile ERROR", { name: filename, err: err.message });
  }
}

/* ---------- Download Text File ---------- */
function downloadTextFile(filename, text) {
  downloadFile(filename, text, "text/plain");
}

/* ---------- Clipboard Helper ---------- */
async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    HIREX?.toast?.("📋 Copied to clipboard!");
    HIREX?.debugLog?.("copyToClipboard OK", { len: text.length });
  } catch (err) {
    console.error("[HIREX] copyToClipboard error:", err);
    HIREX?.toast?.("⚠️ Unable to copy text.");
    HIREX?.debugLog?.("copyToClipboard ERROR", { err: err.message });
  }
}

/* ---------- Timestamp Helper ---------- */
function getTimestamp() {
  const now = new Date();
  const ts = now.toISOString().replace(/[:.]/g, "-");
  HIREX?.debugLog?.("getTimestamp", { ts });
  return ts;
}

/* ---------- Debounce Helper ---------- */
function debounce(fn, delay = 300) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

/* ---------- Export to Global Namespace ---------- */
window.HIREX = window.HIREX || {};
Object.assign(window.HIREX, {
  fetchJSON,
  base64ToBlob,
  blobToBase64,
  downloadFile,
  downloadTextFile,
  copyToClipboard,
  getTimestamp,
  debounce,
});
