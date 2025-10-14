"""
HIREX • api/optimize.py
Job-Aware Resume Optimizer (OpenAI + Optional AIHumanize.io)
• Extracts Company & Role from JD (via GPT).
• Builds an exhaustive, JD-aligned Skills section (GPT only — no local guesses) and renders it in **exactly 4 compact rows**.
• Fills both “Relevant Coursework” lines from JD (GPT only) — **no duplicates across degrees; prioritize JD-related**.
• Limits each itemize under EXPERIENCE/PROJECTS to 3 bullets (per role), with GPT retargeting.
• If compiled PDF exceeds 1 page, iteratively removes the LAST bullet from **Achievements** and,
  after EVERY removal, tries to compile & **save both PDFs** (base + humanized).
• Humanizes ONLY the English inside \resumeItem{...} (keeps LaTeX structure).
• Compiles original + (optional) humanized PDFs; falls back to minimal PDF if needed.
Author: Sri Akash Kadali
"""

import base64
import re
import json
import httpx
import asyncio
from typing import List, Tuple, Dict, Iterable, Optional, Set
from fastapi import APIRouter, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI

from backend.core import config
from backend.core.security import secure_tex_input
from backend.core.compiler import compile_latex_safely
from api.render_tex import render_final_tex
from backend.core.utils import log_event, safe_filename

router = APIRouter()
openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)

# ============================================================
# 🔒 LaTeX-safe utils
# ============================================================

LATEX_ESC = {
    "#": r"\#",
    "%": r"\%",
    "$": r"\$",
    "&": r"\&",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
}
UNICODE_NORM = {
    "–": "-", "—": "-", "−": "-",
    "•": "-", "·": "-", "●": "-",
    "→": "->", "⇒": "=>", "↔": "<->",
    "×": "x", "°": " degrees ",
    "’": "'", "‘": "'", "“": '"', "”": '"',
    "\u00A0": " ", "\uf0b7": "-", "\x95": "-",
}

def latex_escape_text(s: str) -> str:
    for a, b in UNICODE_NORM.items():
        s = s.replace(a, b)
    specials = ['%', '$', '&', '_', '#', '{', '}']
    for ch in specials:
        s = re.sub(rf'(?<!\\){re.escape(ch)}', LATEX_ESC[ch], s)
    s = re.sub(r'(?<!\\)\^', r'\^{}', s)
    s = re.sub(r"[ \t]+", " ", s).strip()
    return s

def strip_all_macros_keep_text(s: str) -> str:
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"\\[a-zA-Z]+\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\[a-zA-Z]+", "", s)
    s = s.replace("{", "").replace("}", "")
    for a, b in UNICODE_NORM.items():
        s = s.replace(a, b)
    return s.strip()

def sanitize_for_minimal(b: str) -> str:
    b = strip_all_macros_keep_text(b)
    b = latex_escape_text(b)
    return b or "(content removed)"

# ============================================================
# 🧰 Balanced \resumeItem parser (handles nested braces)
# ============================================================

def find_resume_items(block: str) -> List[Tuple[int,int,int,int]]:
    out = []
    i = 0
    needle = r"\resumeItem{"
    while True:
        i = block.find(needle, i)
        if i < 0:
            break
        open_brace = i + len(r"\resumeItem")
        if open_brace >= len(block) or block[open_brace] != "{":
            i += 1
            continue
        depth, j = 0, open_brace
        while j < len(block):
            ch = block[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    close_brace = j
                    out.append((i, open_brace, close_brace, close_brace + 1))
                    i = close_brace + 1
                    break
            j += 1
        else:
            break
    return out

def replace_resume_items(block: str, replacements: List[str]) -> str:
    items = find_resume_items(block)
    if not items:
        return block
    if len(replacements) < len(items):
        replacements = replacements + [None] * (len(items) - len(replacements))
    out, last = [], 0
    for (start, open_b, close_b, end), newtxt in zip(items, replacements):
        out.append(block[last:open_b + 1])
        if newtxt is None:
            out.append(block[open_b + 1:close_b])
        else:
            out.append(newtxt)
        out.append(block[close_b:end])
        last = end
    out.append(block[last:])
    return "".join(out)

# ============================================================
# 🔎 Section matchers (supports \section and \section*)
# ============================================================

def section_rx(name: str) -> re.Pattern:
    return re.compile(
        rf"(\\section\*?\{{\s*{re.escape(name)}\s*\}}[\s\S]*?)(?=\\section\*?\{{|\\end\{{document\}})",
        re.IGNORECASE
    )

# Also a generic section header for fuzzy search
SECTION_HEADER_RE = re.compile(r"\\section\*?\{\s*([^\}]*)\s*\}", re.IGNORECASE)

# ============================================================
# 🧠 GPT helpers (strict JSON)
# ============================================================

def _json_from_text(text: str, default):
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return default
    try:
        return json.loads(m.group(0))
    except Exception:
        return default

async def gpt_json(prompt: str, temperature: float = 0.0) -> dict:
    resp = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return _json_from_text(resp.choices[0].message.content or "{}", {})

# ============================================================
# 🧠 JD → company + role (GPT only)
# ============================================================

async def extract_company_role(jd_text: str) -> Tuple[str, str]:
    company_role_example = '{"company":"…","role":"…"}'
    prompt = (
        "Return STRICT JSON:\n"
        f"{company_role_example}\n"
        "Use the official company short name and the exact job title.\n"
        "JD:\n"
        f"{jd_text}"
    )
    try:
        data = await gpt_json(prompt, temperature=0.0)
        company = data.get("company", "Company")
        role = data.get("role", "Role")
        log_event(f"🧠 [JD PARSE] Extracted → company={company}, role={role}")
        return company, role
    except Exception as e:
        log_event(f"⚠️ [JD PARSE] Failed: {e}")
        return "Company", "Role"

# ============================================================
# 🧮 Canonicalization + keep JD requirements
# ============================================================

CANON_SYNONYMS = {
    "hf transformers": "Hugging Face Transformers",
    "transformers": "Hugging Face Transformers",
    "pytorch lightning": "PyTorch",
    "sklearn": "scikit-learn",
    "big query": "BigQuery",
    "google bigquery": "BigQuery",
    "ms sql": "SQL",
    "mysql": "SQL",
    "postgres": "SQL",
    "postgresql": "SQL",
    "bert": "BERT",
    "large language models": "LLMs",
    "llm": "LLMs",
    "llms": "LLMs",
    "gen ai": "Generative AI",
    "generative ai": "Generative AI",
    "ci cd": "CI/CD",
    "k8s": "Kubernetes",
    "g cloud": "GCP",
    "microsoft excel": "Excel",
    # Web3 / blockchain
    "typescript.js": "TypeScript",
    "typesript.js": "TypeScript",
    "web3js": "Web3.js",
    "web3.js": "Web3.js",
    "ethersjs": "Ethers.js",
    "ethers.js": "Ethers.js",
    "smart contracts": "Smart contracts",
}

LANG_MAP = {
    "professional proficiency in english": "English (professional)",
    "english proficiency": "English (professional)",
    "english": "English (professional)",
    "professional proficiency in chinese": "Chinese (professional)",
    "chinese proficiency": "Chinese (professional)",
    "chinese": "Chinese (professional)",
}

def _canon_phrase_shrink(s: str) -> str:
    ls = s.lower().strip()
    m = re.match(r"(basic|foundational)\s+(knowledge|understanding)\s+of\s+(.+)", ls)
    if m: return m.group(3)
    m = re.match(r"(strong|keen)\s+(interest|curiosity)\s+(in|for)\s+(.+)", ls)
    if m: return m.group(4)
    m = re.match(r"(basic|good)\s+(grasp|idea)\s+of\s+(.+)", ls)
    if m: return m.group(3)
    return s

def canonicalize_token(s: str) -> str:
    s = _canon_phrase_shrink(s)
    ls = s.lower().strip()
    s = CANON_SYNONYMS.get(ls, s)
    s = LANG_MAP.get(ls, s)
    s = s.strip(" ,.;:/")
    if ls in {"typescript"}: s = "TypeScript"
    if ls in {"solidity"}: s = "Solidity"
    if ls in {"rust"}: s = "Rust"
    if ls in {"javascript"}: s = "JavaScript"
    return s

def prune_and_compact_skills(skills: List[str], protected: Set[str]) -> List[str]:
    filler_patterns = [
        r"\bability to\b", r"\bexperience with\b", r"\bfamiliarity with\b",
        r"\bstrong\b", r"\bexcellent\b", r"\bproficiency\b"
    ]
    out, seen = [], set()
    prot_lower = {p.lower() for p in protected}
    for raw in skills:
        s = canonicalize_token(raw)
        ls = s.lower()
        if ls not in prot_lower and any(re.search(p, ls) for p in filler_patterns):
            continue
        key = s.lower()
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out

# ============================================================
# 🎯 JD → Skills (JD keywords + JD requirements + GPT-related)
# ============================================================

async def extract_skills_gpt(jd_text: str) -> Tuple[List[str], Set[str]]:
    # Keep the JSON example outside the f-string to avoid brace parsing errors
    json_example = (
        '{\n'
        '  "jd_keywords": ["Python","SQL","Power BI","Tableau","Excel","Data Visualization","Data Analysis","Data Management",\n'
        '                  "GIS","Annotation","Labeling","Data Profiling","Solidity","TypeScript","Web3","Ethereum",\n'
        '                  "OpenZeppelin","Hardhat","Foundry","Ethers.js","Web3.js","Smart contracts","Tokenomics","DAO frameworks","Gamification"],\n'
        '  "requirements": ["Python","SQL","Annotation","Labeling","Solidity","Smart contracts"],\n'
        '  "related":     ["Pandas","NumPy","scikit-learn","NestJS","Node.js","Truffle"]\n'
        '}\n'
    )

    prompt = (
        "Extract skill tokens for this job in THREE sets.\n\n"
        '1) "jd_keywords": ONLY concrete skills that appear explicitly in the JD (languages, libraries, frameworks,\n'
        "   platforms, cloud providers, databases/warehouses, orchestration/MLOps, BI/viz tools, ML topics, LLM eval tasks).\n"
        '2) "requirements": the MUST-HAVE skills/requirements the JD lists (including task-type items such as annotation,\n'
        "   labeling, evaluation, data collection, prompt engineering, translation/transcription, etc.) — keep their exact\n"
        "   canonical names as short tokens.\n"
        '3) "related": closely related/adjacent skills that are reasonable alternates or companions.\n\n'
        "Return STRICT JSON ONLY:\n"
        f"{json_example}\n"
        "Rules:\n"
        "- Deduplicate inside each list.\n"
        "- Use short canonical tokens (no sentences).\n"
        '- Include language proficiency tokens if listed (e.g., "English (professional)").\n'
        "JD:\n"
        f"{jd_text}"
    )
    try:
        data = await gpt_json(prompt, temperature=0.0)
        jd_kw = data.get("jd_keywords", []) or []
        reqs = data.get("requirements", []) or []
        rel  = data.get("related", []) or []

        combined, seen = [], set()
        for lst in (jd_kw, reqs, rel):
            for s in lst:
                s = re.sub(r"[^\w\-\+\.#\/ \(\)]", "", str(s)).strip()
                if not s:
                    continue
                s = canonicalize_token(s)
                k = s.lower()
                if k not in seen:
                    seen.add(k)
                    combined.append(s)

        protected = {canonicalize_token(s).lower() for s in (jd_kw + reqs)}
        log_event(f"💡 [JD SKILLS] jd={len(jd_kw)} req={len(reqs)} rel={len(rel)} → combined={len(combined)}")
        return combined, protected
    except Exception as e:
        log_event(f"⚠️ [JD SKILLS] Failed: {e}")
        return [], set()

# ============================================================
# 🎓 JD → Relevant Coursework (GPT only)
# ============================================================

async def extract_coursework_gpt(jd_text: str, max_courses: int = 6) -> List[str]:
    courses_json_example = '{"courses":["Machine Learning","Time Series Analysis","Financial Analytics"]}'
    prompt = (
        f"From the JD, choose up to {max_courses} highly relevant university courses "
        "that best signal fit. Return STRICT JSON:\n"
        f"{courses_json_example}\n"
        "Use standard course titles (concise).\n"
        "JD:\n"
        f"{jd_text}"
    )
    try:
        data = await gpt_json(prompt, temperature=0.0)
        courses = data.get("courses", []) or []
        out, seen = [], set()
        for c in courses:
            c = re.sub(r"\s+", " ", str(c)).strip()
            if not c:
                continue
            k = c.lower()
            if k not in seen:
                seen.add(k)
                out.append(c)
            if len(out) >= max_courses:
                break
        log_event(f"🎓 [JD COURSES] GPT returned {len(out)} courses.")
        return out
    except Exception as e:
        log_event(f"⚠️ [JD COURSES] Failed: {e}")
        return []

# ============================================================
# 🧱 Skills rendering — EXACTLY 4 LINES (Web3-aware + GPT labels)
# ============================================================

def categorize(sk: Iterable[str]) -> Dict[str, List[str]]:
    cat = {k: [] for k in [
        "Programming", "Data & ML", "Frameworks", "Data Engineering", "Cloud & DevOps",
        "Visualization", "Tools", "Math & Stats", "Soft Skills"
    ]}
    for s in sk:
        t = canonicalize_token(s)
        ls = t.lower()
        def add(bucket): cat[bucket].append(t)

        if ls in {
            "python","r","sql","c++","java","scala","go","matlab","javascript","typescript",
            "rust","solidity","c#","swift","php","kotlin"
        }:
            add("Programming"); continue

        if any(x in ls for x in [
            "pandas","numpy","scipy","scikit","tensor","keras","torch","xgboost","lightgbm",
            "transformers","spacy","catboost","opencv","bert","llms","generative ai","prompt engineering"
        ]):
            add("Data & ML"); continue
        if any(x in ls for x in ["machine learning","deep learning","nlp","vision","time series","recomm"]):
            add("Data & ML"); continue

        if any(x in ls for x in [
            "react","angular","vue","next.js","nuxt","node.js","express","nestjs","django","flask","fastapi",
            "spring",".net","rails","laravel","truffle","hardhat","foundry","openzeppelin","web3.js","ethers.js"
        ]):
            add("Frameworks"); continue

        if any(x in ls for x in [
            "spark","hadoop","airflow","dbt","kafka","snowflake","databricks","bigquery","redshift",
            "etl","warehouse","pipeline"
        ]):
            add("Data Engineering"); continue

        if any(x in ls for x in ["aws","gcp","azure","docker","kuber","kubernetes","ci/cd","mlops","devops","cloud"]):
            add("Cloud & DevOps"); continue

        if any(x in ls for x in [
            "power bi","tableau","matplotlib","seaborn","plotly","viz","visual","excel","gis",
            "data visualization","data analysis","data management","profiling","data profiling"
        ]):
            add("Visualization"); continue

        if any(x in ls for x in [
            "git","linux","bash","unix","jira","mlflow","annotation","labeling","relevance evaluation",
            "preference ranking","summarization","translation","transcription","response generation",
            "response rewrite","similarity evaluation","data collection","content evaluation",
            "prompt","grading","identification","ranking","ethereum","web3","smart contracts","tokenomics",
            "dao","dao frameworks","gamification","crypto","cryptography"
        ]):
            add("Tools"); continue

        if any(x in ls for x in ["english (professional)","chinese (professional)","english","chinese"]):
            add("Soft Skills"); continue

        if any(x in ls for x in ["stat","probab","hypothesis","linear algebra","optimization"]):
            add("Math & Stats"); continue

        add("Tools")

    for k in cat:
        seen, ded = set(), []
        for v in cat[k]:
            key = v.lower()
            if key not in seen:
                seen.add(key); ded.append(v)
        cat[k] = ded
    return cat

def _split_half(vals: List[str]) -> Tuple[List[str], List[str]]:
    if not vals: return [], []
    mid = (len(vals) + 1) // 2
    return vals[:mid], vals[mid:]

def _build_skill_rows(cat: Dict[str, List[str]]) -> List[Tuple[str, List[str]]]:
    """
    Build 4 rows (label, items) using packing logic; GPT may relabel later.
    """
    prog = cat.get("Programming", [])
    ml   = cat.get("Data & ML", [])
    fw   = cat.get("Frameworks", [])
    engd = (cat.get("Data Engineering", []) or []) + (cat.get("Cloud & DevOps", []) or [])
    vizt = (cat.get("Visualization", []) or []) + (cat.get("Tools", []) or [])
    other= (cat.get("Math & Stats", []) or []) + (cat.get("Soft Skills", []) or [])

    rows: List[Tuple[str, List[str]]] = []

    # Row 1
    if prog and all(p.lower() == "sql" for p in prog):
        rows.append(("SQL & Querying", prog))
    else:
        rows.append(("Programming", prog))

    # Row 2
    if ml:
        rows.append(("Machine Learning", ml)); ml = []
    elif fw:
        rows.append(("Frameworks & Libraries", fw)); fw = []
    elif vizt:
        half, vizt = _split_half(vizt); rows.append(("Business Intelligence & Analytics", half))
    elif other:
        half, other = _split_half(other); rows.append(("Other Requirements", half))
    else:
        rows.append(("Frameworks & Libraries", []))

    # Row 3
    if engd:
        rows.append(("Data Engineering & DevOps", engd)); engd = []
    elif fw:
        half, fw = _split_half(fw); rows.append(("Frameworks & Libraries", half))
    elif vizt:
        half, vizt = _split_half(vizt); rows.append(("Tools & Platforms", half))
    elif other:
        half, other = _split_half(other); rows.append(("Other Requirements", half))
    else:
        rows.append(("Data Engineering & DevOps", []))

    # Row 4
    tail = (fw or []) + (vizt or []) + (other or []) + (ml or []) + (engd or [])
    soft_like = [v for v in other]
    row4_label = "Soft Skills & Other" if tail and len(soft_like) >= max(1, len(tail)//2) else "Additional Tools & Skills"
    rows.append((row4_label, tail))
    return rows[:4]

def _sample_list(vals: List[str], k: int = 10) -> List[str]:
    return vals[:k]

def _clean_label(s: str) -> str:
    s = strip_all_macros_keep_text(str(s))
    s = re.sub(r"[^A-Za-z0-9&\/\-\+\.\s]", "", s).strip()
    s = re.sub(r"\s+", " ", s)
    return " ".join(w.capitalize() if not re.match(r"[&/]", w) else w for w in s.split()).strip()

def _valid_labels(labels: List[str]) -> bool:
    if not isinstance(labels, list) or len(labels) != 4:
        return False
    cleaned = [_clean_label(x) for x in labels]
    if any(len(x) == 0 or len(x) > 32 for x in cleaned):
        return False
    if len(set(x.lower() for x in cleaned)) != 4:
        return False
    return True

async def propose_skill_labels_gpt(rows: List[Tuple[str, List[str]]]) -> List[str]:
    """
    Ask GPT for 4 concise, non-duplicate subheadings and reconfirm if needed.
    Returns 4 labels (cleaned). Falls back to defaults on failure.
    """
    defaults = [r[0] for r in rows]
    rows_preview = [
        {"default_label": r[0], "samples": _sample_list(r[1], 10)}
        for r in rows
    ]
    labels_example = '{"labels":["Programming","Machine Learning","Data Engineering & DevOps","Additional Tools & Skills"]}'

    prompt = (
        "You will name 4 Skills table subheadings for a resume.\n"
        "Constraints:\n"
        f"- Return STRICT JSON only: {labels_example}\n"
        "- EXACTLY 4 labels, one for each row in order.\n"
        "- Each label: 1–32 chars, Title Case, no trailing punctuation, allow only letters, numbers, spaces, &, /, +, -, .\n"
        "- No duplicates. Be specific and meaningful based on the row contents.\n\n"
        "Rows (with default labels and sample items):\n"
        f"{json.dumps(rows_preview, ensure_ascii=False, indent=2)}\n"
    )
    data = await gpt_json(prompt, temperature=0.0)
    labels = data.get("labels", []) if isinstance(data, dict) else []
    labels = [_clean_label(x) for x in labels]

    if not _valid_labels(labels):
        reconfirm = (
            f"You returned: {json.dumps(labels, ensure_ascii=False)}.\n"
            "Fix to meet ALL constraints and the row order. Return STRICT JSON only:\n"
            '{{"labels":["...", "...", "...", "..."]}}\n'
            "Constraints:\n"
            "- EXACTLY 4 labels (row order unchanged).\n"
            "- 1–32 chars each, Title Case, no trailing punctuation, allowed chars: letters, numbers, spaces, &, /, +, -, .\n"
            "- No duplicates. Be specific, based on the items.\n"
            "Rows again:\n"
            f"{json.dumps(rows_preview, ensure_ascii=False, indent=2)}\n"
        )
        data2 = await gpt_json(reconfirm, temperature=0.0)
        labels2 = data2.get("labels", []) if isinstance(data2, dict) else []
        labels2 = [_clean_label(x) for x in labels2]
        if _valid_labels(labels2):
            log_event(f"🏷️ [SKILLS LABELS] {labels2}")
            return labels2
        log_event(f"🏷️ [SKILLS LABELS] Fallback to defaults after invalid reconfirm.")
        return defaults

    log_event(f"🏷️ [SKILLS LABELS] {labels}")
    return labels

async def render_skills_block_with_gpt(cat: Dict[str, List[str]]) -> str:
    rows = _build_skill_rows(cat)
    try:
        labels = await propose_skill_labels_gpt(rows)
    except Exception as e:
        log_event(f"⚠️ [SKILLS LABELS] GPT error, using defaults: {e}")
        labels = [r[0] for r in rows]

    lines = [
        r"\section{Skills}",
        r"\begin{itemize}[leftmargin=0.15in, label={}]",
        r"  \item \small{",
        r"  \begin{tabularx}{\linewidth}{@{} l X @{}}"
    ]
    for i, (label, vals) in enumerate(zip(labels, [r[1] for r in rows])):
        content = ", ".join(latex_escape_text(v) for v in vals)
        suffix = " \\\\" if i < 3 else ""
        lines.append(f"  \\textbf{{{latex_escape_text(label)}:}} & {content}{suffix}")
    lines += [
        r"  \end{tabularx}",
        r"  }",
        r"\end{itemize}",
    ]
    return "\n".join(lines)

# (Backup non-GPT label renderer)
def render_skills_block(cat: Dict[str, List[str]]) -> str:
    prog = cat.get("Programming", [])
    ml   = cat.get("Data & ML", [])
    fw   = cat.get("Frameworks", [])
    engd = (cat.get("Data Engineering", []) or []) + (cat.get("Cloud & DevOps", []) or [])
    vizt = (cat.get("Visualization", []) or []) + (cat.get("Tools", []) or [])
    other= (cat.get("Math & Stats", []) or []) + (cat.get("Soft Skills", []) or [])

    rows: List[Tuple[str, List[str]]] = []
    rows.append(("Programming", prog))

    if ml:
        rows.append(("AI/ML Frameworks", ml)); ml = []
    elif fw:
        rows.append(("Frameworks & Libraries", fw)); fw = []
    elif vizt:
        half, vizt = _split_half(vizt); rows.append(("Visualization & Tools", half))
    elif other:
        half, other = _split_half(other); rows.append(("Other Requirements", half))
    else:
        rows.append(("Frameworks & Libraries", []))

    if engd:
        rows.append(("Data Engineering & DevOps", engd)); engd = []
    elif fw:
        half, fw = _split_half(fw); rows.append(("Frameworks & Libraries", half))
    elif vizt:
        half, vizt = _split_half(vizt); rows.append(("Visualization & Tools", half))
    elif other:
        half, other = _split_half(other); rows.append(("Other Requirements", half))
    else:
        rows.append(("Data Engineering & DevOps", []))

    tail = (fw or []) + (vizt or []) + (other or []) + (ml or []) + (engd or [])
    rows.append(("Visualization & Tools & Other Requirements", tail))

    lines = [
        r"\section{Skills}",
        r"\begin{itemize}[leftmargin=0.15in, label={}]",
        r"  \item \small{",
        r"  \begin{tabularx}{\linewidth}{@{} l X @{}}"
    ]
    for i, (label, vals) in enumerate(rows):
        content = ", ".join(latex_escape_text(v) for v in vals)
        suffix = " \\\\" if i < len(rows) - 1 else ""
        lines.append(f"  \\textbf{{{latex_escape_text(label)}:}} & {content}{suffix}")
    lines += [
        r"  \end{tabularx}",
        r"  }",
        r"\end{itemize}",
    ]
    return "\n".join(lines)

# === Async, GPT-aware replacement ===
async def replace_skills_section(body_tex: str, skills: List[str]) -> str:
    new_block = await render_skills_block_with_gpt(categorize(skills))
    pattern = re.compile(r"(\\section\*?\{Skills\}[\s\S]*?)(?=%-----------|\\section\*?\{|\\end\{document\})",
                         re.IGNORECASE)
    if re.search(pattern, body_tex):
        return re.sub(pattern, lambda _m: new_block + "\n", body_tex)
    m = re.search(r"%-----------TECHNICAL SKILLS-----------", body_tex, re.IGNORECASE)
    if m:
        idx = m.end()
        return body_tex[:idx] + "\n" + new_block + "\n" + body_tex[idx:]
    return "%-----------TECHNICAL SKILLS-----------\n" + new_block + "\n" + body_tex

# ============================================================
# 🎓 Replace “Relevant Coursework” lines using GPT list — distinct, JD-first
# ============================================================

def replace_relevant_coursework_distinct(body_tex: str, courses: List[str], max_per_line: int = 6) -> str:
    """
    Finds all lines like: \item \textbf{Relevant Coursework:} ...
    and fills them from the JD-derived course list WITHOUT repetition across lines.
    Splits the unique courses across the first two occurrences (most resumes have 2 degrees).
    """
    # De-duplicate while preserving order
    seen, uniq = set(), []
    for c in courses:
        c = re.sub(r"\s+", " ", str(c)).strip()
        if not c:
            continue
        lc = c.lower()
        if lc not in seen:
            seen.add(lc)
            uniq.append(c)

    line_pat = re.compile(r"(\\item\s*\\textbf\{Relevant Coursework:\})([^\n]*)")
    matches = list(line_pat.finditer(body_tex))
    if not matches:
        return body_tex

    # Prepare chunking for the first two lines; distribute roughly half/half and cap per line
    chunks: List[List[str]] = []
    if len(matches) == 1:
        chunks.append(uniq[:max_per_line])
    else:
        n = len(uniq)
        split_idx = (n + 1) // 2  # ceil-half
        first = uniq[:split_idx][:max_per_line]
        second = uniq[split_idx:split_idx + max_per_line]
        # Ensure second line isn't empty if we have at least 2 total
        if not second and n >= 2 and len(first) >= 2:
            second = [first.pop()]  # move one over
        chunks = [first, second]

        # If there are more "Relevant Coursework" lines, keep filling with any remaining (rare)
        rem = uniq[split_idx + len(chunks[1]) if len(chunks) > 1 else len(chunks[0]):]
        while len(chunks) < len(matches) and rem:
            chunks.append(rem[:max_per_line])
            rem = rem[max_per_line:]

    # Rebuild the body with replacements (escape LaTeX)
    out, last = [], 0
    for i, m in enumerate(matches):
        out.append(body_tex[last:m.start()])
        if i < len(chunks):
            payload = ", ".join(latex_escape_text(x) for x in chunks[i])
            out.append(m.group(1) + " " + payload)
        else:
            # No replacement chunk -> keep original line untouched
            out.append(m.group(0))
        last = m.end()
    out.append(body_tex[last:])
    return "".join(out)

# ============================================================
# ✂️ Limit bullets PER itemize (≤3)
# ============================================================

def trim_itemize_to_three(section_text: str) -> str:
    out, i = [], 0
    start_tag, end_tag = r"\resumeItemListStart", r"\resumeItemListEnd"
    while True:
        a = section_text.find(start_tag, i)
        if a < 0:
            out.append(section_text[i:])
            break
        b = section_text.find(end_tag, a)
        if b < 0:
            out.append(section_text[i:])
            break
        out.append(section_text[i:a])
        block = section_text[a:b]
        items = find_resume_items(block)
        if len(items) > 3:
            keep = items[:3]
            buf, pos = [], 0
            for s, _, _, e in keep:
                buf.append(block[pos:s]); buf.append(block[s:e]); pos = e
            buf.append(block[pos:])
            block = "".join(buf)
            log_event(f"✂️ Trimmed {len(items)}→3 bullets in one itemize.")
        out.append(block); out.append(section_text[b: b + len(end_tag)])
        i = b + len(end_tag)
    return "".join(out)

def limit_experience_bullets(tex_content: str) -> str:
    for sec_name in ["Experience", "Projects"]:
        pat = section_rx(sec_name)
        out, pos = [], 0
        for m in pat.finditer(tex_content):
            out.append(tex_content[pos:m.start()])
            section = m.group(1)
            section = trim_itemize_to_three(section)
            out.append(section)
            pos = m.end()
        out.append(tex_content[pos:])
        tex_content = "".join(out)
    return tex_content

# ============================================================
# 💼 GPT: pick best 3 bullets per role & rewrite for the job
# ============================================================

async def gpt_select_and_rewrite_bullets(jd_text: str, bullets: List[str]) -> List[str]:
    plain = [strip_all_macros_keep_text(b) for b in bullets]
    bullets_json_example = '{"bullets":["...","...","..."]}'
    prompt = (
        "You are optimizing resume bullets for THIS job.\n"
        f"Return STRICT JSON: {bullets_json_example} with EXACTLY 3 items.\n"
        "Rules:\n"
        "- Choose the 3 most relevant bullets for THIS JD.\n"
        "- Keep truthful content; do NOT invent projects or fake metrics.\n"
        "- Rewrite each bullet as ONE concise, past-tense sentence with impact metrics when available.\n"
        "- Avoid first-person; avoid fluff; keep domain wording aligned to the JD.\n\n"
        "JOB DESCRIPTION:\n"
        f"{jd_text}\n\n"
        "CANDIDATE BULLETS:\n"
        + "\n".join(f"- {t}" for t in plain)
    )
    data = await gpt_json(prompt, temperature=0.2)
    out = data.get("bullets", []) or []
    out = [latex_escape_text(s) for s in out if str(s).strip()]
    if len(out) < 3:
        for t in plain:
            if len(out) >= 3:
                break
            out.append(latex_escape_text(t))
    return out[:3]

async def _retarget_one_section(section_text: str, jd_text: str) -> str:
    s_tag, e_tag = r"\resumeItemListStart", r"\resumeItemListEnd"
    out, i = [], 0
    while True:
        a = section_text.find(s_tag, i)
        if a < 0:
            out.append(section_text[i:])
            break
        b = section_text.find(e_tag, a)
        if b < 0:
            out.append(section_text[i:])
            break

        out.append(section_text[i:a])
        block = section_text[a:b]

        items = find_resume_items(block)
        if items:
            originals = [block[op + 1:cl] for (_s, op, cl, _e) in items]
            bullets_new = await gpt_select_and_rewrite_bullets(jd_text, originals)

            def _remove_all_items(btxt: str) -> str:
                res, last = [], 0
                for (s, _, _, e) in find_resume_items(btxt):
                    res.append(btxt[last:s]); last = e
                res.append(btxt[last:])
                return "".join(res)

            block_no_items = _remove_all_items(block)
            insert_at = block_no_items.find(s_tag) + len(s_tag)
            inject = "".join(f"\n  \\resumeItem{{{t}}}" for t in bullets_new)
            block = block_no_items[:insert_at] + inject + block_no_items[insert_at:]

        out.append(block)
        out.append(section_text[b:b + len(e_tag)])
        i = b + len(e_tag)
    return "".join(out)

async def retarget_experience_sections_with_gpt(tex_content: str, jd_text: str) -> str:
    for sec_name in ["Experience", "Projects"]:
        pat = section_rx(sec_name)
        out, pos = [], 0
        for m in pat.finditer(tex_content):
            out.append(tex_content[pos:m.start()])
            section = m.group(1)
            section = await _retarget_one_section(section, jd_text)
            out.append(section)
            pos = m.end()
        out.append(tex_content[pos:])
        tex_content = "".join(out)
    return tex_content

# ============================================================
# 📄 PDF page-count helper
# ============================================================

def _pdf_page_count(pdf_bytes: Optional[bytes]) -> int:
    if not pdf_bytes:
        return 0
    # Count /Type /Page objects (avoid /Pages)
    return len(re.findall(rb"/Type\s*/Page\b", pdf_bytes))

# ============================================================
# 🏅 Achievements trimming (robust)
# ============================================================

ACHIEVEMENT_SECTION_NAMES = [
    "Achievements",
    "Awards & Achievements",
    "Achievements & Awards",
    "Awards",
    "Honors & Awards",
    "Honors",
    "Awards & Certifications",
    "Certifications & Awards",
    "Certifications",
    "Certificates",
    "Accomplishments",
    "Activities & Achievements",
]

def _find_macro_items(block: str, macro: str) -> List[Tuple[int,int,int,int]]:
    """
    Find occurrences of a macro like \resumeSubItem{...} with balanced braces.
    Returns list of (start_idx, open_brace_idx, close_brace_idx, end_idx).
    """
    out, i = [], 0
    needle = f"\\{macro}{{"
    while True:
        i = block.find(needle, i)
        if i < 0:
            break
        open_b = i + len(f"\\{macro}")
        depth, j = 0, open_b
        while j < len(block):
            ch = block[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    close_b = j
                    out.append((i, open_b, close_b, close_b + 1))
                    i = close_b + 1
                    break
            j += 1
        else:
            break
    return out

def _remove_last_any_bullet(section_text: str) -> Tuple[str, bool, str]:
    """
    Try removing the last bullet in this section, in this order:
      1) \resumeItem{...}
      2) \resumeSubItem{...}
      3) \item ...   (until next \item or \end{itemize} or \resumeItemListEnd)
    Returns (new_text, removed?, how).
    """
    items = find_resume_items(section_text)
    if items:
        s, _op, _cl, e = items[-1]
        return section_text[:s] + section_text[e:], True, "resumeItem"

    subitems = _find_macro_items(section_text, "resumeSubItem")
    if subitems:
        s, _op, _cl, e = subitems[-1]
        return section_text[:s] + section_text[e:], True, "resumeSubItem"

    item_positions = [m.start() for m in re.finditer(r"\\item\b", section_text)]
    if item_positions:
        start = item_positions[-1]
        tail_m = re.search(r"(\\item\b|\\end\{itemize\}|\\resumeItemListEnd)", section_text[start+5:])
        end = len(section_text) if not tail_m else start + 5 + tail_m.start()
        return section_text[:start] + section_text[end:], True, "item"

    return section_text, False, ""

def _strip_empty_itemize_blocks(section_text: str) -> str:
    # Remove empty custom blocks: \resumeItemListStart ... \resumeItemListEnd with no \resumeItem inside
    start_tag, end_tag = r"\resumeItemListStart", r"\resumeItemListEnd"
    def _has_items(b: str) -> bool:
        return bool(find_resume_items(b)) or bool(_find_macro_items(b, "resumeSubItem")) or bool(re.search(r"\\item\b", b))
    out, i = [], 0
    while True:
        a = section_text.find(start_tag, i)
        if a < 0:
            out.append(section_text[i:])
            break
        b = section_text.find(end_tag, a)
        if b < 0:
            out.append(section_text[i:])
            break
        block = section_text[a:b]
        if _has_items(block):
            out.append(section_text[i:b + len(end_tag)])
        else:
            out.append(section_text[i:a])  # drop empty block
        i = b + len(end_tag)
    return "".join(out)

def _find_achievements_section_span_fuzzy(tex: str) -> Optional[Tuple[int, int, str]]:
    """
    Fuzzy-locate a section whose title contains any of these keywords:
    achieve|award|honor|cert|accomplish|activity.
    Returns (start_index, end_index, title) of the section block.
    """
    keywords = ("achiev", "award", "honor", "cert", "accomplish", "activity")
    last_match = None

    for m in SECTION_HEADER_RE.finditer(tex):
        title = (m.group(1) or "").lower()
        if any(k in title for k in keywords):
            start = m.start()
            next_m = SECTION_HEADER_RE.search(tex, m.end())
            end = next_m.start() if next_m else tex.find(r"\end{document}")
            if end == -1:
                end = len(tex)
            last_match = (start, end, title)

    return last_match

def remove_one_achievement_bullet(tex_content: str) -> Tuple[str, bool]:
    """
    Try to remove the last bullet-like entry from an Achievements-ish section.
    Supports \section and \section*, multiple common titles, and macros:
    \resumeItem, \resumeSubItem, or plain \item.
    Returns (new_tex, removed?).
    """
    # Exact known names
    for sec in ACHIEVEMENT_SECTION_NAMES:
        pat = section_rx(sec)
        m = pat.search(tex_content)
        if not m:
            continue
        full = m.group(1)
        new_sec, removed, how = _remove_last_any_bullet(full)
        if removed:
            log_event(f"✂️ [TRIM] Removed last bullet from '{sec}' via {how}.")
            new_sec = _strip_empty_itemize_blocks(new_sec)
            return tex_content[:m.start()] + new_sec + tex_content[m.end():], True

    # Fuzzy fallback
    fuzzy_span = _find_achievements_section_span_fuzzy(tex_content)
    if fuzzy_span:
        start, end, title = fuzzy_span
        full = tex_content[start:end]
        new_sec, removed, how = _remove_last_any_bullet(full)
        if removed:
            log_event(f"✂️ [TRIM] Fuzzy match '{title}' — removed via {how}.")
            new_sec = _strip_empty_itemize_blocks(new_sec)
            return tex_content[:start] + new_sec + tex_content[end:], True

    log_event("ℹ️ [TRIM] No Achievements-like bullets found to remove.")
    return tex_content, False

# ============================================================
# 🧠 Main optimizer — Coursework + Skills + 3-bullet Experience
# ============================================================

async def optimize_resume_latex(base_tex: str, jd_text: str) -> str:
    log_event("🟨 [AI] JD-aware Coursework, Skills, and Experience (GPT-driven)")
    split = re.search(r"(%-----------EDUCATION-----------)", base_tex)
    if not split:
        preamble, body = "", base_tex
    else:
        preamble, body = base_tex[:split.start()], base_tex[split.start():]
    body = re.sub(r"\\end\{document\}", "", body)

    # Coursework (distinct across degrees, JD-prioritized)
    courses = await extract_coursework_gpt(jd_text, max_courses=6)
    body = replace_relevant_coursework_distinct(body, courses, max_per_line=6)

    # Skills: JD keywords + JD requirements + related (keep all JD items)
    all_skills_raw, protected = await extract_skills_gpt(jd_text)
    all_skills = prune_and_compact_skills(all_skills_raw, protected=protected)
    body = await replace_skills_section(body, all_skills)  # async & GPT-labeled 4 rows

    # Experience/Projects → EXACT 3 bullets each (GPT-targeted)
    body = await retarget_experience_sections_with_gpt(body, jd_text)

    # Safety net: enforce ≤3 bullets per itemize
    body = limit_experience_bullets(body)

    final = (preamble.strip() + "\n\n" + body.strip()).rstrip()
    if "\\end{document}" not in final:
        final += "\n\\end{document}\n"
    log_event("✅ [AI] Body updated: Coursework (distinct), Skills(4 rows), Experience(3/job-targeted)")
    return final

# ============================================================
# ✨ Humanize ONLY \resumeItem{…} text
# ============================================================

async def humanize_experience_bullets(tex_content: str) -> str:
    log_event("🟨 [HUMANIZE] Targeting EXPERIENCE/PROJECTS")

    async def _humanize_block(block: str) -> str:
        items = find_resume_items(block)
        if not items:
            return block
        plain_texts = []
        for (_s, open_b, close_b, _e) in items:
            inner = block[open_b + 1:close_b]
            txt = strip_all_macros_keep_text(inner)
            plain_texts.append(txt[:1000].strip())

        headers = {"Authorization": config.HUMANIZE_API_KEY, "Content-Type": "application/json"}

        async def rewrite_one(text: str, idx: int) -> str:
            payload = {"model": "0", "mail": "kadali18@terpmail.umd.edu", "data": text}
            for _attempt in range(2):
                try:
                    async with httpx.AsyncClient(timeout=20.0) as client:
                        r = await client.post("https://aihumanize.io/api/v1/rewrite", headers=headers, json=payload)
                        if r.status_code == 200:
                            data = r.json()
                            if data.get("code") == 200 and data.get("data"):
                                return latex_escape_text(data["data"].strip())
                except Exception:
                    await asyncio.sleep(0.4)
            return latex_escape_text(text)

        sem = asyncio.Semaphore(5)
        async def lim(i, t):
            async with sem:
                return await rewrite_one(t, i)
        humanized = await asyncio.gather(*[lim(i, t) for i, t in enumerate(plain_texts, 1)])
        return replace_resume_items(block, humanized)

    for sec_name in ["Experience", "Projects"]:
        pat = section_rx(sec_name)
        out, pos = [], 0
        for m in pat.finditer(tex_content):
            out.append(tex_content[pos:m.start()])
            section = m.group(1)
            s_tag, e_tag = r"\resumeItemListStart", r"\resumeItemListEnd"
            rebuilt, i = [], 0
            while True:
                a = section.find(s_tag, i)
                if a < 0:
                    rebuilt.append(section[i:])
                    break
                b = section.find(e_tag, a)
                if b < 0:
                    rebuilt.append(section[i:])
                    break
                rebuilt.append(section[i:a])
                block = section[a:b]
                block = await _humanize_block(block)
                rebuilt.append(block)
                rebuilt.append(section[b:b + len(e_tag)])
                i = b + len(e_tag)
            out.append("".join(rebuilt))
            pos = m.end()
        out.append(tex_content[pos:])
        tex_content = "".join(out)

    return tex_content

# ============================================================
# 🚀 Endpoint (with one-page guardrail via Achievements trimming)
# ============================================================

@router.post("/optimize")
async def optimize_endpoint(
    base_resume_tex: UploadFile,
    jd_text: str = Form(...),
    use_humanize: bool = Form(False),
):
    try:
        tex_bytes = await base_resume_tex.read()
        tex = tex_bytes.decode("utf-8", errors="ignore")
        raw_tex = secure_tex_input(base_resume_tex.filename, tex)

        company_name, role = await extract_company_role(jd_text)
        optimized_tex = await optimize_resume_latex(raw_tex, jd_text)

        # Ensure each itemize still ≤3 (safety net)
        optimized_tex = limit_experience_bullets(optimized_tex)

        # ---------- Compile base ----------
        final_tex = render_final_tex(optimized_tex)
        pdf_bytes_original = compile_latex_safely(final_tex)
        base_pages = _pdf_page_count(pdf_bytes_original)
        log_event(f"📄 Base PDF pages: {base_pages}")

        # ---------- Optional: build humanized (will be trimmed in sync) ----------
        pdf_bytes_humanized: Optional[bytes] = None
        humanized_tex: Optional[str] = None

        if use_humanize:
            humanized_tex = await humanize_experience_bullets(optimized_tex)
            humanized_tex = limit_experience_bullets(humanized_tex)
            humanized_tex_rendered = render_final_tex(humanized_tex)
            pdf_bytes_humanized = compile_latex_safely(humanized_tex_rendered)

        # ---------- Save directory / filenames ----------
        job_dir = config.DATA_DIR / "Job Resumes"
        job_dir.mkdir(parents=True, exist_ok=True)
        safe_company, safe_role = safe_filename(company_name), safe_filename(role)
        saved_paths: List[str] = []

        # Save initial compilation(s)
        if pdf_bytes_original:
            p = job_dir / f"Sri_Akash_Kadali_Resume_{safe_company}_{safe_role}.pdf"
            p.write_bytes(pdf_bytes_original)
            saved_paths.append(str(p))
            log_event(f"💾 [SAVE] Original PDF → {p}")
        if use_humanize and pdf_bytes_humanized:
            p = job_dir / f"Sri_Akash_Kadali_Resume_{safe_company}_{safe_role}_Humanized.pdf"
            p.write_bytes(pdf_bytes_humanized)
            saved_paths.append(str(p))
            log_event(f"💾 [SAVE] Humanized PDF → {p}")
        elif use_humanize and humanized_tex:
            # keep failed TEX snapshot for debugging
            t = job_dir / f"FAILED_Humanized_{safe_company}_{safe_role}.tex"
            t.write_text(humanized_tex, encoding="utf-8")
            log_event(f"🧾 [DEBUG] Saved failed humanized LaTeX → {t}")

        # ---------- If >1 page, iteratively trim Achievements and save after EVERY removal ----------
        MAX_TRIMS = 50
        cur_tex = optimized_tex
        cur_humanized_tex = humanized_tex if use_humanize else None
        cur_pdf_bytes = pdf_bytes_original
        cur_pages = base_pages
        trim_idx = 0

        while cur_pages > 1 and trim_idx < MAX_TRIMS:
            next_tex, removed = remove_one_achievement_bullet(cur_tex)
            if not removed:
                log_event("ℹ️ No more Achievements bullets to remove; stopping trim loop.")
                break

            trim_idx += 1
            log_event(f"✂️ [TRIM {trim_idx}] Removed one Achievements bullet")

            # Compile base after trim
            next_tex_rendered = render_final_tex(next_tex)
            next_pdf_bytes = compile_latex_safely(next_tex_rendered)
            next_pages = _pdf_page_count(next_pdf_bytes)
            log_event(f"📄 [TRIM {trim_idx}] Base pages now: {next_pages}")

            # Save base after each trim attempt
            if next_pdf_bytes:
                p = job_dir / f"Sri_Akash_Kadali_Resume_{safe_company}_{safe_role}_Trim{trim_idx}.pdf"
                p.write_bytes(next_pdf_bytes)
                saved_paths.append(str(p))
                log_event(f"💾 [SAVE] Trim {trim_idx} base PDF → {p}")

            # Humanized: mirror the removal and save each time
            if use_humanize:
                if cur_humanized_tex is None:
                    cur_humanized_tex = cur_tex  # fallback — achievements bullets are not humanized anyway
                next_h_tex, _ = remove_one_achievement_bullet(cur_humanized_tex)
                h_rendered = render_final_tex(next_h_tex)
                h_pdf = compile_latex_safely(h_rendered)
                if h_pdf:
                    p = job_dir / f"Sri_Akash_Kadali_Resume_{safe_company}_{safe_role}_Trim{trim_idx}_Humanized.pdf"
                    p.write_bytes(h_pdf)
                    saved_paths.append(str(p))
                    log_event(f"💾 [SAVE] Trim {trim_idx} humanized PDF → {p}")
                else:
                    # minimal fallback for the humanized variant
                    blocks = re.findall(r"\\resumeItem\{([\s\S]*?)\}", next_h_tex)
                    bullets = [sanitize_for_minimal(b) for b in blocks] or ["(No humanized bullets available)"]
                    safe_items = "\n".join([f"\\item {b}" for b in bullets])
                    minimal_tex = f"""
\\documentclass[letterpaper,10pt]{{article}}
\\usepackage[margin=0.8in]{{geometry}}
\\usepackage{{enumitem}}
\\usepackage{{hyperref}}
\\begin{{document}}
\\section*{{Humanized Resume Summary}}
\\begin{{itemize}}[leftmargin=0.3in]
{safe_items}
\\end{{itemize}}
\\end{{document}}
"""
                    h_pdf_fallback = compile_latex_safely(minimal_tex)
                    if h_pdf_fallback:
                        p = job_dir / f"Sri_Akash_Kadali_Resume_{safe_company}_{safe_role}_Trim{trim_idx}_Humanized.pdf"
                        p.write_bytes(h_pdf_fallback)
                        saved_paths.append(str(p))
                        log_event(f"💾 [SAVE] Trim {trim_idx} humanized (fallback) → {p}")

                # advance humanized cursor
                cur_humanized_tex = next_h_tex

            # advance base cursor
            cur_tex, cur_pdf_bytes, cur_pages = next_tex, next_pdf_bytes, next_pages

            # Stop as soon as we fit on one page
            if cur_pages <= 1:
                log_event(f"✅ Fits on one page after {trim_idx} trims.")
                break

        # Prepare response using the *latest* fitting tex/PDF (or last attempt)
        final_tex = render_final_tex(cur_tex)
        pdf_bytes_original = compile_latex_safely(final_tex)

        pdf_bytes_humanized = None
        if use_humanize:
            final_h_tex = cur_humanized_tex or cur_tex
            final_h_tex = render_final_tex(final_h_tex)
            pdf_bytes_humanized = compile_latex_safely(final_h_tex)

        log_event(f"🟩 [PIPELINE] Completed — PDFs saved: {len(saved_paths)}")
        return JSONResponse({
            "tex_string": final_tex,
            "pdf_base64": base64.b64encode(pdf_bytes_original or b"").decode("ascii"),
            "pdf_base64_humanized": base64.b64encode(pdf_bytes_humanized or b"").decode("ascii") if pdf_bytes_humanized else None,
            "company_name": company_name,
            "role": role,
            "saved_paths": saved_paths,
        })
    except Exception as e:
        log_event(f"💥 [PIPELINE] Optimization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
