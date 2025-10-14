# HIREX — High Resume eXpert

*A job-aware LaTeX resume optimizer with an optional “humanize” pass. Built with FastAPI + OpenAI + (optional) AIHumanize, and a minimal HTML/JS frontend. Includes a Windows desktop wrapper via PyWebview.*

---

## ✨ What HIREX Does

* **Reads a LaTeX (.tex) resume** and a **Job Description (JD)**.
* **Extracts the company and role** from the JD with OpenAI.
* **Fills/refreshes “Relevant Coursework”** (JD-aligned, no duplicates across degrees).
* **Rebuilds the Skills section in exactly 4 compact rows** with GPT-proposed row labels (deterministic content layout).
* **Retargets Experience/Projects bullets** to the JD and **enforces ≤3 bullets per itemize**.
* **Coverage-driven refinement**: iteratively pushes JD keyword coverage to **≥99%** (truthful only).
* **Smart expand (optional, auto)**: proposes and inserts extra bullets **one-by-one** across roles while compiling after each try, **stopping before the PDF exceeds 1 page**.
* **One-page guardrail**: if still >1 page, **iteratively removes the LAST Achievements bullet** and saves **Trim1, Trim2, …** snapshots.
* **Optional Humanize step**: rewrites only the English inside `\resumeItem{...}` for tone/clarity (no new facts), then mirrors the **one-page** guardrail.
* **Outputs PDFs** (base + humanized if enabled) and the final LaTeX.
* **JD Fit Score (UI)**: the Preview page shows a score **if the backend provides it**; otherwise it hides automatically.

> Target user: LaTeX power-users who want job-aware, ATS-sane tailoring without breaking their macros/template.

---

## 🗂 Repo Layout (key folders)

```text
backend/
  core/
    compiler.py        # sandboxed pdflatex wrapper
    config.py          # env + paths + app constants
    security.py        # upload validation (no LaTeX sanitization)
    utils.py           # logging, hashing, helpers
  api/
    optimize.py        # full pipeline + /api/optimize endpoint
    render_tex.py      # final LaTeX normalizer/closer
    latex_parse.py     # lenient section/bullet parsing
    humanize.py        # AIHumanize integration + sanitizer
    debug.py           # (optional) debug routes
frontend/
  index.html           # upload JD + .tex, toggle Humanize, submit
  preview.html         # shows PDFs/LaTeX (and JD Fit Score if present)
  about.html, help.html
  static/js/           # util.js, ui.js, main.js, preview.js
  static/assets/       # icons, logo
  static/css/          # app.css
main.py                # Boot FastAPI + (optional) PyWebview desktop window
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
. .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -U fastapi uvicorn httpx python-dotenv openai pywebview
```

> If the desktop window doesn’t open on Windows, run the backend only with Uvicorn (below).

---

## 🔐 Environment (.env)

Create a `.env` at repo root:

```ini
# Core
DEBUG=true
HIREX_SECRET=change-me
MAX_UPLOAD_MB=5

# APIs
OPENAI_API_KEY=sk-your-openai-key
HUMANIZE_API_KEY=Bearer your_aihumanize_api_key   # optional
```

---

## ▶️ How to Run

### A) Windows Desktop App (PyWebview)

```bash
python main.py
```

* Launches FastAPI at `http://127.0.0.1:8000` and opens a desktop window with a floating **✖ Close**.

### B) API + Browser (no desktop wrapper)

```bash
uvicorn main:app --reload
# then open http://127.0.0.1:8000
```

---

## 🌐 Frontend Workflow

1. Open **Home** (`index.html`).
2. Upload your base **`.tex` resume** and **paste the Job Description**.
3. (Optional) Toggle **Apply Humanize AI**.
4. Click **Optimize Resume**.
5. You’re redirected to **Preview** to:

   * View **Original Optimized PDF** and (if enabled) **Humanized PDF**.
   * **Download** PDFs and the **final .tex**.
   * See **JD Fit Score** (only if exposed by backend).

### Frontend behavior highlights

* `main.js`

  * Posts multipart to `/api/optimize` (3-min timeout).
  * Caches: `tex_string`, `pdf_base64`, optional `pdf_base64_humanized`, `company_name`, `role`, `saved_paths`.
  * Also caches **JD score/history if present** (keys: `hirex_rating_score`, `hirex_rating_history`).
* `preview.js`

  * Renders PDFs via Blob URLs; provides per-file downloads.
  * Shows **JD Fit Score card only if a score exists**.
  * Offers one-click **Copy LaTeX** and **Download .tex**.
* `util.js`, `ui.js`

  * Robust fetch helpers, toasts, clipboard/download utils, debug logger.

---

## 🧠 Backend: Endpoints & Pipeline

### Endpoints

* `GET /` → `index.html`
* `GET /{page}.html` → `about`, `help`, `preview`, etc.
* `GET /static/...` → static assets
* `GET /health` → health check
* `POST /api/optimize` → **main pipeline** (multipart: `base_resume_tex`, `jd_text`, `use_humanize`)
* `POST /api/debug/log` → optional frontend debug logging

### Pipeline (JD + .tex → PDFs)

1. **Upload validation**

   * Extension/size check (`.tex` accepted; backend also allows `.txt`, but UI restricts to `.tex`).
   * UTF-8 decode; **raw LaTeX preserved** (no macro stripping).
2. **JD parsing** → `company`, `role` (strict JSON).
3. **Coursework** → up to 6 JD-relevant course titles, **deduped across degrees**.
4. **Skills (4 rows)**

   * High-recall extraction (explicit + implied), canonicalization & pruning, **GPT-proposed row labels**.
5. **Experience/Projects retargeting**

   * Pick best bullets per block and **rewrite to include JD keywords truthfully**, **≤3 bullets** each.
6. **Coverage refinement (goal ≥99%)**

   * Compute JD-token coverage; **weave in missing keywords truthfully** across Skills & bullets; rebuild Skills each round.
7. **Smart expand (before trimming)**

   * Propose up to K additional truthful bullets per role; **compile after each insert** and **keep if still 1 page**.
8. **Compile base PDF** (sandboxed `pdflatex`, 2 passes).
9. **One-page guardrail**

   * If >1 page, **remove last Achievements bullet**, compile, **save every TrimN** until ≤1 page or no bullets left.
10. **Optional Humanize (once)**

    * If coverage ≥90% and toggled, humanize only `\resumeItem{...}`, compile, and **mirror the guardrail** if needed.
11. **Save outputs** under `data/Job Resumes/` and return JSON (see below).

---

## 📦 Output Files & Naming

```
data/Job Resumes/
  Sri_Akash_Kadali_Resume_{Company}_{Role}.pdf
  Sri_Akash_Kadali_Resume_{Company}_{Role}_Humanized.pdf
  Sri_Akash_Kadali_Resume_{Company}_{Role}_Trim1.pdf
  Sri_Akash_Kadali_Resume_{Company}_{Role}_Trim1_Humanized.pdf
  ...
```

---

## 🔌 API Usage (direct)

### Request

```bash
curl -X POST http://127.0.0.1:8000/api/optimize \
  -F "base_resume_tex=@/path/to/resume.tex" \
  -F "jd_text=$(cat jd.txt)" \
  -F "use_humanize=true"
```

### Response (shape)

```json
{
  "tex_string": "\\documentclass...\\end{document}",
  "pdf_base64": "JVBERi0xLjQK...",
  "pdf_base64_humanized": "JVBERi0xLjQK...",        // present only if humanize=true + success
  "company_name": "Company",
  "role": "Role",
  "saved_paths": ["/abs/path/Trim1.pdf", "..."],     // all saved PDFs (base + trims + humanized trims)
  "coverage_ratio": 0.99,                            // JD keyword coverage (0–1)
  "coverage_present": ["python","sql","llms", "..."],
  "coverage_missing": [],
  "coverage_history": [
    {"round": 1, "coverage": 0.84, "missing": ["..."]},
    {"round": 2, "coverage": 0.93, "missing": ["..."]},
    {"round": 3, "coverage": 0.99, "missing": []}
  ],
  "humanized": true
}
```

> The UI will also show a **JD Fit Score** card **if** a numeric score is provided by the backend (the current API ships coverage metrics; the score is optional and may be hidden in the UI if not provided).

---

## 🔒 Security & Stability Notes

* **No LaTeX macro stripping** on input — your LaTeX is preserved; changes are via targeted, brace-balanced parsers.
* **Sandboxed `pdflatex`**:

  * temp build dir under `data/cache/latex_builds/`
  * `-no-shell-escape`, `-halt-on-error`
  * 90-second timeout per pass (2 passes)
* **Humanize sanitizer** removes any injected preambles/`documentclass`, escapes stray `%`, and keeps only bullet text.
* **Frontend timeouts**: form submit → 3 minutes; backend Humanize calls are bounded with retries and concurrency limits.

---

## 🧩 Customization Pointers

* **Model**: default chat model is `gpt-4o-mini` (change in `api/optimize.py`).
* **Humanize**: tune `MAX_CONCURRENT`, `TIMEOUT_SEC`, and account email in `api/humanize.py`.
* **Skills labeling**: 4 row labels come from a GPT JSON call; invalid returns fall back to defaults.
* **Coverage goals**: tweak target (e.g., 0.95 or 0.99) or max rounds in `refine_resume_to_keyword_coverage(...)`.
* **Smart expand**: adjust `max_total_new`/`max_new_per_block` (keeps 1-page constraint by compiling after each insert).
* **Trim loop**: change `MAX_TRIMS` or match Achievements with fuzzy names.

---

## 🚑 Troubleshooting

* **No PDFs appear** → ensure `pdflatex` is installed and on PATH; test your `.tex` on Overleaf.
* **Timeouts** → long JDs can hit the 3-min client timeout; re-run or disable Humanize to speed up.
* **Humanized PDF missing** → a minimal fallback `.tex` is saved if humanized compile fails; check logs and `data/Job Resumes/`.
* **Skills look generic** → ensure the JD lists concrete skills; extremely vague JDs reduce extraction precision.

---

## 📄 License

MIT — free to use, modify, and distribute.

---

## 🙏 Credits

* Built by **Sri Akash Kadali** (University of Maryland, College Park)
* Stack: **FastAPI · Python · LaTeX · OpenAI API · Humanize API · HTML · JS**

---

## Change Log

* **v1.1.0**

  * Coverage-driven refinement to **≥99%** JD keyword coverage.
  * **Smart expand**: add truthful extra bullets *only if* the PDF remains one page (compile-guarded).
  * GPT-proposed **Skills row labels** (still exactly 4 rows).
  * Preview UI shows **JD Fit Score** card **when provided** by backend.
  * Response JSON now includes **coverage metrics** and **history**.

* **v1.0.0**

  * First public build: end-to-end pipeline, 4-row skills, JD-aware coursework, 3-bullet cap, Achievements trim loop, dual PDF outputs, Windows wrapper.

---
