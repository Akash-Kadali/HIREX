"""
HIREX • api/debug.py
Minimal debug logger endpoint. Anything POSTed here is printed to server CMD.
Author: Sri Akash Kadali
"""

from fastapi import APIRouter, Request
from backend.core.utils import log_event

router = APIRouter()


# ============================================================
# 🧠 Debug Log Endpoint — FE → BE
# ============================================================
@router.post("/log")
async def debug_log(request: Request):
    """
    Receives frontend debug payloads and prints them to the backend console.

    Expected JSON format:
      {
        "msg": "Some event name",
        "timestamp": "...",
        "page": "index.html",
        "origin": "http://127.0.0.1:8000",
        ...any other contextual data...
      }
    """
    try:
        payload = await request.json()
    except Exception:
        # Fallback for malformed or non-JSON payloads
        body = (await request.body()).decode("utf-8", "ignore")
        payload = {"raw": body}

    log_event(f"🟦 [FE DEBUG] {payload}")
    return {"ok": True, "received": True}
