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

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)

if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)


# ============================================================
# 🌐 FastAPI Backend
# ============================================================
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from api import optimize
from api import debug as debug_api  # optional debug routes
from backend.core.utils import log_event

app = FastAPI(
    title="HIREX API",
    description="HIgh REsume eXpert — Job-Aware Resume Optimizer (LaTeX-based)",
    version="1.0.0",
)


# ------------------------------------------------------------
# Middleware — Request/Response Tracer
# ------------------------------------------------------------
@app.middleware("http")
async def trace_requests(request: Request, call_next):
    """Trace requests for debug output in console."""
    try:
        log_event(f"➡️  {request.method} {request.url.path}")
        if request.query_params:
            log_event(f"   ├─ query={dict(request.query_params)}")
        if request.method in ("POST", "PUT", "PATCH"):
            body = await request.body()
            log_event(f"   ├─ body-bytes={len(body)}")

        response = await call_next(request)
        log_event(f"⬅️  {request.method} {request.url.path} → {response.status_code}")
        return response
    except Exception as e:
        log_event(f"💥 Middleware error on {request.method} {request.url.path}: {e}")
        raise


# ------------------------------------------------------------
# Allow frontend access
# ------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.normpath(os.path.join(ROOT_DIR, "frontend"))
STATIC_PATH = os.path.join(FRONTEND_DIR, "static")

if os.path.exists(STATIC_PATH):
    app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")
else:
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ============================================================
# 📄 Static Frontend Routing
# ============================================================
@app.get("/")
def serve_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if not os.path.exists(index_path):
        return {"error": "Frontend not found"}
    return FileResponse(index_path)


@app.get("/{page_name}")
def serve_html(page_name: str):
    """Serve /about, /help, etc."""
    normalized = page_name if page_name.endswith(".html") else f"{page_name}.html"
    html_path = os.path.join(FRONTEND_DIR, normalized)
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


# ============================================================
# 🧩 API Routes
# ============================================================
app.include_router(optimize.router, prefix="/api", tags=["Optimization"])
app.include_router(debug_api.router, prefix="/api/debug", tags=["Debug"])


@app.get("/health", tags=["System"])
def health():
    """Health check endpoint."""
    return {"status": "ok", "message": "Backend online", "version": "1.0.0"}


# ============================================================
# 🪟 Windows App Launcher (PyWebview)
# ============================================================
def start_fastapi():
    """Run FastAPI server in a background thread."""
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")


def start_window():
    """Launch PyWebview GUI window with a custom floating ✖ Close button."""
    import webview

    # Wait for backend to boot
    time.sleep(1.5)

    class JSBridge:
        """JS → Python bridge for closing the app."""
        def close_app(self):
            print("\n🔴 Close button clicked — exiting HIREX...\n")
            os.kill(os.getpid(), signal.SIGTERM)

    window = webview.create_window(
        title="HIREX — Resume Optimizer",
        url="http://127.0.0.1:8000",
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
        const btn = document.createElement('button');
        btn.textContent = '✖';
        btn.style.position = 'fixed';
        btn.style.top = '10px';
        btn.style.right = '15px';
        btn.style.zIndex = '9999';
        btn.style.padding = '6px 10px';
        btn.style.border = 'none';
        btn.style.borderRadius = '6px';
        btn.style.fontSize = '16px';
        btn.style.background = '#e74c3c';
        btn.style.color = '#fff';
        btn.style.cursor = 'pointer';
        btn.style.boxShadow = '0 2px 6px rgba(0,0,0,0.3)';
        btn.onmouseenter = () => btn.style.background = '#c0392b';
        btn.onmouseleave = () => btn.style.background = '#e74c3c';
        btn.onclick = () => window.pywebview.api.close_app();
        document.body.appendChild(btn);
        """
        window.evaluate_js(js_code)

    # Launch the desktop window
    try:
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

    # Run FastAPI backend in background
    backend_thread = threading.Thread(target=start_fastapi, daemon=True)
    backend_thread.start()

    # Launch the desktop UI window
    start_window()

# To run backend only (no GUI):  uvicorn main:app --reload
