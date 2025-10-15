/* ============================================================
   HIREX • util.js (v1.2.0 — Unified Utility Layer)
   ------------------------------------------------------------
   Shared helper utilities across HIREX front-end modules.
   • Safe JSON/text fetch with retry + timeout (+ auto JSON body)
   • Base64/Blob conversions, universal download, clipboard, debounce
   • Theme + Humanize state helpers (persist + events)
   • Storage wrappers, API base resolver, filename sanitizer
   • FormData builder for single-base flow (no .tex upload)
   Integrated with HIREX logging + toast systems.
   Author: Sri Akash Kadali
   ============================================================ */

/* ============================================================
   🔧 Constants
   ============================================================ */
const UTIL_VERSION = "v1.2.0";
const DEFAULT_BASE_TEX_PATH = "data/samples/base_resume.tex"; // UI hint only; backend reads this
const LS_KEYS = {
  THEME: "hirex-theme",
  HUMANIZE: "hirex-use-humanize",
};

/* ============================================================
   🧰 Storage Helpers (safe localStorage)
   ============================================================ */
function lsGet(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function lsSet(key, val) {
  try { localStorage.setItem(key, val); return true; } catch { return false; }
}

/* ============================================================
   🌐 API Base Resolver
   ============================================================ */
function getApiBase() {
  return ["127.0.0.1", "localhost"].includes(window.location.hostname)
    ? "http://127.0.0.1:8000"
    : window.location.origin;
}

/* ============================================================
   🌗 Theme Helpers (persist + utility)
   (UI wiring happens in ui.js; these give other modules access)
   ============================================================ */
function getSystemTheme() {
  try {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches
      ? "light"
      : "dark";
  } catch { return "dark"; }
}
function getTheme() {
  return lsGet(LS_KEYS.THEME) || getSystemTheme();
}
function setTheme(theme) {
  const ok = lsSet(LS_KEYS.THEME, theme);
  try {
    document.documentElement.setAttribute("data-theme", theme);
  } catch {}
  // Let listeners know (matches ui.js internal eventing style)
  window.dispatchEvent(new CustomEvent("hirex:theme-change", { detail: { theme } }));
  return ok;
}
function onThemeChange(handler) {
  const fn = (e) => handler?.(e.detail?.theme ?? getTheme());
  window.addEventListener("hirex:theme-change", fn);
  return () => window.removeEventListener("hirex:theme-change", fn);
}

/* ============================================================
   🧑‍💼 Humanize State Helpers (persist + event)
   (UI switch is enhanced in ui.js; these expose state to main.js)
   ============================================================ */
function getHumanizeState() {
  return (lsGet(LS_KEYS.HUMANIZE) || "off") === "on";
}
function setHumanizeState(on) {
  lsSet(LS_KEYS.HUMANIZE, on ? "on" : "off");
  window.dispatchEvent(new CustomEvent("hirex:humanize-change", { detail: { on } }));
  return on;
}
function onHumanizeChange(handler) {
  const fn = (e) => handler?.(!!e.detail?.on);
  window.addEventListener("hirex:humanize-change", fn);
  return () => window.removeEventListener("hirex:humanize-change", fn);
}

/* ============================================================
   🌍 Fetch Helpers (retry + timeout; JSON/Text variants)
   ============================================================ */
async function _doFetch(url, options = {}, retries = 1) {
  const controller = new AbortController();
  const timeoutMs = options.timeout ?? 20000;
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  // auto-JSON body if plain object supplied
  const isJsonBody =
    options.body &&
    typeof options.body === "object" &&
    !(options.body instanceof FormData) &&
    !(options.body instanceof Blob) &&
    !(options.body instanceof ArrayBuffer);

  const headers = {
    Accept: "application/json",
    ...(isJsonBody ? { "Content-Type": "application/json" } : {}),
    ...(options.headers || {}),
  };

  try {
    const response = await fetch(url, {
      ...options,
      headers,
      body: isJsonBody ? JSON.stringify(options.body) : options.body,
      signal: controller.signal,
    });

    clearTimeout(timeout);

    if (!response.ok) {
      const errText = await response.text().catch(() => "");
      const msg = `HTTP ${response.status}: ${errText || "Unknown error"}`;
      HIREX?.debugLog?.("fetch ERROR", { url, status: response.status, msg });
      throw new Error(msg);
    }

    return response;
  } catch (err) {
    clearTimeout(timeout);
    if (retries > 0) {
      const attempt = retries;
      HIREX?.toast?.(`⚠️ Network hiccup — retrying (${attempt})...`);
      await new Promise((r) => setTimeout(r, 800));
      return _doFetch(url, options, retries - 1);
    }
    HIREX?.toast?.(`❌ Network error: ${err?.message || err}`);
    HIREX?.debugLog?.("fetch FAIL", { url, err: err?.message || String(err) });
    throw err;
  }
}

/* JSON response */
async function fetchJSON(url, options = {}, retries = 1) {
  const res = await _doFetch(url, options, retries);
  const json = await res.json();
  HIREX?.debugLog?.("fetchJSON OK", { url, keys: Object.keys(json || {}) });
  return json;
}

/* Text response */
async function fetchText(url, options = {}, retries = 1) {
  const res = await _doFetch(url, options, retries);
  const text = await res.text();
  HIREX?.debugLog?.("fetchText OK", { url, len: text.length });
  return text;
}

/* POST JSON shorthand */
function postJSON(url, data, options = {}, retries = 1) {
  return fetchJSON(
    url,
    { method: "POST", body: data, ...(options || {}) },
    retries
  );
}

/* ============================================================
   🧪 Base64/Blob Conversions
   ============================================================ */
function base64ToBlob(base64, mime = "application/octet-stream") {
  try {
    const binary = atob(base64);
    const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
    const blob = new Blob([bytes], { type: mime });
    HIREX?.debugLog?.("base64ToBlob OK", { size: blob.size, mime });
    return blob;
  } catch (err) {
    console.error("[HIREX] base64ToBlob error:", err);
    HIREX?.toast?.("⚠️ Failed to decode Base64.");
    HIREX?.debugLog?.("base64ToBlob ERROR", { err: err.message });
    return null;
  }
}

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

/* ============================================================
   ⬇️ Download & Clipboard
   ============================================================ */
function downloadFile(filename, data, mime = "application/octet-stream") {
  try {
    let blob;
    if (typeof data === "string" && !data.startsWith("data:")) {
      blob = new Blob([data], { type: mime });
    } else if (typeof data === "string" && data.startsWith("data:")) {
      blob = base64ToBlob(data.split(",")[1], mime);
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
    a.remove();
    URL.revokeObjectURL(url);

    HIREX?.toast?.(`⬇️ Downloading ${filename}...`);
    HIREX?.debugLog?.("downloadFile OK", { name: filename, size: blob.size });
  } catch (err) {
    console.error("[HIREX] downloadFile error:", err);
    HIREX?.toast?.("❌ Download failed.");
    HIREX?.debugLog?.("downloadFile ERROR", { name: filename, err: err.message });
  }
}
function downloadTextFile(filename, text) {
  downloadFile(filename, text, "text/plain");
}

async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    HIREX?.toast?.("📋 Copied to clipboard!");
    HIREX?.debugLog?.("copyToClipboard OK", { len: text.length });
  } catch (err) {
    console.error("[HIREX] copyToClipboard error:", err);
    HIREX?.toast?.("⚠️ Clipboard permission denied.");
    HIREX?.debugLog?.("copyToClipboard ERROR", { err: err.message });
  }
}

/* ============================================================
   🕒 Misc Helpers
   ============================================================ */
function getTimestamp() {
  const ts = new Date().toISOString().replace(/[:.]/g, "-");
  HIREX?.debugLog?.("getTimestamp", { ts });
  return ts;
}

function debounce(fn, delay = 300) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

function sleep(ms = 500) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function formatBytes(bytes, decimals = 2) {
  if (!+bytes) return "0 Bytes";
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const value = parseFloat((bytes / Math.pow(k, i)).toFixed(dm));
  return `${value} ${sizes[i]}`;
}

/* Safe filename for downloads */
function sanitizeFilename(name, fallback = "file") {
  try {
    const clean = String(name)
      .replace(/[\\/:*?"<>|]+/g, "_")
      .replace(/\s+/g, " ")
      .trim();
    return clean || fallback;
  } catch {
    return fallback;
  }
}

/* ============================================================
   📝 FormData builder (single-base flow: no .tex upload)
   ============================================================ */
function buildOptimizeFormData(jdText, useHumanize) {
  const fd = new FormData();
  fd.append("jd_text", jdText || "");
  fd.append("use_humanize", useHumanize ? "true" : "false");
  // No base_resume_tex appended — backend will load DEFAULT_BASE_TEX_PATH
  return fd;
}

/* ============================================================
   🔗 Export to Global Namespace
   ============================================================ */
window.HIREX = window.HIREX || {};
Object.assign(window.HIREX, {
  // constants
  UTIL_VERSION,
  DEFAULT_BASE_TEX_PATH,
  LS_KEYS,

  // storage + base
  lsGet, lsSet,
  getApiBase,

  // theme
  getSystemTheme, getTheme, setTheme, onThemeChange,

  // humanize
  getHumanizeState, setHumanizeState, onHumanizeChange,

  // fetch
  fetchJSON, fetchText, postJSON,

  // file/base64
  base64ToBlob, blobToBase64,
  downloadFile, downloadTextFile, copyToClipboard,

  // misc
  getTimestamp, debounce, sleep, formatBytes, sanitizeFilename,

  // form
  buildOptimizeFormData,
});

console.log(
  `%c[HIREX] util.js ${UTIL_VERSION} loaded`,
  "color:#6ea8fe;font-weight:bold;"
);
