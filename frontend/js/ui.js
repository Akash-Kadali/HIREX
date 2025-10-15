/* ============================================================
   HIREX • ui.js (v1.2.1 — Unified Global UI Layer)
   ------------------------------------------------------------
   Global UI behavior for all pages:
   • Theme persistence + cross-page/cross-tab sync (system fallback)
   • Smooth scrolling, sticky left navigation on desktop
   • Humanize left/right switch enhancer (robust; keyboard + x-tab sync)
   • Toast + debug utilities (shared globally)
   Author: Sri Akash Kadali
   ============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  const toast = document.getElementById("toast");
  const APP_VERSION = "v1.2.1";
  const THEME_KEY = "hirex-theme";
  const HUMANIZE_KEY = "hirex-use-humanize";
  const currentPage = window.location.pathname.split("/").pop() || "index.html";

  /* ============================================================
     🧠 GLOBAL NAMESPACE SETUP
     ============================================================ */
  window.HIREX = window.HIREX || {};
  Object.assign(window.HIREX, {
    version: APP_VERSION,

    /* ---------- Toast Utility ---------- */
    toast: (msg, duration = 2800) => {
      if (!toast) return console.log("[HIREX]", msg);
      toast.textContent = msg;
      toast.classList.add("visible");
      clearTimeout(toast._timeout);
      toast._timeout = setTimeout(() => toast.classList.remove("visible"), duration);
    },

    /* ---------- Smooth Scroll ---------- */
    scrollTo: (selector, offset = 0) => {
      const el = document.querySelector(selector);
      if (el) {
        const top = el.getBoundingClientRect().top + window.scrollY - offset;
        window.scrollTo({ top, behavior: "smooth" });
      }
    },

    /* ---------- Timestamp Helper ---------- */
    getTimestamp: () => {
      const d = new Date();
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
        d.getDate()
      ).padStart(2, "0")}_${String(d.getHours()).padStart(2, "0")}-${String(
        d.getMinutes()
      ).padStart(2, "0")}`;
    },

    /* ---------- Debug Logger (Frontend → Backend) ---------- */
    debugLog: async (msg, data = {}) => {
      const payload = {
        msg,
        ...data,
        timestamp: new Date().toISOString(),
        page: currentPage,
        origin: window.location.origin,
      };
      console.log("%c🟦 [HIREX DEBUG]", "color:#6a4fff;font-weight:bold;", msg, data);

      try {
        const base =
          ["127.0.0.1", "localhost"].includes(window.location.hostname)
            ? "http://127.0.0.1:8000"
            : window.location.origin;

        await fetch(`${base}/api/debug/log`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      } catch (err) {
        console.warn("[HIREX DEBUG] Log send failed:", err?.message || err);
      }
    },
  });

  /* ============================================================
     🌗 THEME: RESTORE + SYNC (with system fallback)
     ============================================================ */
  const html = document.documentElement;

  const getSystemTheme = () =>
    window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches
      ? "light"
      : "dark";

  const getSavedTheme = () => {
    try { return localStorage.getItem(THEME_KEY); } catch { return null; }
  };

  const setTheme = (theme, { persist = true, silent = false } = {}) => {
    html.setAttribute("data-theme", theme);
    if (persist) {
      try { localStorage.setItem(THEME_KEY, theme); } catch {}
    }
    syncThemeButtons(theme);
    // notify listeners (preview, etc.)
    window.dispatchEvent(new CustomEvent("hirex:theme-change", { detail: { theme } }));
    if (!silent) HIREX.toast(`🌗 Switched to ${theme} mode`);
  };

  // Initial theme: saved → system
  const initialTheme = getSavedTheme() || getSystemTheme();
  setTheme(initialTheme, { persist: !!getSavedTheme(), silent: true });

  // Toggle buttons (support multiple across pages)
  const themeButtons = Array.from(document.querySelectorAll('[data-theme-toggle], #themeToggle'));

  function syncThemeButtons(theme) {
    themeButtons.forEach((btn) => {
      const next = theme === "dark" ? "light" : "dark";
      // keep icon/text minimal; page CSS can replace this with an SVG if needed
      btn.textContent = "🌗";
      btn.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
      btn.dataset.theme = theme;
      btn.title = `Switch to ${next} mode`;
    });
  }

  themeButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const cur = html.getAttribute("data-theme") || "dark";
      const next = cur === "dark" ? "light" : "dark";
      setTheme(next);
    });
  });

  // Cross-tab sync for theme
  window.addEventListener("storage", (e) => {
    if (e.key === THEME_KEY && e.newValue) {
      setTheme(e.newValue, { persist: false, silent: true });
    }
  });

  // Follow system changes only if user hasn't explicitly chosen
  const mql = window.matchMedia("(prefers-color-scheme: light)");
  mql.addEventListener?.("change", () => {
    if (!getSavedTheme()) setTheme(getSystemTheme(), { persist: false, silent: true });
  });

  /* ============================================================
     ✨ INTERSECTION OBSERVER (Scroll Animations)
     ============================================================ */
  const animatedElems = document.querySelectorAll("[data-anim], .anim");
  if (animatedElems.length) {
    const revealObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry, i) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-animated");
            entry.target.style.transition = `opacity .6s ease-out ${i * 0.05}s, transform .6s ease-out ${i * 0.05}s`;
            revealObserver.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.15 }
    );
    animatedElems.forEach((el) => revealObserver.observe(el));
  }

  /* ============================================================
     ⚙️ SMOOTH INTERNAL SCROLL LINKS
     ============================================================ */
  document.querySelectorAll('a[href^="#"]').forEach((link) => {
    link.addEventListener("click", (e) => {
      const target = document.querySelector(link.getAttribute("href"));
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        target.focus?.({ preventScroll: true });
      }
    });
  });

  /* ============================================================
     🧭 ACTIVE NAV LINK HIGHLIGHTING
     ============================================================ */
  document.querySelectorAll("aside a").forEach((a) => {
    const href = a.getAttribute("href");
    if (href && href.endsWith(currentPage)) {
      a.setAttribute("aria-current", "page");
      a.classList.add("active-link");
    } else {
      a.removeAttribute("aria-current");
      a.classList.remove("active-link");
    }
  });

  /* ============================================================
     📌 LEFT NAV: CONSISTENT STICKY ON DESKTOP
     ============================================================ */
  const sidebar = document.querySelector("aside.sidebar, aside#sidebar, aside");
  const applySidebarLayout = () => {
    if (!sidebar) return;
    const isDesktop = window.innerWidth >= 881;
    if (isDesktop) {
      Object.assign(sidebar.style, {
        position: "sticky",
        top: "0px",
        height: "100vh",
        overflowY: "auto",
        willChange: "transform",
      });
      document.body.classList.add("has-sticky-sidebar");
    } else {
      sidebar.style.position = "";
      sidebar.style.top = "";
      sidebar.style.height = "";
      sidebar.style.overflowY = "";
      sidebar.style.willChange = "";
      document.body.classList.remove("has-sticky-sidebar");
    }
  };
  applySidebarLayout();
  window.addEventListener("resize", () => {
    clearTimeout(applySidebarLayout._t);
    applySidebarLayout._t = setTimeout(applySidebarLayout, 120);
  });

  /* ============================================================
     ♿ ACCESSIBILITY: FOCUS OUTLINE MANAGEMENT
     ============================================================ */
  const enableFocusOutline = () => {
    document.body.classList.add("user-is-tabbing");
    window.removeEventListener("keydown", enableFocusOutline);
    window.addEventListener("mousedown", disableFocusOutline);
  };
  const disableFocusOutline = () => {
    document.body.classList.remove("user-is-tabbing");
    window.removeEventListener("mousedown", disableFocusOutline);
    window.addEventListener("keydown", enableFocusOutline);
  };
  window.addEventListener("keydown", enableFocusOutline);

  /* ============================================================
     🌐 CONNECTIVITY STATUS FEEDBACK
     ============================================================ */
  window.addEventListener("online", () => HIREX.toast("✅ Back online"));
  window.addEventListener("offline", () => HIREX.toast("⚠️ Offline mode"));

  /* ============================================================
     🧩 SIDEBAR + MENU TOGGLE SYNC
     ============================================================ */
  const menuToggle = document.getElementById("menuToggle");
  if (menuToggle) {
    menuToggle.addEventListener("click", () => {
      document.body.classList.toggle("nav-open");
      const state = document.body.classList.contains("nav-open") ? "opened" : "closed";
      HIREX.debugLog("Sidebar toggle", { state });
    });
  }

  /* ============================================================
     🔀 HUMANIZE TOGGLE ENHANCER  (transform-based slide CSS compatible)
     - Works with the new pill switch (#humanize-toggle + hidden #use_humanize_state)
     - Gracefully upgrades the legacy checkbox (#use_humanize) into the new switch
     - Keyboard support (Space/Enter/Left/Right), cross-tab sync via localStorage
     ============================================================ */
  (function enhanceHumanize() {
    let switchEl = document.getElementById("humanize-toggle");
    let hidden = document.getElementById("use_humanize_state");
    const legacyCheckbox = document.getElementById("use_humanize");

    // If no switch exists but legacy checkbox does, replace with new UI
    if (!switchEl && legacyCheckbox) {
      const field = legacyCheckbox.closest(".field") || legacyCheckbox.parentElement || document.body;
      const wrap = document.createElement("div");
      wrap.className = "field";
      wrap.innerHTML = `
        <input type="hidden" id="use_humanize_state" value="off" />
        <div id="humanize-toggle" class="switch" role="group" aria-label="Humanize toggle">
          <span class="opt opt-off active">Optimize</span>
          <button type="button" class="knob" aria-pressed="false" aria-label="Toggle Humanize"></button>
          <span class="opt opt-on">Humanize</span>
        </div>
        <small class="muted">Refines tone only. No facts are changed.</small>
      `;
      field.replaceWith(wrap);
      switchEl = wrap.querySelector("#humanize-toggle");
      hidden = wrap.querySelector("#use_humanize_state");
    }

    if (!switchEl) return;

    const knob = switchEl.querySelector(".knob");
    const optOff = switchEl.querySelector(".opt-off");
    const optOn = switchEl.querySelector(".opt-on");

    // ARIA roles for better a11y
    knob?.setAttribute("role", "switch");
    knob?.setAttribute("tabindex", "0");

    const persist = (on) => {
      try { localStorage.setItem(HUMANIZE_KEY, on ? "on" : "off"); } catch {}
    };

    const setState = (on, { silent = false } = {}) => {
      switchEl.classList.toggle("on", on);
      optOff?.classList.toggle("active", !on);
      optOn?.classList.toggle("active", on);
      knob?.setAttribute("aria-pressed", on ? "true" : "false");
      knob?.setAttribute("aria-checked", on ? "true" : "false");
      if (hidden) hidden.value = on ? "on" : "off";
      persist(on);

      // Inform other modules/pages
      const evt = new CustomEvent("hirex:humanize-change", { detail: { on } });
      window.dispatchEvent(evt);

      if (!silent) HIREX.toast(on ? "🧑‍💼 Humanize: ON" : "⚙️ Optimize: ON");
    };

    const saved = (() => {
      try { return localStorage.getItem(HUMANIZE_KEY); } catch { return null; }
    })();
    const startOn = saved ? saved === "on" : false;
    setState(startOn, { silent: true });

    // Pointer interactions
    switchEl.addEventListener("click", () => setState(!switchEl.classList.contains("on")));
    optOff?.addEventListener("click", (e) => { e.stopPropagation(); setState(false); });
    optOn?.addEventListener("click", (e) => { e.stopPropagation(); setState(true); });

    // Keyboard interactions
    knob?.addEventListener("keydown", (e) => {
      const curOn = switchEl.classList.contains("on");
      if (e.key === " " || e.key === "Enter") {
        e.preventDefault();
        setState(!curOn);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        setState(true);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        setState(false);
      }
    });

    // Cross-tab sync for humanize state
    window.addEventListener("storage", (e) => {
      if (e.key === HUMANIZE_KEY && e.newValue) {
        const on = e.newValue === "on";
        setState(on, { silent: true });
      }
    });
  })();

  /* ============================================================
     📄 FRONTEND: REMOVE/NEUTER .tex UPLOAD (UI SIDE)
     - Hide legacy file input if present and let backend use base_resume.tex
     ============================================================ */
  (function neutralizeTexUpload() {
    const fileInput = document.getElementById("resume");
    const field = fileInput?.closest(".field") || fileInput?.parentElement;
    if (fileInput) {
      fileInput.disabled = true;
      fileInput.setAttribute("aria-hidden", "true");
      fileInput.style.display = "none";
      if (field) field.style.display = "none";
      HIREX.debugLog("Base .tex upload hidden; default base will be used.");
    }
    const hint = document.getElementById("base-tex-hint");
    if (hint) hint.textContent = "Using default base: data/samples/base_resume.tex";
  })();

  /* ============================================================
     ⌨️ GLOBAL SHORTCUTS
     ============================================================ */
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key.toLowerCase() === "h") {
      e.preventDefault();
      HIREX.toast("💡 HIREX shortcut active (Ctrl+H)");
      HIREX.debugLog("GLOBAL SHORTCUT", { combo: "Ctrl+H" });
    }
  });

  /* ============================================================
     🧩 CONSOLE BRANDING (Developer Info)
     ============================================================ */
  console.log(
    `%c⚙️ HIREX UI ${APP_VERSION} loaded`,
    "background:#6ea8fe;color:#fff;padding:4px 8px;border-radius:4px;font-weight:bold;"
  );
  console.log(
    "%cMade with ❤️ by Sri Akash Kadali — University of Maryland",
    "color:#a3aed0;font-style:italic;"
  );

  HIREX.debugLog("UI LOADED", {
    version: APP_VERSION,
    page: currentPage,
    origin: window.location.origin,
  });
});
