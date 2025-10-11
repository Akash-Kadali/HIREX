"""
HIREX • api/humanize.py
Integrates with AIHumanize.io API for tone-only rewriting of Experience & Project bullets.
Optimized for concurrency and reliability.
Author: Sri Akash Kadali
"""

import re
import httpx
import asyncio
from backend.core import config
from backend.core.utils import log_event

# ============================================================
# ⚙️ Configuration
# ============================================================
AIHUMANIZE_API_URL = "https://aihumanize.io/api/v1/rewrite"
AIHUMANIZE_MODE = "0"  # 0: quality | 1: balance | 2: enhanced
AIHUMANIZE_EMAIL = "kadali18@terpmail.umd.edu"  # registered account
MAX_CONCURRENT = 5  # control concurrency
TIMEOUT_SEC = 15.0   # per-request timeout


# ============================================================
# 🧠 Humanize All \resumeItem Bullets (Concurrent Mode)
# ============================================================
async def humanize_resume_items(tex_content: str) -> str:
    """
    Finds all \\resumeItem{...} bullets and sends each one to AIHumanize.io
    for tone/clarity improvement. Processes up to MAX_CONCURRENT bullets
    concurrently with retries. Preserves LaTeX structure.
    """
    log_event("🟨 [HUMANIZE] Step 1: Extracting bullets")
    bullets = re.findall(r"\\resumeItem\{(.*?)\}", tex_content, re.DOTALL)
    log_event(f"    • Found {len(bullets)} bullets")

    if not bullets:
        log_event("⚠️ [HUMANIZE] No bullets found to humanize.")
        return tex_content

    headers = {
        "Authorization": config.HUMANIZE_API_KEY,
        "Content-Type": "application/json",
    }

    async def rewrite_bullet(bullet: str, idx: int) -> str:
        """Handle a single bullet rewrite with timeout + retry."""
        text = bullet.strip()
        if not text:
            return text

        payload = {
            "model": AIHUMANIZE_MODE,
            "mail": AIHUMANIZE_EMAIL,
            "data": text,
        }

        for attempt in range(2):  # retry twice if fails
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT_SEC) as client:
                    r = await client.post(AIHUMANIZE_API_URL, headers=headers, json=payload)
                    r.raise_for_status()
                    data = r.json()

                    if data.get("code") == 200 and data.get("data"):
                        rewritten = data["data"].strip()
                        log_event(f"    • Bullet {idx} rewritten (len={len(rewritten)})")
                        return rewritten
            except Exception as e:
                log_event(f"⚠️ [HUMANIZE] Bullet {idx} attempt {attempt+1} failed: {e}")
                await asyncio.sleep(0.5)

        log_event(f"⚠️ [HUMANIZE] Bullet {idx} fallback to original")
        return text

    # Run limited concurrency
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def limited_rewrite(idx, b):
        async with semaphore:
            return await rewrite_bullet(b, idx)

    tasks = [limited_rewrite(i, b) for i, b in enumerate(bullets, start=1)]
    rewritten_lines = await asyncio.gather(*tasks)

    # ============================================================
    # 🧩 Replace bullets safely in LaTeX
    # ============================================================
    out_tex = tex_content
    for old, new in zip(bullets, rewritten_lines):
        safe_new = new.strip().rstrip(".")
        out_tex = out_tex.replace(old, safe_new, 1)

    # ✅ Optional cleanup for repetitive sentences
    out_tex = re.sub(
        r"(Developed automated processes for cleansing and analyzing large volumes of data,[^.]*)+",
        r"\1",
        out_tex,
        flags=re.IGNORECASE,
    )

    # Debug output
    print("\n" + "=" * 90)
    print("💬 HUMANIZED BULLETS (DEBUG MODE)")
    print("=" * 90)
    print(out_tex)
    print("=" * 90)
    print(f"📏 Length after Humanize: {len(out_tex)} characters")
    print("=" * 90 + "\n")

    log_event(f"✅ [HUMANIZE] Completed {len(bullets)} bullets successfully (concurrent mode)")
    return out_tex


# ============================================================
# 🧪 Local Test
# ============================================================
if __name__ == "__main__":
    import asyncio

    sample_tex = r"""
    \resumeItem{worked on python scripts for data processing}
    \resumeItem{helped team with docker deployments}
    \resumeItem{deployed 3 APIs with 99% uptime}
    """

    async def run_test():
        result = await humanize_resume_items(sample_tex)
        print("\n=== Humanized Output ===\n", result)

    asyncio.run(run_test())
