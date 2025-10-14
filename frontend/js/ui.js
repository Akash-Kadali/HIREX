/* ============================================================
   HIREX • ui.js (Debug-enabled Global UI Layer)
   Global UI behavior: animations, toasts, navigation, and helpers.
   Loaded on every page (after util.js).
   Author: Sri Akash Kadali
   ============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  const toast = document.getElementById("toast");
  const APP_VERSION = "v1.0.0";

  /* ============================================================
     🧠 GLOBAL NAMESPACE SETUP
     ============================================================ */
  window.HIREX = window.HIREX || {};
  Object.assign(window.HIREX, {
    version: APP_VERSION,

    /* ---------- Toast Utility ---------- */
    toast: (msg, duration = 2500) => {
      if (!toast) {
        console.log("[HIREX]", msg);
        return;
      }
      toast.textContent = msg;
      toast.style.display = "block";
      toast.style.opacity = "1";
      setTimeout(() => {
        toast.style.opacity = "0";
        setTimeout(() => (toast.style.display = "none"), 350);
      }, duration);
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
      try {
        const payload = {
          msg,
          ...data,
          timestamp: new Date().toISOString(),
          page: window.location.pathname.split("/").pop() || "index.html",
          origin: window.location.origin,
        };

        console.log("%c🟦 [HIREX DEBUG]", "color:#6a4fff;font-weight:bold;", msg, data);

        const base =
          window.location.hostname === "127.0.0.1" ||
          window.location.hostname === "localhost"
            ? "http://127.0.0.1:8000"
            : window.location.origin;

        await fetch(`${base}/api/debug/log`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      } catch (err) {
        console.warn("[HIREX DEBUG] Log send failed:", err.message);
      }
    },
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
            entry.target.style.transition = `opacity 0.6s ease-out ${i * 0.08}s, transform 0.6s ease-out ${i * 0.08}s`;
            revealObserver.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.2 }
    );
    animatedElems.forEach((el) => revealObserver.observe(el));
  }

  /* ============================================================
     ⚙️ SMOOTH INTERNAL SCROLL LINKS
     ============================================================ */
  document.querySelectorAll('a[href^="#"]').forEach((link) => {
    link.addEventListener("click", (e) => {
      const targetId = link.getAttribute("href");
      const targetEl = document.querySelector(targetId);
      if (targetEl) {
        e.preventDefault();
        targetEl.scrollIntoView({ behavior: "smooth", block: "start" });
        targetEl.focus({ preventScroll: true });
      }
    });
  });

  /* ============================================================
     🧭 ACTIVE LINK HIGHLIGHTING
     ============================================================ */
  const currentPage = window.location.pathname.split("/").pop() || "index.html";
  document.querySelectorAll("nav a, aside a").forEach((a) => {
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
     ♿ ACCESSIBILITY FOCUS HANDLER
     ============================================================ */
  function enableFocusOutline() {
    document.body.classList.add("user-is-tabbing");
    window.removeEventListener("keydown", enableFocusOutline);
    window.addEventListener("mousedown", disableFocusOutline);
  }

  function disableFocusOutline() {
    document.body.classList.remove("user-is-tabbing");
    window.removeEventListener("mousedown", disableFocusOutline);
    window.addEventListener("keydown", enableFocusOutline);
  }

  window.addEventListener("keydown", enableFocusOutline);

  /* ============================================================
     🌐 CONNECTIVITY STATUS TOASTS
     ============================================================ */
  window.addEventListener("online", () => HIREX.toast("✅ You're back online."));
  window.addEventListener("offline", () => HIREX.toast("⚠️ You're offline."));

  /* ============================================================
     ⌨️ GLOBAL KEYBOARD SHORTCUTS
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
    "background:#4f8cff;color:#fff;padding:4px 8px;border-radius:4px;font-weight:bold;"
  );
  console.log(
    "%cMade with ❤️ by Sri Akash Kadali — University of Maryland",
    "color:#9ca3af;font-style:italic;"
  );

  HIREX.debugLog("UI LOADED", {
    version: APP_VERSION,
    page: currentPage,
    origin: window.location.origin,
  });
});
