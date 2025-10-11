"""
HIREX • api/optimize.py
Job-Aware Resume Optimizer (OpenAI + AIHumanize.io version)
Preserves full LaTeX content unchanged and prints step-by-step debug logs.
Optimized for reliability and concurrency.
Author: Sri Akash Kadali
"""

import re
import httpx
import asyncio
from fastapi import APIRouter, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI

from backend.core import config
from backend.core.security import secure_tex_input
from backend.core.utils import log_event

router = APIRouter()
openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)

# ============================================================
# 🧠 Resume Optimization via OpenAI (Preserves Full LaTeX)
# ============================================================
async def optimize_resume_latex(base_tex: str, jd_text: str) -> str:
    log_event("🟨 [AI] Step 1: Building prompt for OpenAI")

    protected_macros = re.findall(
        r"(\\newcommand\{\\resumeItem\}[\s\S]*?\\newcommand\{\\resumeSubheading\})",
        base_tex,
    )
    macro_block = protected_macros[0] if protected_macros else ""

    base_tex_guarded = re.sub(
        r"(\\newcommand\{\\resumeItem\}[\s\S]*?\\newcommand\{\\resumeSubheading\})",
        r"% === BEGIN: DO NOT EDIT MACROS ===\n\1\n% === END: DO NOT EDIT MACROS ===",
        base_tex,
    )

    prompt = f"""
You are HIREX, a professional LaTeX Resume Optimizer AI.

GOAL:
Given the complete LaTeX resume and a Job Description (JD),
rewrite only from the EDUCATION section onward.

STRICT RULES:
1. Preserve everything above the EDUCATION section exactly (preamble, formatting, macros, etc.).
2. Fill "Relevant Coursework:" under EDUCATION with 4–6 items related to the JD.
3. Create SKILLS section from JD-relevant items only (Languages, Frameworks, Cloud, Tools).
4. For each job in EXPERIENCE:
   - Keep company name, title, and dates unchanged.
   - Include exactly 3 concise JD-aligned bullet points using \\resumeItem{{...}}.
   - Do not add fake companies or change organization names.
5. Optimize ACHIEVEMENTS section — keep only JD-relevant achievements.
6. Maintain full LaTeX syntax and indentation.
7. Output only valid LaTeX content from %-----------EDUCATION----------- to \\end{{document}}.
   Do not include ``` fences or any commentary.

BASE RESUME (.tex):
{base_tex_guarded}

JOB DESCRIPTION:
{jd_text}
"""

    try:
        log_event("🟨 [AI] Step 2: Sending request to OpenAI API")
        resp = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
        )
        log_event("🟩 [AI] Step 3: Response received from OpenAI")

        partial_tex = resp.choices[0].message.content or ""
        cleaned_partial = partial_tex.replace("```latex", "").replace("```", "").strip()

        if macro_block:
            cleaned_partial = re.sub(
                r"\\newcommand\{\\resumeItem\}[\s\S]*?\\newcommand\{\\resumeSubheading\}",
                lambda m: macro_block,
                cleaned_partial,
            )
        elif "\\newcommand{\\resumeItem}" not in cleaned_partial:
            cleaned_partial = (
                "\\newcommand{\\resumeItem}[1]{\\item\\small{{#1} \\vspace{-2pt}}}\n"
                + cleaned_partial
            )

        match = re.search(r"(%-----------EDUCATION-----------)", base_tex)
        if not match:
            log_event("⚠️ EDUCATION marker not found in base resume.")
            return base_tex

        preamble = base_tex[: match.end()]
        final_tex = preamble + "\n" + cleaned_partial

        if "\\end{document}" not in final_tex:
            final_tex += "\n\\end{document}\n"

        print("\n" + "=" * 90)
        print("📄 FINAL OPTIMIZED LATEX OUTPUT (DEBUG MODE)")
        print("=" * 90)
        print(final_tex)
        print("=" * 90)
        print(f"📏 Length: {len(final_tex)} characters")
        print("=" * 90 + "\n")

        log_event("✅ [AI] Step 4: OpenAI rewrite complete (LaTeX preserved)")
        return final_tex

    except Exception as e:
        log_event(f"💥 [AI] OpenAI optimization failed: {e}")
        raise HTTPException(status_code=500, detail=f"OpenAI optimization failed: {e}")


# ============================================================
# ✨ Humanize Experience Bullets (Concurrent Mode)
# ============================================================
async def humanize_experience_bullets(tex_content: str) -> str:
    log_event("🟨 [HUMANIZE] Step 1: Extracting bullets")
    bullets = re.findall(r"\\resumeItem\{(.*?)\}", tex_content, re.DOTALL)
    log_event(f"    • Found {len(bullets)} bullets")

    if not bullets:
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
            "model": "0",
            "mail": "kadali18@terpmail.umd.edu",
            "data": text,
        }
        for attempt in range(2):  # retry twice if failed
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    r = await client.post("https://aihumanize.io/api/v1/rewrite",
                                          headers=headers, json=payload)
                    r.raise_for_status()
                    data = r.json()
                    if data.get("code") == 200 and data.get("data"):
                        log_event(f"    • Bullet {idx} rewritten (len={len(data['data'])})")
                        return data["data"].strip()
            except Exception as e:
                log_event(f"⚠️ [HUMANIZE] Bullet {idx} attempt {attempt+1} failed: {e}")
                await asyncio.sleep(0.5)
        return text

    # 🧩 Run concurrently with limit
    semaphore = asyncio.Semaphore(5)  # max 5 concurrent calls

    async def limited_rewrite(idx, b):
        async with semaphore:
            return await rewrite_bullet(b, idx)

    tasks = [limited_rewrite(i, b) for i, b in enumerate(bullets, start=1)]
    rewritten_lines = await asyncio.gather(*tasks)

    # Replace bullets
    out_tex = tex_content
    for old, new in zip(bullets, rewritten_lines):
        out_tex = out_tex.replace(old, new.strip().rstrip("."), 1)

    out_tex = re.sub(
        r"(Developed automated processes for cleansing and analyzing large volumes of data,[^.]*)+",
        r"\1",
        out_tex,
        flags=re.IGNORECASE,
    )

    print("\n" + "=" * 90)
    print("💬 HUMANIZED BULLETS (DEBUG MODE)")
    print("=" * 90)
    print(out_tex)
    print("=" * 90)
    print(f"📏 Length after Humanize: {len(out_tex)} characters")
    print("=" * 90 + "\n")

    log_event(f"✅ [HUMANIZE] Completed {len(bullets)} bullets concurrently")
    return out_tex


# ============================================================
# 🚀 Endpoint — /api/optimize
# ============================================================
@router.post("/optimize")
async def optimize_endpoint(base_resume_tex: UploadFile, jd_text: str = Form(...)):
    try:
        log_event("🟧 [PIPELINE] Step 1: Reading uploaded file")
        tex_bytes = await base_resume_tex.read()
        log_event(f"    • File name: {base_resume_tex.filename}, bytes: {len(tex_bytes)}")

        tex = tex_bytes.decode("utf-8", errors="ignore")
        raw_tex = secure_tex_input(base_resume_tex.filename, tex)
        log_event(f"🟧 [PIPELINE] Step 2: Decoded resume length = {len(raw_tex)}")

        jd_text = jd_text.strip()
        log_event(f"🟧 [PIPELINE] Step 3: JD length = {len(jd_text)}")

        if not raw_tex or not jd_text:
            raise HTTPException(status_code=400, detail="Missing resume or JD input.")

        log_event("🟧 [PIPELINE] Step 4: Sending to OpenAI...")
        optimized = await optimize_resume_latex(raw_tex, jd_text)
        log_event(f"    • Optimized length = {len(optimized)}")

        log_event("🟧 [PIPELINE] Step 5: Sending to Humanize API concurrently...")
        humanized = await humanize_experience_bullets(optimized)
        log_event(f"    • Humanized length = {len(humanized)}")

        print("\n" + "=" * 90)
        print("🚀 FINAL HIREX OUTPUT (POST-HUMANIZE)")
        print("=" * 90)
        print(humanized)
        print("=" * 90)
        print(f"📏 Total Output Length: {len(humanized)} characters")
        print("=" * 90 + "\n")

        log_event("🟩 [PIPELINE] Step 6: Returning final LaTeX output")
        return JSONResponse({"tex_string": humanized})

    except Exception as e:
        log_event(f"💥 [PIPELINE] Optimization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
