# --- stdlib ---
import asyncio
import base64
import json
import re
from typing import List, Tuple, Dict, Iterable, Optional, Set

# --- third-party ---
import httpx
from fastapi import APIRouter, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI

# --- local ---
from backend.core import config
from backend.core.compiler import compile_latex_safely
from backend.core.security import secure_tex_input
from backend.core.utils import log_event, safe_filename
from api.render_tex import render_final_tex

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
                    close_b = j
                    out.append((i, open_brace, close_b, close_b + 1))
                    i = close_b + 1
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
# 🎯 JD → Skills (high-recall + semantically aligned)
# ============================================================

async def extract_skills_gpt(jd_text: str) -> Tuple[List[str], Set[str]]:
    """
    Extract high-recall skill tokens from any JD.
    Captures explicit and strongly implied technical and linguistic skills
    so early coverage ≈95-99 % without multiple refinement loops.
    """
    json_example = (
        '{\n'
        '  "jd_keywords": ["Python","SQL","LLMs","Transformer Models","Debugging Workflows",'
        '"Data Analysis","Machine Learning","Evaluation","Prompt Engineering","Docker","Kubernetes"],\n'
        '  "requirements": ["Python","JavaScript","Problem Solving","Debugging Workflows",'
        '"Algorithms","Data Structures","English (professional)"],\n'
        '  "related": ["Pandas","NumPy","scikit-learn","PyTorch","TensorFlow","OpenAI API",'
        '"FastAPI","AWS","GCP","CI/CD","Git","Linux"]\n'
        '}'
    )

    prompt = (
        "Extract all technical and linguistic skill tokens for this job in THREE sets.\n\n"
        "1) \"jd_keywords\": include every concrete skill, library, framework, platform, or concept "
        "explicitly mentioned OR semantically implied by the JD "
        "(e.g., if the JD says 'large language models', also include 'LLMs', 'Transformer Models').\n"
        "2) \"requirements\": the MUST-HAVE skills or task-type requirements "
        "(annotation, debugging, evaluation, data labeling, algorithmic problem solving, etc.).\n"
        "3) \"related\": adjacent or supporting skills that a recruiter would expect to co-occur "
        "(e.g., Pandas with Python, Docker with CI/CD, etc.).\n\n"
        "Rules:\n"
        "- Return STRICT JSON ONLY in the format:\n"
        f"{json_example}\n"
        "- Deduplicate across lists.\n"
        "- Use short canonical tokens (1–4 words, no full sentences).\n"
        "- Include both direct and adjacent terms that appear naturally on a resume.\n"
        "- Preserve language-proficiency tokens if present (e.g., 'English (professional)').\n\n"
        "JD:\n"
        f"{jd_text}"
    )

    try:
        data = await gpt_json(prompt, temperature=0.0)
        jd_kw = data.get("jd_keywords", []) or []
        reqs  = data.get("requirements", []) or []
        rel   = data.get("related", []) or []

        combined, seen = [], set()
        for lst in (jd_kw, reqs, rel):
            for s in lst:
                s = re.sub(r"[^\w\-\+\.#\/ \(\)]", "", str(s)).strip()
                if not s:
                    continue
                s = canonicalize_token(s)
                if s.lower() not in seen:
                    seen.add(s.lower())
                    combined.append(s)

        protected = {canonicalize_token(s).lower() for s in (jd_kw + reqs)}
        log_event(f"💡 [JD SKILLS] high-recall jd={len(jd_kw)} req={len(reqs)} rel={len(rel)} → {len(combined)} total")
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
        ]) or any(x in ls for x in ["machine learning","deep learning","nlp","vision","time series","recomm"]):
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
            if v.lower() not in seen:
                seen.add(v.lower()); ded.append(v)
        cat[k] = ded
    return cat

def _split_half(vals: List[str]) -> Tuple[List[str], List[str]]:
    if not vals: return [], []
    mid = (len(vals) + 1) // 2
    return vals[:mid], vals[mid:]

def _build_skill_rows(cat: Dict[str, List[str]]) -> List[Tuple[str, List[str]]]:
    prog = cat.get("Programming", [])
    ml   = cat.get("Data & ML", [])
    fw   = cat.get("Frameworks", [])
    engd = (cat.get("Data Engineering", []) or []) + (cat.get("Cloud & DevOps", []) or [])
    vizt = (cat.get("Visualization", []) or []) + (cat.get("Tools", []) or [])
    other= (cat.get("Math & Stats", []) or []) + (cat.get("Soft Skills", []) or [])

    rows: List[Tuple[str, List[str]]] = []
    rows.append(("Programming", prog if not (prog and all(p.lower()=="sql" for p in prog)) else prog))
    if ml: rows.append(("Machine Learning", ml)); ml=[]
    elif fw: rows.append(("Frameworks & Libraries", fw)); fw=[]
    elif vizt: half, vizt = _split_half(vizt); rows.append(("Business Intelligence & Analytics", half))
    elif other: half, other = _split_half(other); rows.append(("Other Requirements", half))
    else: rows.append(("Frameworks & Libraries", []))

    if engd: rows.append(("Data Engineering & DevOps", engd)); engd=[]
    elif fw: half, fw = _split_half(fw); rows.append(("Frameworks & Libraries", half))
    elif vizt: half, vizt = _split_half(vizt); rows.append(("Tools & Platforms", half))
    elif other: half, other = _split_half(other); rows.append(("Other Requirements", half))
    else: rows.append(("Data Engineering & DevOps", []))

    tail = (fw or []) + (vizt or []) + (other or []) + (ml or []) + (engd or [])
    row4_label = "Soft Skills & Other" if other and len(other) >= max(1, len(tail)//2) else "Additional Tools & Skills"
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
    defaults = [r[0] for r in rows]
    rows_preview = [{"default_label": r[0], "samples": _sample_list(r[1], 10)} for r in rows]
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
        log_event("🏷️ [SKILLS LABELS] Fallback to defaults after invalid reconfirm.")
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
    lines += [r"  \end{tabularx}", r"  }", r"\end{itemize}"]
    return "\n".join(lines)

async def replace_skills_section(body_tex: str, skills: List[str]) -> str:
    new_block = await render_skills_block_with_gpt(categorize(skills))
    pattern = re.compile(r"(\\section\*?\{Skills\}[\s\S]*?)(?=%-----------|\\section\*?\{|\\end\{document\})", re.IGNORECASE)
    if re.search(pattern, body_tex):
        return re.sub(pattern, lambda _m: new_block + "\n", body_tex)
    m = re.search(r"%-----------TECHNICAL SKILLS-----------", body_tex, re.IGNORECASE)
    if m:
        idx = m.end()
        return body_tex[:idx] + "\n" + new_block + "\n" + body_tex[idx:]
    return "%-----------TECHNICAL SKILLS-----------\n" + new_block + "\n" + body_tex

# ============================================================
# 🎓 Replace “Relevant Coursework” lines — distinct, JD-first
# ============================================================

def replace_relevant_coursework_distinct(body_tex: str, courses: List[str], max_per_line: int = 6) -> str:
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

    chunks: List[List[str]] = []
    if len(matches) == 1:
        chunks.append(uniq[:max_per_line])
    else:
        n = len(uniq)
        split_idx = (n + 1) // 2
        first = uniq[:split_idx][:max_per_line]
        second = uniq[split_idx:split_idx + max_per_line]
        if not second and n >= 2 and len(first) >= 2:
            second = [first.pop()]
        chunks = [first, second]
        rem = uniq[split_idx + len(chunks[1]) if len(chunks) > 1 else len(chunks[0]):]
        while len(chunks) < len(matches) and rem:
            chunks.append(rem[:max_per_line]); rem = rem[max_per_line:]

    out, last = [], 0
    for i, m in enumerate(matches):
        out.append(body_tex[last:m.start()])
        if i < len(chunks):
            payload = ", ".join(latex_escape_text(x) for x in chunks[i])
            out.append(m.group(1) + " " + payload)
        else:
            out.append(m.group(0))
        last = m.end()
    out.append(body_tex[last:])
    return "".join(out)

# ============================================================
# 💼 GPT: select + rewrite bullets for universal JD alignment
# ============================================================

async def gpt_select_and_rewrite_bullets(jd_text: str, bullets: List[str]) -> List[str]:
    """
    Picks the top 3 bullets and rewrites them so that every bullet contains
    at least one JD-relevant keyword. Maximizes alignment while staying truthful.
    Works for any job domain.
    """
    plain = [strip_all_macros_keep_text(b) for b in bullets]
    bullets_json_example = '{"bullets":["...","...","..."]}'

    prompt = (
        "You are optimizing resume bullets for maximum alignment with THIS job description.\n"
        f"Return STRICT JSON: {bullets_json_example} with EXACTLY 3 rewritten items.\n\n"
        "Rules:\n"
        "- Select the 3 bullets that best match the JD’s skills, tools, and outcomes, "
        "even if other bullets seem more impressive.\n"
        "- Reuse JD wording (keywords, verbs, technologies, or evaluation terms) when they truthfully describe the work.\n"
        "- Each bullet MUST include at least one JD-relevant keyword "
        "(language, framework, ML concept, evaluation task, or skill phrase).\n"
        "- Keep factual accuracy; never fabricate new projects, data, or results.\n"
        "- Write each as ONE concise past-tense sentence (≤30 words) with metrics when available.\n"
        "- Avoid first person and fluff; use domain-specific action verbs.\n\n"
        "JOB DESCRIPTION:\n"
        f"{jd_text}\n\n"
        "CANDIDATE BULLETS:\n" + "\n".join(f"- {t}" for t in plain)
    )

    data = await gpt_json(prompt, temperature=0.0)
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
            out.append(section_text[i:]); break
        b = section_text.find(e_tag, a)
        if b < 0:
            out.append(section_text[i:]); break
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
                res.append(btxt[last:]); return "".join(res)

            block_no_items = _remove_all_items(block)
            insert_at = block_no_items.find(s_tag) + len(s_tag)
            inject = "".join(f"\n  \\resumeItem{{{t}}}" for t in bullets_new)
            block = block_no_items[:insert_at] + inject + block_no_items[insert_at:]
        out.append(block); out.append(section_text[b:b + len(e_tag)])
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
            out.append(section); pos = m.end()
        out.append(tex_content[pos:])
        tex_content = "".join(out)
    return tex_content

# ============================================================
# 📄 PDF page-count helper
# ============================================================

def _pdf_page_count(pdf_bytes: Optional[bytes]) -> int:
    if not pdf_bytes:
        return 0
    return len(re.findall(rb"/Type\s*/Page\b", pdf_bytes))

# ============================================================
# 🏅 Achievements trimming (robust)
# ============================================================

ACHIEVEMENT_SECTION_NAMES = [
    "Achievements","Awards & Achievements","Achievements & Awards","Awards",
    "Honors & Awards","Honors","Awards & Certifications","Certifications & Awards",
    "Certifications","Certificates","Accomplishments","Activities & Achievements",
]

def _find_macro_items(block: str, macro: str) -> List[Tuple[int, int, int, int]]:
    """
    Find occurrences of a macro like \macro{...} with balanced braces.
    Returns a list of (start_idx, open_brace_idx, close_brace_idx, end_idx).
    """
    out: List[Tuple[int, int, int, int]] = []
    i = 0
    needle = f"\\{macro}{{"  # e.g., "\resumeSubItem{"
    while True:
        i = block.find(needle, i)
        if i < 0:
            break

        # index of the opening '{'
        open_b = i + len(f"\\{macro}")
        if open_b >= len(block) or block[open_b] != "{":
            i += 1
            continue

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
            # unmatched braces; stop scanning
            break

    return out

def _remove_last_any_bullet(section_text: str) -> Tuple[str, bool, str]:
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
    start_tag, end_tag = r"\resumeItemListStart", r"\resumeItemListEnd"
    def _has_items(b: str) -> bool:
        return bool(find_resume_items(b)) or bool(_find_macro_items(b, "resumeSubItem")) or bool(re.search(r"\\item\b", b))
    out, i = [], 0
    while True:
        a = section_text.find(start_tag, i)
        if a < 0: out.append(section_text[i:]); break
        b = section_text.find(end_tag, a)
        if b < 0: out.append(section_text[i:]); break
        block = section_text[a:b]
        if _has_items(block):
            out.append(section_text[i:b + len(end_tag)])
        else:
            out.append(section_text[i:a])  # drop empty
        i = b + len(end_tag)
    return "".join(out)

def _find_achievements_section_span_fuzzy(tex: str) -> Optional[Tuple[int, int, str]]:
    keywords = ("achiev", "award", "honor", "cert", "accomplish", "activity")
    last_match = None
    for m in SECTION_HEADER_RE.finditer(tex):
        title = (m.group(1) or "").lower()
        if any(k in title for k in keywords):
            start = m.start()
            next_m = SECTION_HEADER_RE.search(tex, m.end())
            end = next_m.start() if next_m else tex.find(r"\end{document}")
            if end == -1: end = len(tex)
            last_match = (start, end, title)
    return last_match

def remove_one_achievement_bullet(tex_content: str) -> Tuple[str, bool]:
    for sec in ACHIEVEMENT_SECTION_NAMES:
        pat = section_rx(sec)
        m = pat.search(tex_content)
        if not m: continue
        full = m.group(1)
        new_sec, removed, how = _remove_last_any_bullet(full)
        if removed:
            log_event(f"✂️ [TRIM] Removed last bullet from '{sec}' via {how}.")
            new_sec = _strip_empty_itemize_blocks(new_sec)
            return tex_content[:m.start()] + new_sec + tex_content[m.end():], True
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
# 🔎 Coverage normalization helpers (LaTeX unescape + variants)
# ============================================================

_LATEX_UNESC = [
    (r"\#", "#"), (r"\$", "$"), (r"\%", "%"), (r"\&", "&"),
    (r"\_", "_"), (r"\/", "/"),
]

def _plain_text_for_coverage(tex: str) -> str:
    """
    Produce a plain, human-ish text for coverage matching:
      - strip macros
      - unescape common LaTeX sequences (C\\# -> C#, CI\\/CD -> CI/CD)
      - collapse whitespace
    """
    s = strip_all_macros_keep_text(tex)
    for a, b in _LATEX_UNESC:
        s = s.replace(a, b)
    # very common resume tokens:
    s = s.replace("C\\#", "C#").replace("CI\\/CD", "CI/CD")
    s = s.replace("A\\/B", "A/B").replace("R\\&D", "R&D")
    s = re.sub(r"\s+", " ", s).strip()
    return s

# Map canonical token -> acceptable variant spellings for coverage only
_VARIANTS = {
    "kubernetes": ["k8s"],
    "node.js": ["nodejs", "node js", "node"],
    "ci/cd": ["ci cd", "ci-cd"],
    "llms": ["llm", "large language models", "large-language models"],
    "openai api": ["openai"],
    "hugging face transformers": ["hf transformers", "transformers"],
    "postgresql": ["postgres", "postgres sql"],
    "c++": ["cpp"],
    "c#": ["c sharp", "csharp"],
    "sql": ["t-sql", "pl/sql", "ms sql", "postgres", "mysql"],
    "bigquery": ["google bigquery", "big query"],
}

def _expand_variants(token: str) -> List[str]:
    """
    For a canonical token, return a set of variant strings to try when matching.
    Includes punctuation-relaxed forms for robustness (e.g., 'nodejs' vs 'node.js').
    """
    t = canonicalize_token(token).lower().strip()
    alts = _VARIANTS.get(t, [])
    relaxed = {
        t,
        t.replace(".", ""),
        t.replace("/", " "),
        t.replace("-", " "),
    }
    return sorted({*alts, *relaxed})

# ============================================================
# 🧠 Main optimizer — Coursework + Skills + JD-retargeted bullets (High-Recall + Proactive)
# ============================================================

async def optimize_resume_latex(base_tex: str, jd_text: str) -> str:
    """
    Perform a full JD-aware optimization pass:
    - Extracts JD-relevant coursework (with keyword reinforcement)
    - Builds high-recall Skills section (synonyms + related terms)
    - Retargets Experience bullets to JD (truthful rewrite)
    - Proactively improves keyword coverage to ≥95% before refinement loop
    """
    log_event("🟨 [AI] JD-aware Coursework, Skills, and Experience (GPT-driven, high-recall)")

    # --- Split preamble/body ---
    split = re.search(r"(%-----------EDUCATION-----------)", base_tex)
    if not split:
        preamble, body = "", base_tex
    else:
        preamble, body = base_tex[:split.start()], base_tex[split.start():]
    body = re.sub(r"\\end\{document\}", "", body)

    # --- JD-based Relevant Coursework (with reinforcement) ---
    courses = await extract_coursework_gpt(jd_text, max_courses=6)
    body = replace_relevant_coursework_distinct(body, courses, max_per_line=6)

    # --- JD-based Skills extraction (high recall + canonicalization) ---
    all_skills_raw, protected = await extract_skills_gpt(jd_text)
    all_skills = prune_and_compact_skills(all_skills_raw, protected=protected)
    body = await replace_skills_section(body, all_skills)

    # --- Retarget Experience/Projects bullets to JD keywords ---
    body = await retarget_experience_sections_with_gpt(body, jd_text)

    # --- Proactive coverage improvement (ensures ≥95% before refinement) ---
    try:
        tokens = await get_coverage_targets_from_jd(jd_text)
        cov = compute_keyword_coverage(body, tokens)
        if cov["ratio"] < 0.95:
            log_event(f"⚙️ [PRE-COVERAGE] Initial ratio {cov['ratio']:.2%}; improving for ≥95%.")
            body = await gpt_improve_for_missing_keywords(body, jd_text, cov["missing"])
        else:
            log_event(f"✅ [PRE-COVERAGE] Already {cov['ratio']:.2%} — no pre-improvement needed.")
    except Exception as e:
        log_event(f"⚠️ [PRE-COVERAGE] Improvement step skipped due to error: {e}")

    # --- Final merge and validation ---
    final = (preamble.strip() + "\n\n" + body.strip()).rstrip()
    if "\\end{document}" not in final:
        final += "\n\\end{document}\n"

    log_event("✅ [AI] Body finalized: Coursework (JD-based), Skills (high-recall), "
              "Experience (JD-aligned), Coverage (≥95%).")
    return final

# ============================================================
# ✨ Humanize ONLY \resumeItem{…} text (run once after ≥90% coverage)
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
                if a < 0: rebuilt.append(section[i:]); break
                b = section.find(e_tag, a)
                if b < 0: rebuilt.append(section[i:]); break
                rebuilt.append(section[i:a])
                block = section[a:b]
                block = await _humanize_block(block)
                rebuilt.append(block)
                rebuilt.append(section[b:b + len(e_tag)])
                i = b + len(e_tag)
            out.append("".join(rebuilt)); pos = m.end()
        out.append(tex_content[pos:])
        tex_content = "".join(out)
    return tex_content

# ============================================================
# 🔧 Body/preamble split & merge
# ============================================================

_EDU_SPLIT_ANCHOR = re.compile(r"(%-----------EDUCATION-----------)|\\section\\*?\\{\\s*Education\\s*\\}", re.IGNORECASE)

def _split_preamble_body(tex: str) -> tuple[str, str]:
    m = _EDU_SPLIT_ANCHOR.search(tex)
    if not m:
        return "", re.sub(r"\\end\\{document\\}\\s*$", "", tex)
    start = m.start()
    preamble = tex[:start]
    body = re.sub(r"\\end\\{document\\}\\s*$", "", tex[start:])
    return preamble, body

def _merge_tex(preamble: str, body: str) -> str:
    out = (preamble.strip() + "\n\n" + body.strip()).rstrip()
    if "\\end{document}" not in out:
        out += "\n\\end{document}\n"
    return out

def _sanitize_improved_body(s: str) -> str:
    s = s.replace("```latex", "").replace("```", "").strip()
    s = re.sub(r"(?is)\\documentclass.*?\\begin\\{document\\}", "", s)
    s = re.sub(r"(?is)\\end\\{document\\}", "", s)
    return s.strip()

# ============================================================
# 🔍 JD keyword coverage helpers (target = jd_keywords + requirements)
# ============================================================

def _token_regex(token: str) -> re.Pattern:
    """
    Regex for a token that may include punctuation like C++, CI/CD, Node.js.
    Uses alpha-num boundaries rather than \\b to tolerate symbols.
    """
    t = token.lower().strip()
    t = re.escape(t)
    t = t.replace(r"\ ", r"\s+").replace(r"\/", r"\s*\/\s*").replace(r"\.", r"\.")
    return re.compile(rf"(?<![a-z0-9]){t}(?![a-z0-9])", re.IGNORECASE)

def _present_tokens_in_text(text_plain: str, tokens: Iterable[str]) -> Tuple[Set[str], Set[str]]:
    """
    Variant-aware presence check:
      - expands each canonical token into acceptable variants
      - matches using a relaxed boundary regex (_token_regex)
    """
    present, missing = set(), set()
    low_text = text_plain.lower()
    for tok in {canonicalize_token(t).lower().strip() for t in tokens if str(t).strip()}:
        hit = False
        for v in _expand_variants(tok):
            if _token_regex(v).search(low_text):
                hit = True
                break
        (present if hit else missing).add(tok)
    return present, missing


# ============================================================
# 🪄 Coverage token filtering (skip soft/unwinnable items)
# ============================================================

_SKIP_PATTERNS = [
    r"english\s*\(professional\)", r"chinese\s*\(professional\)",
    r"\bcommunication\b", r"\bteamwork\b", r"\bcollaboration\b",
    r"debugging workflows", r"strong interest", r"\bcuriosity\b",
]

def _is_coverage_token(tok: str) -> bool:
    ls = canonicalize_token(tok).lower().strip()
    return not any(re.search(p, ls) for p in _SKIP_PATTERNS)

async def get_coverage_targets_from_jd(jd_text: str) -> List[str]:
    """
    Build the set of tokens the score is based on, **excluding** soft/low-signal items.
    Uses the protected set (jd_keywords + requirements) from the JD extractor.
    """
    _combined, protected = await extract_skills_gpt(jd_text)
    kept = [t for t in protected if _is_coverage_token(t)]
    return sorted(list({canonicalize_token(t).lower() for t in kept if t}))


def compute_keyword_coverage(tex_content: str, tokens_for_coverage: List[str]) -> Dict[str, object]:
    """
    Compute coverage over fully plain text derived from LaTeX:
      - macros stripped
      - common LaTeX escapes unescaped (so C#, CI/CD, R&D, A/B match)
    """
    plain = _plain_text_for_coverage(tex_content)
    present, missing = _present_tokens_in_text(plain, tokens_for_coverage)
    total = max(1, len(set(tokens_for_coverage)))
    ratio = len(present) / total
    return {
        "ratio": ratio,
        "present": sorted(present),
        "missing": sorted(missing),
        "total": total
    }


# ============================================================
# ✍️ GPT step to weave in missing keywords (truthfully)
# ============================================================

# ============================================================
# ✍️ GPT step to weave in missing keywords (truthfully) — Skills + Experience/Projects
# ============================================================

async def gpt_improve_for_missing_keywords(body_tex: str, jd_text: str, missing_tokens: List[str]) -> str:
    """
    Ask GPT to incorporate as many of the missing JD tokens as TRUTH allows,
    by (a) reinforcing the Skills table and (b) rewriting Experience/Projects bullets.
    No fabrication; reuse existing truthful content and wording.
    Returns improved LaTeX BODY (Education→end).
    """
    example = '{"improved_body": "%-----------EDUCATION-----------\\n..."}'
    rules = (
        "Goal: incorporate as many of these missing JD keywords as TRUTH allows: "
        + ", ".join(missing_tokens[:60])
        + ".\n"
          "- Update ONLY the LaTeX BODY (Education→end). Keep all resume macros intact (e.g., \\resumeItem, \\resumeItemListStart/End).\n"
          "- PRIORITY 1: Reword existing bullets under Experience/Projects to truthfully reflect tools/tasks already done; add metrics if they already exist.\n"
          "- PRIORITY 2: Strengthen the Skills table using short canonical tokens; do NOT add skills the candidate never used.\n"
          "- Do NOT invent new employers/projects or claim tools that were not used.\n"
          "- Keep to one page in spirit; ≤3 bullets per role unless it still fits on one page.\n"
          "- Return STRICT JSON only with the key improved_body."
    )
    prompt = (
        f"{rules}\n\n"
        f"RETURN STRICT JSON ONLY like: {example}\n\n"
        "JOB DESCRIPTION:\n"
        f"{jd_text}\n\n"
        "CURRENT BODY (LaTeX, from Education onward):\n"
        f"{body_tex}"
    )
    data = await gpt_json(prompt, temperature=0.0)
    ib = str((data or {}).get("improved_body", "")).strip()
    return _sanitize_improved_body(ib) if ib else body_tex

# ============================================================
# 🔁 Coverage-driven refinement (aim for ≥ 90%)
# ============================================================

async def _rebuild_skills_safely(tex_content: str, jd_text: str) -> str:
    all_skills_raw, protected = await extract_skills_gpt(jd_text)
    all_skills = prune_and_compact_skills(all_skills_raw, protected=protected)
    return await replace_skills_section(tex_content, all_skills)

# ============================================================
# 🔁 Coverage-driven refinement (aim for ≥ 99%) — Skills + Experience/Projects every round
# ============================================================

async def refine_resume_to_keyword_coverage(
    tex_content: str,
    jd_text: str,
    min_ratio: float = 0.99,
    max_rounds: int = 12
) -> Tuple[str, Dict[str, object], list]:
    """
    Iteratively improve BODY to reach ≥ min_ratio coverage of JD tokens (jd_keywords + requirements).
    On every round:
      - GPT rewrites Experience/Projects bullets + strengthens Skills (truthful),
      - rebuild Skills from JD,
      - remain within one page spirit (formal trim happens later).
    Returns (final_tex, coverage_report, history)
    """
    tokens = await get_coverage_targets_from_jd(jd_text)
    pre, body = _split_preamble_body(tex_content)
    history = []

    # Initial rebuild of Skills helps coverage immediately
    merged = _merge_tex(pre, body)
    merged = await _rebuild_skills_safely(merged, jd_text)
    pre, body = _split_preamble_body(merged)

    for rnd in range(1, max_rounds + 1):
        cur_tex = _merge_tex(pre, body)
        cov = compute_keyword_coverage(cur_tex, tokens)
        history.append({"round": rnd, "coverage": cov["ratio"], "missing": cov["missing"][:40]})
        log_event(f"📊 [COVERAGE r{rnd}] {len(cov['present'])}/{cov['total']} → {cov['ratio']:.1%}")

        if cov["ratio"] >= min_ratio:
            return cur_tex, cov, history

        # 1) Ask GPT to weave in missing tokens (truthful) across Skills + Experience/Projects
        improved_body = await gpt_improve_for_missing_keywords(body, jd_text, cov["missing"])
        merged2 = _merge_tex(pre, improved_body)

        # 2) Explicitly retarget Experience/Projects with JD again (keeps bullets laser-aligned)
        merged2 = await retarget_experience_sections_with_gpt(merged2, jd_text)

        # 3) Rebuild Skills from JD one more time to consolidate tokens
        merged2 = await _rebuild_skills_safely(merged2, jd_text)

        pre, body = _split_preamble_body(merged2)

    # Final compute and return (even if below target)
    final_tex = _merge_tex(pre, body)
    cov = compute_keyword_coverage(final_tex, tokens)
    return final_tex, cov, history


# ============================================================
# ➕ Add experience bullets (truthful) until just under 1 page
# ============================================================

async def gpt_propose_additional_bullets(jd_text: str, role_text_plain: str, current_plain_bullets: List[str], max_new: int = 2) -> List[str]:
    """
    Ask GPT for up to `max_new` additional bullets derived from the SAME truthful content.
    No new claims; rephrase/split/quantify existing achievements aligned to JD keywords.
    """
    example = '{"bullets":["…","…"]}'
    prompt = (
        "You will propose extra resume bullets for a role to improve JD fit.\n"
        f"Return STRICT JSON ONLY: {example}\n"
        f"max_new={max_new}\n"
        "Rules:\n"
        "- Derive bullets ONLY from the SAME truthful role content below; do NOT invent projects, tools, or claims.\n"
        "- You may split an existing bullet into two distinct impacts, add specific metrics, or highlight JD keywords actually used.\n"
        "- Concise, past-tense single sentences; no first-person.\n\n"
        "JOB DESCRIPTION (focus keywords, tasks):\n"
        f"{jd_text}\n\n"
        "ROLE CONTEXT (plain text):\n"
        f"{role_text_plain}\n\n"
        "CURRENT BULLETS:\n" + "\n".join(f"- {b}" for b in current_plain_bullets)
    )
    data = await gpt_json(prompt, temperature=0.2)
    out = data.get("bullets", []) if isinstance(data, dict) else []
    out = [latex_escape_text(s) for s in out if str(s).strip()]
    return out[:max_new]

async def add_experience_until_one_page(tex_content: str, jd_text: str, max_total_new: int = 6, max_new_per_block: int = 2) -> Tuple[str, int]:
    """
    Inserts additional \resumeItem bullets one-by-one across Experience/Projects blocks,
    compiling after each insert and stopping right before exceeding 1 page.
    Returns (new_tex, added_count).
    """
    added = 0
    def compile_pages(s: str) -> int:
        rendered = render_final_tex(s)
        pdf = compile_latex_safely(rendered)
        return _pdf_page_count(pdf)

    for sec_name in ["Experience", "Projects"]:
        while added < max_total_new:
            pat = section_rx(sec_name)
            m = pat.search(tex_content)
            if not m: break
            section = m.group(1)
            s_tag, e_tag = r"\resumeItemListStart", r"\resumeItemListEnd"

            # iterate over each itemize block inside the section
            idx = 0
            changed_any_block = False
            while added < max_total_new:
                a = section.find(s_tag, idx)
                if a < 0: break
                b = section.find(e_tag, a)
                if b < 0: break
                block = section[a:b]

                # prepare plain context & current bullets
                items = find_resume_items(block)
                current_bullets_plain = [strip_all_macros_keep_text(block[op + 1:cl]) for (_s, op, cl, _e) in items]
                role_context_plain = strip_all_macros_keep_text(block)

                # ask GPT for up to K new bullets for this block
                proposals = await gpt_propose_additional_bullets(jd_text, role_context_plain, current_bullets_plain, max_new=max_new_per_block)
                if not proposals:
                    idx = b + len(e_tag); continue

                # Try proposals one by one with compile checks
                for p in proposals:
                    candidate_block = block[:-0]  # copy
                    candidate_block = candidate_block + f"\n  \\resumeItem{{{p}}}"
                    candidate_section = section[:a] + candidate_block + section[b:]
                    candidate_tex = tex_content[:m.start()] + candidate_section + tex_content[m.end():]

                    pages = compile_pages(candidate_tex)
                    if pages <= 1:
                        tex_content = candidate_tex
                        section = candidate_section
                        added += 1
                        changed_any_block = True
                        log_event(f"➕ [EXPAND] Inserted extra bullet (now total +{added}); pages={pages}")
                        if added >= max_total_new:
                            break
                    else:
                        log_event("⛔ [EXPAND] Insertion would exceed 1 page — skipped this bullet.")
                        break
                idx = section.find(e_tag, a) + len(e_tag)
            if not changed_any_block:
                break
    return tex_content, added

# ============================================================
# 🚀 Endpoint (iterate to ≥90% keyword coverage, humanize once after)
# ============================================================

@router.post("/optimize")
async def optimize_endpoint(
    jd_text: str = Form(...),
    use_humanize: bool = Form(False),
    base_resume_tex: Optional[UploadFile] = None,  # now optional
):
    try:
        # ---- Load base .tex (upload if provided, else server default) ----
        raw_tex: str = ""
        if base_resume_tex is not None:
            tex_bytes = await base_resume_tex.read()
            if tex_bytes:
                tex = tex_bytes.decode("utf-8", errors="ignore")
                raw_tex = secure_tex_input(base_resume_tex.filename or "upload.tex", tex)

        if not raw_tex:
            default_path = getattr(config, "DEFAULT_BASE_RESUME", None)
            if not default_path or not default_path.exists():
                raise HTTPException(
                    status_code=500,
                    detail=f"Default base resume not found at {default_path}"
                )
            raw_tex = default_path.read_text(encoding="utf-8")
            log_event(f"📄 Using server default base: {default_path}")

        # ---- Core pipeline ----
        company_name, role = await extract_company_role(jd_text)
        optimized_tex = await optimize_resume_latex(raw_tex, jd_text)

        optimized_tex, coverage_report, coverage_history = await refine_resume_to_keyword_coverage(
            optimized_tex, jd_text, min_ratio=0.99, max_rounds=12
        )

        # If still <99%, try adding a few bullets but keep 1 page
        if coverage_report["ratio"] < 0.99:
            optimized_tex, added = await add_experience_until_one_page(
                optimized_tex, jd_text, max_total_new=6, max_new_per_block=2
            )
            if added > 0:
                optimized_tex = await _rebuild_skills_safely(optimized_tex, jd_text)
                tokens = await get_coverage_targets_from_jd(jd_text)
                coverage_report = compute_keyword_coverage(optimized_tex, tokens)
                coverage_history.append({
                    "round": "expand",
                    "coverage": coverage_report["ratio"],
                    "missing": coverage_report["missing"][:40]
                })

        # Always rebuild Skills once more before compile
        optimized_tex = await _rebuild_skills_safely(optimized_tex, jd_text)
        log_event("🔧 [SKILLS] Final rebuild before compile")

        # ---------- Compile base ----------
        final_tex = render_final_tex(optimized_tex)
        pdf_bytes_original = compile_latex_safely(final_tex)
        base_pages = _pdf_page_count(pdf_bytes_original)
        log_event(f"📄 Base PDF pages: {base_pages}")

        # ---------- Trim Achievements until 1 page (saving each trim) ----------
        job_dir = config.DATA_DIR / "Job Resumes"
        job_dir.mkdir(parents=True, exist_ok=True)
        safe_company, safe_role = safe_filename(company_name), safe_filename(role)
        saved_paths: List[str] = []

        MAX_TRIMS = 50
        cur_tex = optimized_tex
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
            next_tex_rendered = render_final_tex(next_tex)
            next_pdf_bytes = compile_latex_safely(next_tex_rendered)
            next_pages = _pdf_page_count(next_pdf_bytes)
            log_event(f"📄 [TRIM {trim_idx}] Base pages now: {next_pages}")
            if next_pdf_bytes:
                p = job_dir / f"Sri_Akash_Kadali_Resume_{safe_company}_{safe_role}_Trim{trim_idx}.pdf"
                p.write_bytes(next_pdf_bytes)
                saved_paths.append(str(p))
                log_event(f"💾 [SAVE] Trim {trim_idx} base PDF → {p}")
            cur_tex, cur_pdf_bytes, cur_pages = next_tex, next_pdf_bytes, next_pages
            if cur_pages <= 1:
                log_event(f"✅ Fits on one page after {trim_idx} trims.")
                break

        # ---------- Humanize ONCE if requested and ≥90% coverage ----------
        pdf_bytes_humanized: Optional[bytes] = None
        humanized_tex: Optional[str] = None
        did_humanize = False

        if use_humanize and coverage_report["ratio"] >= 0.90:
            did_humanize = True
            humanized_tex = await humanize_experience_bullets(cur_tex)
            humanized_tex_rendered = render_final_tex(humanized_tex)
            pdf_bytes_humanized = compile_latex_safely(humanized_tex_rendered)
            # If humanized >1 page, mirror trim loop
            h_pages = _pdf_page_count(pdf_bytes_humanized)
            trim_h_idx = 0
            while h_pages > 1 and trim_h_idx < MAX_TRIMS:
                next_h_tex, _ = remove_one_achievement_bullet(humanized_tex)
                h_rendered = render_final_tex(next_h_tex)
                h_pdf = compile_latex_safely(h_rendered)
                if h_pdf:
                    p = job_dir / f"Sri_Akash_Kadali_Resume_{safe_company}_{safe_role}_Trim{trim_idx}_Humanized.pdf"
                    p.write_bytes(h_pdf)
                    saved_paths.append(str(p))
                humanized_tex, pdf_bytes_humanized = next_h_tex, h_pdf
                h_pages = _pdf_page_count(pdf_bytes_humanized)
                trim_h_idx += 1

        # ---------- Save final outputs ----------
        if cur_pdf_bytes:
            p = job_dir / f"Sri_Akash_Kadali_Resume_{safe_company}_{safe_role}.pdf"
            p.write_bytes(cur_pdf_bytes)
            saved_paths.append(str(p))
            log_event(f"💾 [SAVE] Original PDF → {p}")
        if did_humanize and pdf_bytes_humanized:
            p = job_dir / f"Sri_Akash_Kadali_Resume_{safe_company}_{safe_role}_Humanized.pdf"
            p.write_bytes(pdf_bytes_humanized)
            saved_paths.append(str(p))
            log_event(f"💾 [SAVE] Humanized PDF → {p}")
        elif use_humanize and coverage_report["ratio"] >= 0.90 and humanized_tex and not pdf_bytes_humanized:
            t = job_dir / f"FAILED_Humanized_{safe_company}_{safe_role}.tex"
            t.write_text(humanized_tex, encoding="utf-8")
            log_event(f"🧾 [DEBUG] Saved failed humanized LaTeX → {t}")

        log_event(f"🟩 [PIPELINE] Completed — PDFs saved: {len(saved_paths)}")
        return JSONResponse({
            "tex_string": render_final_tex(cur_tex),
            "pdf_base64": base64.b64encode(cur_pdf_bytes or b"").decode("ascii"),
            "pdf_base64_humanized": base64.b64encode(pdf_bytes_humanized or b"").decode("ascii") if (did_humanize and pdf_bytes_humanized) else None,
            "company_name": company_name,
            "role": role,
            "saved_paths": saved_paths,
            "coverage_ratio": coverage_report["ratio"],
            "coverage_present": coverage_report["present"],
            "coverage_missing": coverage_report["missing"],
            "coverage_history": coverage_history,
            "humanized": did_humanize,
        })
    except Exception as e:
        log_event(f"💥 [PIPELINE] Optimization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
