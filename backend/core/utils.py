"""
HIREX • core/utils.py
Common utility functions shared across backend modules.
For this version: No LaTeX escaping or text cleaning — passes LaTeX as-is.
Author: Sri Akash Kadali
"""

import re
import html
import hashlib
from datetime import datetime


# ============================================================
# 🔐 HASHING UTILITIES
# ============================================================
def sha256_str(data: str) -> str:
    """Generate a full SHA256 hash of a string."""
    if data is None:
        data = ""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def simple_hash(data: str, length: int = 8) -> str:
    """Generate a short deterministic hash (used for cache keys or content IDs)."""
    return sha256_str(data)[:length]


# ============================================================
# 📜 TEXT HELPERS (NO LATEX ESCAPING)
# ============================================================
def tex_escape(text: str) -> str:
    """
    Passthrough for LaTeX text (no escaping).
    Used when sending LaTeX to or receiving from OpenAI/Humanize.
    """
    return text or ""


def html_escape(text: str) -> str:
    """HTML-escape text for safe display inside web UIs (not LaTeX)."""
    return html.escape(text or "")


def clean_text(text: str) -> str:
    """
    Lightweight text cleaner (no normalization, no space compression).
    Keeps LaTeX intact.
    """
    if not text:
        return ""
    return str(text)


def safe_filename(name: str) -> str:
    """Convert a string into a safe, cross-platform filename."""
    if not name:
        return "file"
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    return name[:64]


# ============================================================
# 🧠 LOGGING & DIAGNOSTIC HELPERS
# ============================================================
def log_event(msg: str):
    """Lightweight timestamped log for backend events."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")


def benchmark(name: str):
    """
    Context manager for timing code blocks.
    Example:
        with benchmark("Optimize Resume"):
            run_some_code()
    """
    import time

    class _Timer:
        def __enter__(self):
            self.start = time.time()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            duration = (time.time() - self.start) * 1000
            log_event(f"⏱️ {name} completed in {duration:.1f} ms")

    return _Timer()


# ============================================================
# 🧪 Local Test
# ============================================================
if __name__ == "__main__":
    sample = r"""
    \documentclass{article}
    \begin{document}
    Hello \textbf{World!} $E = mc^2$
    \end{document}
    """
    print("Original LaTeX (unchanged):")
    print(sample)
    print("SHA256:", sha256_str(sample))
    print("Short Hash:", simple_hash(sample))
    print("Safe File:", safe_filename("My Resume (final).tex"))

    with benchmark("Hash Generation"):
        for _ in range(10000):
            sha256_str(sample)
