# HIREX — High Resume eXpert (v1.2.1)

*A job-aware LaTeX resume optimizer with an optional “humanize” pass. Built with FastAPI + OpenAI + (optional) AIHumanize, and a modern HTML/JS UI. Ships with a Windows desktop wrapper via PyWebview.*

> **What’s new (v1.2.x)**
>
> * **Single-base flow:** the UI no longer uploads `.tex`; it always uses the canonical server file `data/samples/base_resume.tex` (override with `BASE_RESUME_PATH`).   
> * **Polished UI:** dark/light theme toggle, sticky left sidebar, mobile slide-in menu, **Humanize pill switch**, and a top progress bar with graceful finish.  
> * **Smarter Preview:** adaptive PDF viewer + **JD Fit Score gauge** (auto-derives from backend score or coverage).  
> * **Resilient frontend:** cancel button, retries, compatibility shim if an older backend still requires `base_resume_tex`.  
> * **Back-end brain:** iterative coverage loop that targets **≥99%** JD token coverage, plus **one-by-one bullet expansion** with compile checks to keep to one page.  

---

## ✨ What HIREX Does

* **Reads a LaTeX (.tex) resume** and a **Job Description (JD)** (UI supplies JD only; backend loads base `.tex`). 
* **Extracts the company and role** from the JD with OpenAI.
* **Fills “Relevant Coursework”** (JD-aligned, deduped across degrees).
* **Rebuilds Skills in exactly 4 compact rows** with **GPT-proposed row labels** (deterministic layout).
* **Retargets Experience/Projects bullets** to the JD and **enforces ≤3 bullets per itemize**.
* **Coverage-driven refinement**: iteratively pushes JD keyword coverage to **≥99%** (truthful only). 
* **Smart expand (auto, optional)**: proposes extra truthful bullets **one-by-one** across roles while compiling after each try, **stopping before the PDF exceeds 1 page**. 
* **One-page guardrail**: if still >1 page, trims the **last Achievements bullet** (saves **Trim1, Trim2, …** snapshots).
* **Optional Humanize step**: rewrites only the English inside `\resumeItem{...}` for tone/clarity (no new facts), then mirrors the **one-page** guardrail.
* **Outputs PDFs** (base + humanized if enabled) and the final LaTeX.
* **JD Fit Score (UI)**: Preview shows a score **if the backend provides it** (falls back to coverage). 

> **Target user:** LaTeX power-users who want job-aware, ATS-sane tailoring without breaking their macros/template.

---

## 🗂 Repo Layout (key folders)

```
backend/
  core/
    compiler.py        # sandboxed pdflatex wrapper
    config.py          # env + paths + app constants (BASE_RESUME_PATH override)
    security.py        # upload validation (no LaTeX sanitization)
    utils.py           # logging, hashing, helpers
  api/
    optimize.py        # full pipeline + /api/optimize endpoint
    render_tex.py      # final LaTeX normalizer/closer
    latex_parse.py     # lenient section/bullet parsing
    humanize.py        # AIHumanize integration + sanitizer
    debug.py           # (optional) debug routes
frontend/
  index.html           # JD-only input, Humanize pill, progress bar, theme toggle
  preview.html         # adaptive PDFs + JD Fit Score gauge
  about.html, help.html
  static/js/           # util.js, ui.js, main.js, preview.js
  static/assets/       # icons, logo
  static/css/          # base.css, animations.css, app.css
main.py                # Boot FastAPI + (optional) PyWebview desktop window
data/
  samples/base_resume.tex
  Job Resumes/         # compiled PDFs saved here
```

> On startup, the app ensures `data/`, `data/cache/latex_builds/`, and output directories exist. PDFs are saved under **`data/Job Resumes/`**. 

---

## ⚙️ Requirements

* **Python** 3.10+
* **LaTeX** with `pdflatex` on `PATH` (TeX Live/MiKTeX)
* (Optional) **Edge WebView2** for the Windows desktop mode
* API keys:

  * `OPENAI_API_KEY` (required: JD parsing, skills/coursework, bullet retargeting)
  * `HUMANIZE_API_KEY` (optional, only if you toggle Humanize)

### Install Python deps

```bash
python -m venv .venv
# Windows:
. .venv/Scripts/activate
# macOS/Linux:
. .venv/bin/activate

pip install -U fastapi uvicorn httpx python-dotenv openai pywebview
```

---

## 🔐 Environment (.env)

Create a `.env` at repo root:

```ini
# Core
DEBUG=true
HIREX_SECRET=change-me
MAX_UPLOAD_MB=5

# Base resume (server file used by UI)
BASE_RESUME_PATH=data/samples/base_resume.tex

# APIs
OPENAI_API_KEY=sk-your-openai-key
HUMANIZE_API_KEY=Bearer your_aihumanize_api_key   # optional
```

> The UI always uses the server’s canonical base resume; override via `BASE_RESUME_PATH`. 

---

## ▶️ How to Run

### A) Windows Desktop App (PyWebview)

```bash
python main.py
```

*Launches FastAPI at `http://127.0.0.1:8000` and opens a desktop window.*

### B) API + Browser (no desktop wrapper)

```bash
uvicorn main:app --reload
# then open http://127.0.0.1:8000
```

---

## 🌐 Frontend Workflow

1. Open **Home** (`index.html`).
2. Paste the **Job Description** (JD). The base resume comes from `data/samples/base_resume.tex`. 
3. Toggle **Humanize** (optional).
4. Click **Optimize Resume**.
5. Go to **Preview**:

   * View **Optimized** and (if enabled) **Humanized** PDFs.
   * **Download** PDFs and the **final .tex**.
   * See **JD Fit Score** (if provided by backend; otherwise derived from coverage). 

### UI Details

* **Humanize pill switch** with keyboard/cross-tab sync. 
* **Progress bar** during optimization with graceful completion event. 
* **Theme toggle, sticky sidebar, and responsive mobile menu.**   
* **Local cache** of LaTeX/PDFs/score for Preview. 

---

## 🧠 Backend: Endpoints & Pipeline

### Endpoints

* `GET /` → `index.html`
* `GET /{page}.html` → `about`, `help`, `preview`, etc.
* `GET /static/...` → static assets
* `GET /health` → health check
* `POST /api/optimize` → **main pipeline** (form: `jd_text`, `use_humanize`; `base_resume_tex` optional for legacy flows) 
* `POST /api/debug/log` → optional frontend debug logging

### Pipeline (JD + base `.tex` → PDFs)

1. **Base resume**: use uploaded `.tex` if provided; otherwise load server default (`BASE_RESUME_PATH`). 
2. **JD parsing** → `company`, `role`.
3. **Coursework** → up to 6 JD-relevant course titles.
4. **Skills (4 rows)** with **GPT-proposed row labels**.
5. **Experience/Projects retargeting** (≤3 bullets each).
6. **Coverage refinement** to **≥99%** (truthful; variant-aware tokens). 
7. **Smart expand** (compile-guarded) to add bullets **until just under 1 page**. 
8. **Compile base PDF**.
9. **One-page trim loop**: remove the last **Achievements** bullet; save **TrimN** snapshots.
10. **Optional Humanize** once (if coverage ≥90%); mirror trim loop for humanized variant.
11. **Save outputs** under `data/Job Resumes/` and return JSON with coverage metrics and history. 

---

## 🔌 Example: API Usage

```bash
curl -X POST http://127.0.0.1:8000/api/optimize \
  -F "jd_text=$(cat jd.txt)" \
  -F "use_humanize=true"
# (Optionally add: -F "base_resume_tex=@/path/to/resume.tex" for legacy flows)
```

**Response (shape)**

```json
{
  "tex_string": "\\documentclass...\\end{document}",
  "pdf_base64": "JVBERi0xLjQK...",
  "pdf_base64_humanized": "JVBERi0xLjQK...",
  "company_name": "Company",
  "role": "Role",
  "saved_paths": ["/abs/path/Trim1.pdf", "..."],
  "coverage_ratio": 0.99,
  "coverage_present": ["python","sql","llms"],
  "coverage_missing": [],
  "coverage_history": [{"round":1,"coverage":0.84}, {"round":2,"coverage":0.93}, {"round":3,"coverage":0.99}],
  "humanized": true
}
```

---

## 🧩 Customization Pointers

* **Model**: default chat model is `gpt-4o-mini`.
* **Humanize**: tune concurrency/timeouts in `api/humanize.py`.
* **Skill labels**: GPT proposes 4 row labels; if invalid, code falls back to safe defaults.
* **Coverage target**: change min ratio / rounds in `refine_resume_to_keyword_coverage(...)`. 
* **Smart expand**: control `max_total_new` / `max_new_per_block` (compile-guarded). 
* **Base resume path**: set `BASE_RESUME_PATH` in `.env`. 

---

## 🔒 Security & Stability

* **LaTeX preserved**; we use brace-balanced parsers to target just the content we edit.
* **Sandboxed `pdflatex`** in a temp build dir; no shell escape; hardened error/timeouts.
* **Humanize sanitizer**: strips any injected preamble/class, escapes stray `%`, and only rewrites bullet text.
* **Frontend timeouts**: form submit bounded; **Cancel** is available mid-run. 

---

## 🚑 Troubleshooting

* **“No PDFs appear”** → ensure `pdflatex` is installed and on PATH.
* **“Using the wrong base resume?”** → verify `BASE_RESUME_PATH` or replace `data/samples/base_resume.tex`.  
* **“Humanized PDF missing”** → backend saves a fallback `.tex` for failed compiles; check logs.
* **“Score didn’t show in Preview”** → the UI derives a score from coverage if backend didn’t provide one. 

---

## 📄 License

MIT — free to use, modify, and distribute.

---

## 🙏 Credits

* Built by **Sri Akash Kadali** (University of Maryland, College Park)
* Stack: **FastAPI · Python · LaTeX · OpenAI API · Humanize API · HTML · JS**

---

## 📦 Change Log

### v1.2.1 (UI/JS refresh)

* **main.js / ui.js** unified integration, **cancel** mid-run, robust retries, and compatibility retry with placeholder `base_resume_tex` when a legacy backend responds with 422.  
* Cross-tab **theme** and **Humanize** state sync; sticky sidebar consistency; mobile menu polish. 

### v1.2.0 (UI)

* **JD-only** input; base resume sourced from server file; **Humanize pill switch**; **progress bar**; adaptive Preview with **JD Fit Score** gauge.    

### v1.2.0 (Backend)

* Iterative coverage loop targeting **≥99%** (variant-aware matching), JD-aligned 4-row Skills with **GPT labels**, and compile-guarded **Smart expand** bullets to stay ≤1 page.  

---

## 🔧 Upgrade Notes (from v1.1.x)

* Remove any `.tex` upload UI; the frontend now posts only the JD + Humanize flag. 
* Place/point your canonical base resume at `data/samples/base_resume.tex` or set `BASE_RESUME_PATH`. 
* Ensure output write permissions for `data/Job Resumes/`. 

---
