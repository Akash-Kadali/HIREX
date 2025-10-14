"""
HIREX • api/humanize.py
Integrates with AIHumanize.io API for tone-only rewriting of Experience & Project bullets.
Now includes strong LaTeX sanitizer to prevent duplicated preamble or document corruption.
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
MAX_CONCURRENT = 5  # concurrent request limit
TIMEOUT_SEC = 15.0  # per-request timeout (seconds)


# ============================================================
# 🧹 Sanitizer: Removes Any LaTeX Preamble or Junk
# ============================================================
def clean_humanized_text(text: str) -> str:
    """Remove LaTeX headers, packages, or markdown fences accidentally injected by AIHumanize."""
    cleaned = text

    # Remove document/preamble-level commands
    cleaned = re.sub(r"(?i)\\document(class|begin|end)\{.*?\}", "", cleaned)
    cleaned = re.sub(r"(?i)\\usepackage(\[[^\]]*\])?\{.*?\}", "", cleaned)
    cleaned = re.sub(r"(?i)\\newcommand\{[^}]*\}\{[^}]*\}", "", cleaned)
    cleaned = re.sub(r"(?i)\\input\{.*?\}", "", cleaned)

    # Remove comments and resume headers
    cleaned = re.sub(r"(?m)^%.*$", "", cleaned)
    cleaned = re.sub(r"(?i)%[-=]+.*?\n", "", cleaned)
    cleaned = re.sub(r"(?i)%\s*resume.*?\n", "", cleaned)

    # Remove markdown/code fences and stray braces
    cleaned = cleaned.replace("```latex", "").replace("```", "")
    cleaned = re.sub(r"[\{\}]+", " ", cleaned)

    # Escape unescaped % (so they don't comment out LaTeX text)
    cleaned = re.sub(r"(?<!\\)%", r"\\%", cleaned)

    # Collapse excessive whitespace
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

    # Final safety: reject if forbidden LaTeX keywords remain
    if re.search(r"\\document|\\usepackage|\\begin|\\newcommand", cleaned, re.I):
        log_event("⚠️ [HUMANIZE] Unsafe LaTeX fragment detected — reverting to original.")
        return ""

    return cleaned


# ============================================================
# 🧠 Humanize All \resumeItem Bullets (Concurrent Mode)
# ============================================================
async def humanize_resume_items(tex_content: str) -> str:
    """
    Finds all \\resumeItem{...} bullets and sends each one to AIHumanize.io
    for tone/clarity improvement. Sanitizes every rewritten bullet to ensure valid LaTeX.
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

    # ------------------------------------------------------------
    # 🧩 Individual Bullet Rewrite with Sanitization + Retry
    # ------------------------------------------------------------
    async def rewrite_bullet(bullet: str, idx: int) -> str:
        original = bullet.strip()
        if not original:
            return original

        payload = {
            "model": AIHUMANIZE_MODE,
            "mail": AIHUMANIZE_EMAIL,
            "data": original,
        }

        for attempt in range(2):  # retry twice max
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT_SEC) as client:
                    r = await client.post(AIHUMANIZE_API_URL, headers=headers, json=payload)
                    r.raise_for_status()
                    data = r.json()

                    if data.get("code") == 200 and data.get("data"):
                        candidate = clean_humanized_text(data["data"].strip())
                        if candidate:
                            log_event(f"    • Bullet {idx} rewritten safely (len={len(candidate)})")
                            return candidate
                        else:
                            log_event(f"    • Bullet {idx} reverted (unsafe LaTeX detected)")
                            return original
            except Exception as e:
                log_event(f"⚠️ [HUMANIZE] Bullet {idx} attempt {attempt+1} failed: {e}")
                await asyncio.sleep(0.5)

        log_event(f"⚠️ [HUMANIZE] Bullet {idx} fallback to original")
        return original

    # ------------------------------------------------------------
    # 🚦 Run Concurrently (Limited by Semaphore)
    # ------------------------------------------------------------
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def limited_rewrite(i, b):
        async with semaphore:
            return await rewrite_bullet(b, i)

    rewritten_lines = await asyncio.gather(*[limited_rewrite(i, b) for i, b in enumerate(bullets, start=1)])

    # ------------------------------------------------------------
    # 🧩 Replace Bullets Safely in LaTeX
    # ------------------------------------------------------------
    out_tex = tex_content
    for old, new in zip(bullets, rewritten_lines):
        safe_new = new.strip().rstrip(".")
        out_tex = out_tex.replace(old, safe_new, 1)

    # Final sanity cleanup: remove any stray reinserted preambles
    out_tex = re.sub(r"(?i)\\document(class|begin|end)\{.*?\}", "", out_tex)
    out_tex = re.sub(r"(?i)%\s*resume.*?\n", "", out_tex)
    out_tex = re.sub(r"(?i)\\usepackage(\[[^\]]*\])?\{.*?\}", "", out_tex)
    out_tex = re.sub(r"(?i)\\newcommand\{[^}]*\}\{[^}]*\}", "", out_tex)
    out_tex = re.sub(r"\n{3,}", "\n\n", out_tex).strip()

    log_event(f"✅ [HUMANIZE] Completed {len(bullets)} bullets successfully (sanitized concurrent mode)")
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
