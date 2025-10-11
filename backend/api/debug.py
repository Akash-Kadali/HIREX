"""
HIREX • api/debug.py
Minimal debug logger endpoint. Anything POSTed here is printed to server CMD.
"""

from fastapi import APIRouter, Request
from backend.core.utils import log_event

router = APIRouter()

@router.post("/log")
async def debug_log(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {"raw": (await request.body()).decode("utf-8", "ignore")}
    log_event(f"🟦 FE DEBUG: {payload}")
    return {"ok": True}
