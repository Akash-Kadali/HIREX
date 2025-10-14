"""
HIREX • api/latex_parse.py
Lightweight Resume Parser (Raw-Preserve Mode)
Extracts sections from LaTeX or text resumes with zero cleaning or normalization.
Purpose: Provide unaltered LaTeX/text blocks for AI-based optimization.
Author: Sri Akash Kadali
"""

import re
from typing import Dict, List


# ============================================================
# ⚙️ Section Extraction Utilities
# ============================================================
def extract_section(tex: str, section_name: str) -> str:
    """
    Extracts raw LaTeX section content between \section{<section_name>}
    or equivalent text headers. No stripping or cleanup is applied.
    """
    pattern = (
        rf"(?:\\section\{{{re.escape(section_name)}\}}"
        rf"|^{section_name}\s*$)(.*?)(?=\\section|\n[A-Z][A-Za-z ]+\n|$)"
    )
    match = re.search(pattern, tex, flags=re.DOTALL | re.IGNORECASE | re.MULTILINE)
    return match.group(1) if match else ""


# ============================================================
# 🧠 Main Parser (No Cleaning, No Normalization)
# ============================================================
def parse_latex_resume(tex_content: str) -> Dict:
    """
    Parses a LaTeX or plain-text resume into structured JSON form.
    All text is preserved as-is (no trimming, reformatting, or escaping).

    Extracts:
      - Education
      - Skills
      - Experience
      - Projects
      - Achievements
    """
    tex = tex_content.replace("\r", "")

    education_block = extract_section(tex, "Education")
    skills_block = extract_section(tex, "Skills")
    experience_block = extract_section(tex, "Experience")
    projects_block = extract_section(tex, "Projects")
    achievements_block = extract_section(tex, "Achievements")

    return {
        "education": _extract_bullets(education_block) or _split_lines(education_block),
        "skills": _parse_skills(skills_block),
        "experience": _parse_experience(experience_block),
        "projects": _parse_experience(projects_block),
        "achievements": _extract_bullets(achievements_block) or _split_lines(achievements_block),
    }


# ============================================================
# 🧩 Helper Parsers (Preserve Original Text)
# ============================================================
def _split_lines(block: str) -> List[str]:
    """Split section into lines — keeps all original spacing and symbols."""
    return [ln for ln in block.splitlines() if ln.strip()]


def _extract_bullets(section: str) -> List[str]:
    """Extract bullet lines without reformatting or cleanup."""
    bullets = re.findall(r"\\item\s+(.*)", section)
    if not bullets:
        bullets = re.findall(r"[-•]\s+(.*)", section)
    return [b for b in bullets if b.strip()]


def _parse_experience(section: str) -> List[Dict]:
    """
    Extract Experience/Projects entries minimally.
    Preserves LaTeX formatting and avoids stripping or normalization.
    """
    entries = []

    # LaTeX pattern: company/title/date + itemize block
    pattern = re.compile(
        r"\\textbf\{(.*?)\}\s*\\hfill\s*\\textit\{(.*?)\}\s*"
        r"(?:\\hfill\s*([^\n]+))?(.*?)\\end\{itemize\}",
        flags=re.DOTALL,
    )
    matches = re.findall(pattern, section)
    if matches:
        for company, title, date, rest in matches:
            bullets = _extract_bullets(rest)
            entries.append({
                "company": company,
                "title": title,
                "date": date,
                "bullets": bullets,
            })
        return entries

    # Plain text fallback (preserves spacing)
    blocks = re.split(r"\n(?=[A-Z].*\d{4})", section)
    for block in blocks:
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue

        header = lines[0]
        date_match = re.search(r"\b\d{4}.*\d{4}\b", header)
        date = date_match.group(0) if date_match else ""
        title, company = "", ""
        if " at " in header:
            title, company = header.split(" at ", 1)
        elif "-" in header:
            parts = header.split("-", 1)
            title = parts[0]
            company = parts[1]

        bullets = [ln for ln in lines[1:] if not re.match(r"^[A-Z][A-Za-z ]+$", ln)]
        entries.append({
            "company": company or "Unknown",
            "title": title or "Role",
            "date": date,
            "bullets": bullets,
        })
    return entries


def _parse_skills(section: str) -> Dict[str, List[str]]:
    """Extracts Skills lines as-is (no lowercase, trimming, or formatting)."""
    lines = [l for l in section.splitlines() if l.strip()]
    skills_dict: Dict[str, List[str]] = {}
    for line in lines:
        if ":" in line:
            key, val = line.split(":", 1)
            values = [v.strip() for v in val.split(",") if v.strip()]
            if values:
                skills_dict[key.strip()] = values
    return skills_dict


# ============================================================
# 🧪 Local Test
# ============================================================
if __name__ == "__main__":
    sample_resume = r"""
    \documentclass{article}
    \begin{document}

    %-----------EDUCATION-----------
    \section{Education}
    University of Maryland, College Park, United States CGPA: 3.55/4
    Master of Science in Applied Machine Learning August 2024 - May 2026
    • Relevant Coursework:

    %-----------EXPERIENCE-----------
    \section{Experience}
    \textbf{Machine Learning Intern} \hfill \textit{IIT Indore} \hfill May 2023 – Dec 2023
    \begin{itemize}
      \item Developed DeBERTa-based architecture for hate-speech detection.
      \item Improved accuracy using contrastive learning.
      \item Enhanced features with emotion embeddings.
    \end{itemize}

    \end{document}
    """

    from pprint import pprint
    pprint(parse_latex_resume(sample_resume))
