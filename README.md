# 🧠 HIREX — Job-Aware Resume Optimizer (LaTeX + AIHumanize)

**Author:** Sri Akash Kadali
**Version:** 1.0.0
**Frameworks:** FastAPI · OpenAI · AIHumanize.io · LaTeX · HTML · JS · PyWebview

---

## 🚀 Overview

**HIREX** (High Resume eXpert) is a cross-platform AI tool that rewrites and optimizes LaTeX resumes to match any job description while preserving factual content.
It combines **OpenAI GPT** for JD-aware restructuring and **AIHumanize.io** for tone polishing.

---

## 🧩 Architecture

```
HIREX/
│
├── backend/
│   ├── main.py              → FastAPI + PyWebview launcher
│   ├── api/
│   │   ├── optimize.py      → AI resume optimizer (OpenAI + Humanize)
│   │   ├── debug.py         → Debug log endpoint
│   │   ├── humanize.py      → AIHumanize.io concurrent rewriter
│   │   ├── latex_parse.py   → Raw LaTeX section extractor
│   │   └── render_tex.py    → Final LaTeX sanitizer
│   │
│   └── core/
│       ├── config.py        → Environment, paths, API keys
│       ├── compiler.py      → Safe pdflatex → PDF builder
│       ├── security.py      → Upload validation
│       └── utils.py         → Hashing, logging, helpers
│
├── frontend/
│   ├── index.html           → Upload + JD form
│   ├── preview.html         → Optimized LaTeX viewer
│   ├── about.html, help.html
│   └── static/
│       ├── js/
│       │   ├── util.js, ui.js, main.js, preview.js
│       └── css/app.css
│
├── data/cache/latex_builds  → temporary .tex/.pdf builds
├── resume_template.tex      → base LaTeX template
├── .env                     → secrets (OpenAI + Humanize keys)
└── README.md
```

---

## ⚙️ Backend Setup

### 1️⃣  Environment

```bash
python -m venv venv
source venv/bin/activate  # (Windows: venv\Scripts\activate)
pip install -r requirements.txt
```

### 2️⃣  .env File

Create a `.env` in the root:

```bash
OPENAI_API_KEY=sk-xxxxx
HUMANIZE_API_KEY=Bearer xxxxxx
DEBUG=true
MAX_UPLOAD_MB=5
HIREX_SECRET=hirex-dev-secret
```

### 3️⃣  Launch

**Option A – CLI**

```bash
uvicorn backend.main:app --reload
```

**Option B – Windows App**

```bash
python backend/main.py
```

➡ Opens PyWebview window with Close (✖) button.

Backend available at [http://127.0.0.1:8000](http://127.0.0.1:8000)
Health check → `/health`

---

## 💻 Frontend Usage

1. Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)**.
2. Upload a `.tex` resume and paste the full Job Description.
3. Click **Optimize Resume** → backend calls `/api/optimize`.
4. Wait (2–3 min) for AI + Humanize to complete.
5. View output on **Preview** page.
6. Copy or download the generated `.tex`.

---

## 🔁 Optimization Pipeline

1. **Upload & Validate** — `security.py` ensures safe `.tex`.
2. **OpenAI Rewrite** — `optimize_resume_latex()` keeps everything above EDUCATION intact, rewrites JD-aligned sections.
3. **Humanize Pass** — `humanize_experience_bullets()` sends each bullet to AIHumanize API concurrently (5 threads).
4. **Render & Return** — Clean LaTeX → JSON response (`{"tex_string": ...}`) sent to frontend.
5. **Frontend Preview** — `preview.js` loads from `localStorage`, enables copy/download.

---

## 🔒 Security

* Validates extension (.tex) and size ≤ 5 MB.
* Sandboxed LaTeX build via `pdflatex -no-shell-escape`.
* No persistent storage — temporary files auto-deleted.

---

## 🧠 API Reference

| Endpoint         | Method | Description                                        |
| ---------------- | ------ | -------------------------------------------------- |
| `/api/optimize`  | POST   | Upload LaTeX + JD → returns optimized LaTeX string |
| `/api/debug/log` | POST   | Logs frontend events to console                    |
| `/health`        | GET    | Backend status check                               |

---

## 🧪 Example Request

```bash
curl -X POST "http://127.0.0.1:8000/api/optimize" \
  -F "base_resume_tex=@resume.tex" \
  -F "jd_text=Machine Learning Engineer position requiring AWS and Python"
```

**Response:**

```json
{"tex_string": "\\section{Education} ... \\end{document}"}
```

---

## 🖼️ Frontend Scripts

* **util.js** → fetch helpers, Base64, download, clipboard.
* **ui.js** → animations, global toast, debug logger.
* **main.js** → form upload + call `/api/optimize`.
* **preview.js** → LaTeX viewer + copy/download buttons.

---

## 🧰 Debugging

All major steps print to CMD:

```
[2025-10-11 17:35:12] 🟧 [PIPELINE] Step 1: Reading uploaded file
[2025-10-11 17:35:13] 🟩 [AI] Step 3: Response received from OpenAI
[2025-10-11 17:35:18] ✅ [HUMANIZE] Completed 12 bullets concurrently
```

Frontend logs also reach backend via `/api/debug/log`.

---

## 📦 Output

* Optimized `.tex` downloadable from Preview.
* Optional PDF generation via `compile_latex_safely()` if `pdflatex` installed.

---

## 🧾 License

**MIT License** — free for personal, educational, or open-source use.

---

## ❤️ Credits

Developed by **Sri Akash Kadali**
University of Maryland, College Park
📧 [sriakashkadali@gmail.com](mailto:sriakashkadali@gmail.com)
🔗 [https://github.com/Akash-Kadali](https://github.com/Akash-Kadali)
