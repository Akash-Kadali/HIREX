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

# ------------------------------------------------------------
# Directory Structure
# ------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
TEMP_LATEX_DIR = CACHE_DIR / "latex_builds"
TEMPLATE_DIR = BACKEND_DIR / "templates"

# Ensure required directories exist
for d in [DATA_DIR, CACHE_DIR, TEMP_LATEX_DIR, TEMPLATE_DIR]:
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
# 🧩 Path Utilities
# ============================================================
def get_tex_build_path(filename: str) -> Path:
    """Return absolute path for a temporary LaTeX build file."""
    return TEMP_LATEX_DIR / filename


# ============================================================
# 🧪 Local Test
# ============================================================
if __name__ == "__main__":
    print("=========== HIREX CONFIG ===========")
    print(f"APP_NAME        : {APP_NAME}")
    print(f"APP_VERSION     : {APP_VERSION}")
    print(f"BASE_DIR        : {BASE_DIR}")
    print(f"DEBUG_MODE      : {DEBUG_MODE}")
    print(f"MAX_UPLOAD_MB   : {MAX_UPLOAD_MB}")
    print(f"TEMP_LATEX_DIR  : {TEMP_LATEX_DIR}")
    print(f"OPENAI_API_KEY  : {'set' if OPENAI_API_KEY else 'missing'}")
    print(f"HUMANIZE_API_KEY: {'set' if HUMANIZE_API_KEY else 'missing'}")
