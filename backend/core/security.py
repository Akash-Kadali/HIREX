"""
HIREX • core/security.py
Security and validation utilities for uploaded files and user input.
This version preserves full LaTeX content (no sanitization or macro stripping).
Author: Sri Akash Kadali
"""

import os
from backend.core import config
from backend.core.utils import safe_filename, log_event


# ============================================================
# ⚙️ File Validation
# ============================================================
def validate_file(upload_name: str, content: bytes) -> str:
    """
    Validate uploaded file before use.
    Returns sanitized filename if safe, else raises ValueError.
    """
    if not upload_name:
        raise ValueError("❌ Missing filename in upload.")

    _, ext = os.path.splitext(upload_name)
    if ext.lower() not in getattr(config, "ALLOWED_EXTENSIONS", {".tex"}):
        raise ValueError(f"❌ Invalid file extension: {ext}")

    size_mb = len(content) / (1024 * 1024)
    max_mb = getattr(config, "MAX_UPLOAD_MB", 5)
    if size_mb > max_mb:
        raise ValueError(f"❌ File exceeds {max_mb} MB limit (got {size_mb:.2f} MB).")

    if not content.strip():
        raise ValueError("❌ Uploaded file is empty.")

    safe_name = safe_filename(upload_name)
    log_event(f"✅ File validated: {safe_name} ({size_mb:.2f} MB)")
    return safe_name


# ============================================================
# 🧩 Direct Pass-through (No Sanitization)
# ============================================================
def secure_tex_input(filename: str, content) -> str:
    """
    Lightweight safety layer:
      1. Validate file type and size.
      2. Decode to UTF-8 safely.
      3. Preserve raw LaTeX exactly (no cleaning or filtering).
    Returns original LaTeX ready for OpenAI optimization.
    """
    _ = validate_file(
        filename,
        content if isinstance(content, (bytes, bytearray)) else str(content).encode(),
    )

    try:
        if isinstance(content, (bytes, bytearray)):
            tex = content.decode("utf-8", errors="ignore")
        elif isinstance(content, str):
            tex = content
        else:
            raise TypeError("Unsupported content type for LaTeX input.")
    except Exception as e:
        raise ValueError(f"⚠️ Failed to decode file as UTF-8: {e}")

    log_event(f"✅ Raw LaTeX preserved and validated for: {filename}")
    return tex


# ============================================================
# 🧪 Local Test
# ============================================================
if __name__ == "__main__":
    example = br"""
    \documentclass{article}
    \begin{document}
    Hello \textbf{World!} This content should remain unchanged.
    \input{my_commands.tex}
    \end{document}
    """

    try:
        raw = secure_tex_input("resume.tex", example)
        print("==== Raw Output ====")
        print(raw)
    except Exception as e:
        print("ERROR:", e)
