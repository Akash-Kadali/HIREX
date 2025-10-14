# HIREX — High Resume eXpert

*A job‑aware LaTeX resume optimizer with an optional "humanize" pass. Built with FastAPI + OpenAI + (optional) AIHumanize, and a minimal HTML/JS frontend. Includes a Windows desktop wrapper via PyWebview.*

---

## ✨ What HIREX Does

* **Reads a LaTeX (.tex) resume** and a **Job Description (JD)**.
* **Extracts the company and role** from the JD using OpenAI.
* **Fills/refreshes “Relevant Coursework”** (JD‑aligned, no duplicates across degrees).
* **Rebuilds the Skills section in exactly 4 compact rows** (labels chosen by GPT, rows built deterministically to avoid bloat).
* **Retargets Experience/Projects bullets** to the JD and **caps each itemize to 3 bullets**.
* If the **compiled PDF exceeds one page**, it **iteratively removes the LAST bullet in Achievements** and compiles/saves after *each* removal (so you get Trim1, Trim2, … files).
* **Optional Humanize step**: rewrites *only* the English inside `\resumeItem{...}` for tone/clarity (no facts added), with a LaTeX‑safety sanitizer.
* **Outputs PDFs** (base + humanized if enabled) and the final LaTeX.

> Target user: LaTeX power‑users who want job‑aware, ATS‑sane tailoring without breaking their macros/template.

---

## 🗂 Repo Layout (key folders)

```text
backend/
  core/
    compiler.py        # pdflatex sandbox wrapper
    config.py          # env + paths + app constants
    security.py        # upload validation (no LaTeX sanitization)
    utils.py           # logging, hashing, helpers
  api/
    optimize.py        # main pipeline & /api/optimize endpoint
    render_tex.py      # safe final LaTeX renderer
    latex_parse.py     # lenient section/bullet extractor (raw‑preserve mode)
    humanize.py        # AIHumanize integration + sanitizer
    debug.py           # (optional) debug routes
frontend/
  index.html           # upload JD + .tex, toggle Humanize, submit
  preview.html         # shows PDFs + final LaTeX, download buttons
  about.html, help.html
  static/js/           # util.js, ui.js, main.js, preview.js
  static/assets/       # icons, logo
  static/css/          # app.css (loaded by HTML)
main.py                # Boot FastAPI + (optional) PyWebview desktop window
```

> Paths and directories are created at startup (e.g., `data/cache`, `data/output`) as configured in `backend/core/config.py`.

---

## ⚙️ Requirements

* **Python** 3.10+
* **LaTeX** distribution with `pdflatex` available in `PATH` (TeX Live/MiKTeX)
* (Optional) **Edge WebView2 / Webview** runtime for the Windows desktop mode
* API keys:

  * `OPENAI_API_KEY` (required for JD parsing, skills/coursework, bullet retargeting)
  * `HUMANIZE_API_KEY` (optional, only if you toggle Humanize)

### Install Python deps

```bash
python -m venv .venv
. .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -U fastapi uvicorn httpx python-dotenv openai pywebview
```

> On Windows, `pywebview` uses Edge (Chromium) by default. If the desktop window fails to open, run the backend only with Uvicorn (see below).

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

> Missing keys are warned in debug mode; Humanize remains entirely optional.

---

## ▶️ How to Run

### A) Windows Desktop App (PyWebview)

```bash
python main.py
```

* Launches FastAPI at `http://127.0.0.1:8000` and opens a desktop window that loads the UI.
* A floating **✖ Close** button cleanly terminates the app.

### B) API + Browser (no desktop wrapper)

```bash
uvicorn main:app --reload
# then open http://127.0.0.1:8000 in your browser
```

> The frontend is served from `/` (`index.html`), with `/preview.html`, `/about.html`, and `/help.html` available. Static assets are mounted at `/static`.

---

## 🌐 Frontend Workflow

1. Open **Home** (`index.html`).
2. Upload your base **`.tex` resume** and **paste the Job Description**.
3. (Optional) Toggle **Apply Humanize AI**.
4. Click **Optimize Resume**.
5. After success, you’re redirected to **Preview** (`preview.html`) where you:

   * View **Original Optimized PDF** and (if enabled) **Humanized PDF**.
   * **Download** PDFs and the **final .tex**.

### Frontend behavior highlights

* `main.js`: posts a multipart form to `/api/optimize`; auto‑determines API base; applies a 3‑minute request timeout; persists results in `localStorage`.
* `preview.js`: renders cached PDFs via object URLs; provides per‑file download buttons; displays the final LaTeX with copy/download actions.
* `util.js`: robust fetch with timeout/AbortController, Base64↔Blob helpers, safe download utilities.
* `ui.js`: global toasts, scroll/focus helpers, connectivity toasts, debug logger to backend.

---

## 🧠 Backend: Endpoints & Pipeline

### Endpoints

* `GET /` → `index.html` (falls back to bundled UI)
* `GET /{page}.html` → serves `about`, `help`, `preview`, etc.
* `GET /static/...` → static assets
* `GET /health` → health check
* `POST /api/optimize` → **main pipeline** (multipart: `base_resume_tex`, `jd_text`, `use_humanize`)
* `POST /api/debug/log` → optional frontend debug logging hook

### Data flow (*.tex + JD → PDFs)

1. **Upload validation**

   * Filename + size checked; only `.tex` allowed.
   * Content decoded to UTF‑8 but otherwise preserved (no macro stripping).

2. **JD parsing (OpenAI)**

   * Extract **`company`** and **`role`** (strict JSON).

3. **Coursework**

   * GPT picks up to 6 JD‑relevant course titles.
   * Fills the first two `Relevant Coursework:` lines **without duplicates** (across degrees), up to 6 per line.

4. **Skills (4 rows)**

   * GPT extracts `jd_keywords`, `requirements`, `related`.
   * Tokens are canonicalized, deduped, and lightly pruned (JD items **protected** from pruning).
   * Rows built deterministically and **GPT proposes 4 concise labels** → rendered as a compact 4‑row table.

5. **Experience/Projects bullets**

   * For each `\resumeItemListStart ... \resumeItemListEnd` block, GPT picks **the best 3 bullets** aligned to the JD and rewrites them in concise, past‑tense sentences (no invention).
   * A safety pass **enforces ≤ 3 bullets per itemize**.

6. **Compile PDFs**

   * LaTeX is post‑processed to remove code fences and ensure `\end{document}`.
   * A **sandboxed `pdflatex`** run (2 passes) compiles to PDF (no shell escape, temp dir, 90s timeout). If unavailable, compilation is skipped gracefully.

7. **One‑page guardrail (Achievements trimming)**

   * If the base PDF is >1 page, the pipeline **removes the last bullet from an Achievements‑like section**, recompiles, and **saves each TrimN PDF**.
   * Humanized variant mirrors the same removal and saves TrimN_Humanized as well (or a minimal fallback PDF if LaTeX fails post‑humanize).

8. **Optional Humanize**

   * Only the text inside `\resumeItem{...}` is sent to AIHumanize in parallel (bounded concurrency, retry).
   * A strict sanitizer removes any preamble/`\usepackage`/`\documentclass` the service might inject and escapes stray `%`.

9. **Outputs**

   * JSON returns: final LaTeX (`tex_string`), Base64 PDFs (`pdf_base64`, optionally `pdf_base64_humanized`), `company_name`, `role`, and all **saved file system paths**.
   * Files are stored under `data/Job Resumes/` with names like `Sri_Akash_Kadali_Resume_{Company}_{Role}.pdf`, plus trims.

---

## 📦 Output Files & Naming

All PDFs are written to:

```
data/Job Resumes/
  Sri_Akash_Kadali_Resume_{Company}_{Role}.pdf
  Sri_Akash_Kadali_Resume_{Company}_{Role}_Humanized.pdf
  Sri_Akash_Kadali_Resume_{Company}_{Role}_Trim1.pdf
  Sri_Akash_Kadali_Resume_{Company}_{Role}_Trim1_Humanized.pdf
  ...
```

The response also includes an array of absolute paths (`saved_paths`) for convenience.

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
  "pdf_base64": "JVBERi0xLjQK...",                   // base optimized PDF
  "pdf_base64_humanized": "JVBERi0xLjQK...",            // optional
  "company_name": "...",
  "role": "...",
  "saved_paths": ["/abs/path/Trim1.pdf", "..."]
}
```

---

## 🔒 Security & Stability Notes

* **No LaTeX macro stripping on input** — your LaTeX is preserved. Only the *specific* sections are changed via targeted regex + brace‑balanced parsers.
* **pdflatex sandboxing** —

  * temp build dir under `data/cache/latex_builds/`
  * `-no-shell-escape` and `-halt-on-error`
  * 90‑second timeout per compilation
* **Humanize sanitizer** prevents injected preambles/`\usepackage`/code fences and escapes stray `%` to avoid accidental comments.
* **Network timeouts**: frontend form → 3 min; backend humanize per bullet → 15–20s with retries and concurrency limit.

---

## 🧩 Customization Pointers

* **Model**: default GPT model is `gpt-4o-mini` (chat‑completions). Change in `api/optimize.py`.
* **Humanize**: `AIHUMANIZE_MODE`, `MAX_CONCURRENT`, `TIMEOUT_SEC`, and the registered email can be tuned in `api/humanize.py`.
* **Skills labeling**: the 4 row labels come from a GPT JSON call; if it fails validation, the renderer falls back to defaults.
* **Trimming loop**: increase/decrease `MAX_TRIMS` as needed; achievements section is matched by exact or fuzzy header names.
* **File size limits**: `MAX_UPLOAD_MB` in `.env`.

---

## 🚑 Troubleshooting

* **No PDFs appear**: ensure `pdflatex` is installed and on PATH. Try compiling the LaTeX on Overleaf to confirm the template is valid.
* **Timeouts**: very long JDs or slow networks can trigger the 3‑minute client timeout. Re‑run or disable Humanize to speed up.
* **Humanized PDF missing**: the pipeline saves a fallback minimal PDF if the humanized LaTeX fails. Check `data/Job Resumes/` and the console logs.
* **Skills not updating**: make sure the JD actually lists concrete skills; generic phrases may be pruned.

---

## 📄 License

MIT — free to use, modify, and distribute.

---

## 🙏 Credits

* Built by **Sri Akash Kadali** (University of Maryland, College Park)
* Stack: **FastAPI · Python · LaTeX · OpenAI API · Humanize API · HTML · JS**

---

## Change Log

* **v1.0.0**

  * Initial public build: end‑to‑end pipeline, 4‑row skills, JD‑aware coursework, 3‑bullet cap, achievements trim loop, dual PDF outputs, Windows wrapper.
