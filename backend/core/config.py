"""
HIREX • core/config.py
Global configuration for backend constants, environment variables,
and directory paths.
Author: Sri Akash Kadali
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ============================================================
# 🌍 Environment Setup
# ============================================================

# Load environment variables from .env if present
load_dotenv()


# ============================================================
# 📁 Directory Structure
# ============================================================
# Project root (…/HIREX)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Conventional top-level folders
BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
TEMP_LATEX_DIR = CACHE_DIR / "latex_builds"
TEMPLATE_DIR = BACKEND_DIR / "templates"
OUTPUT_DIR = DATA_DIR / "output"          # 📁 Final compiled resumes saved here
SAMPLES_DIR = DATA_DIR / "samples"        # 📁 Stores default/sample .tex files

# Ensure required directories exist
for d in [DATA_DIR, CACHE_DIR, TEMP_LATEX_DIR, TEMPLATE_DIR, OUTPUT_DIR, SAMPLES_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ============================================================
# ⚙️ Core Application Settings
# ============================================================
APP_NAME = "HIREX"
APP_VERSION = "1.0.0"
DEBUG_MODE = os.getenv("DEBUG", "true").lower() == "true"

# Upload restrictions
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "5"))
ALLOWED_EXTENSIONS = {".tex", ".txt"}


# ============================================================
# 🔐 Security & Secrets
# ============================================================
SECRET_KEY = os.getenv("HIREX_SECRET", "hirex-dev-secret")
JWT_ALGORITHM = "HS256"


# ============================================================
# 🤖 API Keys (OpenAI + Humanize)
# ============================================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
HUMANIZE_API_KEY = os.getenv("HUMANIZE_API_KEY", "")

# Developer warnings for missing keys (in debug mode only)
if DEBUG_MODE:
    if not OPENAI_API_KEY:
        print("[HIREX] ⚠️ OPENAI_API_KEY not found in environment.")
    if not HUMANIZE_API_KEY:
        print("[HIREX] ⚠️ HUMANIZE_API_KEY not found in environment.")


# ============================================================
# 🧷 Default Base Resume Path (server-side fallback)
# ============================================================
def _resolve_env_path(var_name: str, default_path: Path) -> Path:
    """
    Resolve a path from an env var. Supports ~ expansion and relative paths
    (relative to BASE_DIR). Falls back to default_path if var is unset/empty.
    """
    raw = os.getenv(var_name, "").strip()
    if not raw:
        return default_path
    p = Path(os.path.expanduser(raw))
    if not p.is_absolute():
        p = BASE_DIR / p
    return p


# Canonical default base-resume file (override with BASE_RESUME_PATH)
DEFAULT_BASE_RESUME: Path = _resolve_env_path(
    "BASE_RESUME_PATH",
    SAMPLES_DIR / "base_resume.tex",
)

if DEBUG_MODE and not DEFAULT_BASE_RESUME.exists():
    print(f"[HIREX] ⚠️ Default base resume not found at: {DEFAULT_BASE_RESUME}")
    print("        Set BASE_RESUME_PATH in .env or place base_resume.tex in data/samples/")


# ============================================================
# 🧩 Path Utilities
# ============================================================
def get_tex_build_path(filename: str) -> Path:
    """Return absolute path for a temporary LaTeX build artifact."""
    return TEMP_LATEX_DIR / filename


def get_output_pdf_path(filename: str) -> Path:
    """Return absolute path for saving final compiled resume PDFs."""
    return OUTPUT_DIR / filename


def is_allowed_upload(filename: str) -> bool:
    """Check if a filename has an allowed extension."""
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


# ============================================================
# 🧪 Local Test
# ============================================================
if __name__ == "__main__":
    print("=========== HIREX CONFIG ===========")
    print(f"APP_NAME              : {APP_NAME}")
    print(f"APP_VERSION           : {APP_VERSION}")
    print(f"BASE_DIR              : {BASE_DIR}")
    print(f"DEBUG_MODE            : {DEBUG_MODE}")
    print(f"MAX_UPLOAD_MB         : {MAX_UPLOAD_MB}")
    print(f"TEMP_LATEX_DIR        : {TEMP_LATEX_DIR}")
    print(f"OUTPUT_DIR            : {OUTPUT_DIR}")
    print(f"SAMPLES_DIR           : {SAMPLES_DIR}")
    print(f"DEFAULT_BASE_RESUME   : {DEFAULT_BASE_RESUME} ({'exists' if DEFAULT_BASE_RESUME.exists() else 'missing'})")
    print(f"OPENAI_API_KEY        : {'set' if OPENAI_API_KEY else 'missing'}")
    print(f"HUMANIZE_API_KEY      : {'set' if HUMANIZE_API_KEY else 'missing'}")
