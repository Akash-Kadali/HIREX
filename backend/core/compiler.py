"""
HIREX • core/compiler.py
Secure LaTeX compiler — converts .tex → .pdf in a sandboxed temp directory.
Prevents shell escapes, runs pdflatex with restricted flags.
Author: Sri Akash Kadali
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

from backend.core import config
from backend.core.utils import log_event


# ============================================================
# 🧩 Safe PDF Compilation Utility
# ============================================================
def compile_latex_safely(tex_string: str) -> bytes | None:
    """
    Compiles LaTeX source code into PDF bytes securely.
    Returns PDF bytes (on success) or None (on failure).

    Security & Stability:
    - Uses sandboxed temp directory under config.TEMP_LATEX_DIR
    - Disables shell escape and external commands
    - Runs pdflatex twice for stable references
    - Cleans up temporary files automatically
    - Compatible with TeX Live / MiKTeX on all OS
    """
    pdflatex_path = shutil.which("pdflatex")
    if pdflatex_path is None:
        log_event("⚠️ pdflatex not found in PATH. Skipping PDF build.")
        return None

    try:
        temp_root = getattr(config, "TEMP_LATEX_DIR", None)
        with tempfile.TemporaryDirectory(dir=temp_root) as tmpdir:
            tmpdir = Path(tmpdir)
            tex_path = tmpdir / "resume.tex"
            pdf_path = tmpdir / "resume.pdf"
            log_path = tmpdir / "compile.log"

            # Write LaTeX source
            tex_path.write_text(tex_string, encoding="utf-8")
            log_event(f"📄 Starting LaTeX compile in: {tmpdir}")

            # Safe compile command
            cmd = [
                pdflatex_path,
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-no-shell-escape",
                str(tex_path),
            ]

            # Run pdflatex twice for proper references
            for i in range(2):
                proc = subprocess.run(
                    cmd,
                    cwd=tmpdir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=90,
                    encoding="utf-8",
                    errors="ignore",
                    check=False,
                )
                log_path.write_text(proc.stdout)
                log_event(f"🧱 pdflatex pass {i+1} completed (code={proc.returncode})")

            # Check PDF output
            if pdf_path.exists():
                pdf_bytes = pdf_path.read_bytes()
                size_kb = len(pdf_bytes) / 1024
                log_event(f"✅ PDF built successfully ({size_kb:.1f} KB).")
                return pdf_bytes

            # Error fallback — show last 10 lines of log
            if log_path.exists():
                tail = "\n".join(log_path.read_text().splitlines()[-10:])
                log_event(f"⚠️ No PDF produced. Last compiler output:\n{tail}")
            else:
                log_event("⚠️ Compilation failed — no log file created.")
            return None

    except subprocess.TimeoutExpired:
        log_event("⏱️ LaTeX compilation timed out (90s limit).")
        return None
    except Exception as e:
        log_event(f"💥 Unexpected LaTeX compile error: {e}")
        return None


# ============================================================
# 🧪 Local Test
# ============================================================
if __name__ == "__main__":
    sample_tex = r"""
    \documentclass{article}
    \begin{document}
    Hello World! This is a HIREX LaTeX compile test.
    \end{document}
    """
    result = compile_latex_safely(sample_tex)
    print("✅ PDF generated:", bool(result))
