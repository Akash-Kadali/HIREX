"""
HIREX • main.py (Windows App Version)
Launches FastAPI backend + your HTML/CSS/JS UI inside a native Windows window.
Includes a Close button (top-right ✖️) that exits cleanly.
Author: Sri Akash Kadali
"""

# ============================================================
# 🧭 Path Setup
# ============================================================
import os
import sys
import threading
import time
import signal
from typing import Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)

if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)


# ============================================================
# 🪵 Logging Helper (fallback if project logger missing)
# ============================================================
def _fallback_log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")

try:
    from backend.core.utils import log_event  # type: ignore
except Exception:
    log_event = _fallback_log


# ============================================================
# 🌐 FastAPI Backend
# ============================================================
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse

# Optional project routers
try:
    from api import optimize  # your optimization endpoints (router)
except Exception as e:  # hardened import with explanation
    optimize = None
    log_event(f"⚠️  Could not import api.optimize: {e}")

try:
    from api import debug as debug_api  # optional debug routes
except Exception as e:
    debug_api = None
    log_event(f"⚠️  Could not import api.debug: {e}")

APP_VERSION = "1.2.1"

app = FastAPI(
    title="HIREX API",
    description="HIgh REsume eXpert — Job-Aware Resume Optimizer (LaTeX-based)",
    version=APP_VERSION,
)


# ------------------------------------------------------------
# Middleware — Request/Response Tracer
# ------------------------------------------------------------
@app.middleware("http")
async def trace_requests(request: Request, call_next):
    """Trace requests for debug output in console (non-intrusive)."""
    try:
        log_event(f"➡️  {request.method} {request.url.path}")
        if request.query_params:
            log_event(f"   ├─ query={dict(request.query_params)}")
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                body = await request.body()
                log_event(f"   ├─ body-bytes={len(body)}")
            except Exception:
                pass

        response = await call_next(request)
        log_event(f"⬅️  {request.method} {request.url.path} → {response.status_code}")
        return response
    except Exception as e:
        log_event(f"💥 Middleware error on {request.method} {request.url.path}: {e}")
        return JSONResponse({"error": "internal_middleware_error", "detail": str(e)}, status_code=500)


# ------------------------------------------------------------
# Allow frontend access
# ------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # dev-friendly; restrict for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.normpath(os.path.join(ROOT_DIR, "frontend"))
STATIC_PATH = os.path.join(FRONTEND_DIR, "static")

# Static mount (serve /static/**)
static_dir = STATIC_PATH if os.path.exists(STATIC_PATH) else FRONTEND_DIR
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
else:
    log_event(f"⚠️  Static path not found: {static_dir}")


# ============================================================
# 📄 Static Frontend Routing (index + top-level pages)
# ============================================================
def _frontend_path(name: str) -> Optional[str]:
    path = os.path.join(FRONTEND_DIR, name)
    return path if os.path.exists(path) else None

@app.get("/", include_in_schema=False)
def serve_index():
    index_path = _frontend_path("index.html")
    if not index_path:
        return JSONResponse({"error": "frontend_not_found", "dir": FRONTEND_DIR}, status_code=404)
    return FileResponse(index_path)

@app.get("/{page_name}", include_in_schema=False)
def serve_html(page_name: str):
    """
    Serve top-level pages: /about, /help, /preview, etc.
    Falls back to index.html for unknown names to keep UX smooth.
    """
    normalized = page_name if page_name.endswith(".html") else f"{page_name}.html"
    page_path = _frontend_path(normalized)
    if page_path:
        return FileResponse(page_path)
    # Redirect unknown top-level paths to home (SPA-like behavior)
    index_path = _frontend_path("index.html")
    return FileResponse(index_path) if index_path else RedirectResponse("/")


# ============================================================
# 🧩 API Routes
# ============================================================
if optimize and getattr(optimize, "router", None):
    app.include_router(optimize.router, prefix="/api", tags=["Optimization"])
else:
    log_event("⚠️  Skipping /api (optimize) — router not available")

if debug_api and getattr(debug_api, "router", None):
    app.include_router(debug_api.router, prefix="/api/debug", tags=["Debug"])
else:
    log_event("ℹ️  Debug router not present — continuing without /api/debug")

@app.get("/health", tags=["System"])
def health():
    """Health check endpoint."""
    return {"status": "ok", "message": "Backend online", "version": APP_VERSION}


# ============================================================
# 🪟 Windows App Launcher (PyWebview)
# ============================================================
def start_fastapi():
    """Run FastAPI server in a background thread."""
    import uvicorn
    # quiet uvicorn logs for a cleaner console; middleware already traces
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="error",
        timeout_keep_alive=25,
        proxy_headers=False,
        server_header=False,
    )


def _wait_for_backend(url: str, timeout_s: float = 15.0) -> bool:
    """Poll /health until backend responds or timeout elapses."""
    import urllib.request
    import json

    start = time.time()
    health_url = url.rstrip("/") + "/health"
    while time.time() - start < timeout_s:
        try:
            with urllib.request.urlopen(health_url, timeout=1.5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data.get("status") == "ok":
                        return True
        except Exception:
            time.sleep(0.35)
    return False


def start_window():
    """Launch PyWebview GUI window with a custom floating ✖ Close button."""
    import webview

    base_url = "http://127.0.0.1:8000"

    # Wait for backend to boot (poll health instead of static sleep)
    if not _wait_for_backend(base_url, timeout_s=20):
        log_event("⚠️  Backend did not respond to /health within timeout. Continuing to open window…")

    class JSBridge:
        """JS → Python bridge for closing the app."""
        def close_app(self):
            print("\n🔴 Close button clicked — exiting HIREX...\n")
            # Try graceful shutdown then hard-exit
            try:
                os.kill(os.getpid(), signal.SIGTERM)
            except Exception:
                os._exit(0)

    window = webview.create_window(
        title="HIREX — Resume Optimizer",
        url=base_url,
        width=1280,
        height=820,
        resizable=True,
        frameless=False,  # use native Windows title bar
        background_color="#10131a",
        js_api=JSBridge(),
    )

    # Inject top-right ✖ button (HTML overlay)
    def inject_close_button():
        js_code = """
        (function(){
          if (window.__hirexCloseInjected) return;
          window.__hirexCloseInjected = true;
          const btn = document.createElement('button');
          btn.textContent = '✖';
          Object.assign(btn.style, {
            position:'fixed', top:'10px', right:'15px', zIndex:'9999',
            padding:'6px 10px', border:'none', borderRadius:'6px',
            fontSize:'16px', background:'#e74c3c', color:'#fff', cursor:'pointer',
            boxShadow:'0 2px 6px rgba(0,0,0,0.3)'
          });
          btn.addEventListener('mouseenter',()=>btn.style.background='#c0392b');
          btn.addEventListener('mouseleave',()=>btn.style.background='#e74c3c');
          btn.addEventListener('click', ()=> window.pywebview?.api?.close_app && window.pywebview.api.close_app());
          document.body.appendChild(btn);
        })();
        """
        try:
            window.evaluate_js(js_code)
        except Exception as e:
            log_event(f"⚠️  Failed to inject close button: {e}")

    # Launch the desktop window
    try:
        # Prefer Edge (fastest on modern Windows); fall back automatically
        webview.start(func=inject_close_button, gui="edgechromium", debug=False)
    except Exception:
        webview.start(func=inject_close_button, debug=False)


# ============================================================
# 🚀 Entry Point
# ============================================================
if __name__ == "__main__":
    print("🚀 Launching HIREX (Windows App Mode)...")
    print("✅ Backend: http://127.0.0.1:8000")
    print("🟢 Click ✖ or press Ctrl+C to exit.\n")

    # Graceful CTRL+C handling on Windows
    def _graceful_exit(signum, frame):
        print("\n🛑 Shutting down HIREX…")
        os._exit(0)

    try:
        signal.signal(signal.SIGINT, _graceful_exit)
        # SIGTERM is available on Windows in Python 3.8+; use if present
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _graceful_exit)
    except Exception:
        pass

    # Run FastAPI backend in background
    backend_thread = threading.Thread(target=start_fastapi, daemon=True)
    backend_thread.start()

    # Launch the desktop UI window
    start_window()

# To run backend only (no GUI):  uvicorn main:app --reload
