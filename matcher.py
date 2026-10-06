"""Extraction, storage, and conservative JD-to-resume scoring for v1."""

from __future__ import annotations

import json
import re
from pathlib import Path


SKILL_ALIASES = {
    "react": ("react", "react.js", "reactjs"),
    "express": ("express", "express.js", "expressjs"),
    "aws": ("aws", "amazon web services"),
    "azure": ("azure", "microsoft azure"),
    "gcp": ("gcp", "google cloud platform", "google cloud"),
    "javascript": ("javascript", "js"),
    "typescript": ("typescript", "ts"),
    "node.js": ("node.js", "nodejs"),
    "python": ("python",),
    "java": ("java",),
    "sql": ("sql",),
    "postgresql": ("postgresql", "postgres"),
    "mongodb": ("mongodb",),
    "docker": ("docker",),
    "kubernetes": ("kubernetes", "k8s"),
    "git": ("git",),
    "linux": ("linux",),
    "html": ("html",),
    "css": ("css",),
    "rest api": ("rest api", "restful api", "rest apis", "restful apis"),
    "machine learning": ("machine learning", "ml"),
    "nlp": ("nlp", "natural language processing"),
    "tensorflow": ("tensorflow",),
    "pytorch": ("pytorch",),
    "scikit-learn": ("scikit-learn", "sklearn"),
    "pandas": ("pandas",),
    "numpy": ("numpy",),
    "spark": ("spark", "apache spark"),
    "redis": ("redis",),
    "graphql": ("graphql",),
    "ci/cd": ("ci/cd", "continuous integration", "continuous deployment"),
    "agile": ("agile",),
    "scrum": ("scrum",),
    "c++": ("c++",),
    "data structures": ("data structures",),
    "algorithms": ("algorithms",),
    "object-oriented programming": ("object-oriented programming", "object oriented programming", "object-oriented language", "oop"),
}
RELATED_SKILLS = {frozenset(("aws", "azure")), frozenset(("aws", "gcp")), frozenset(("azure", "gcp"))}
_ALIASES = sorted(
    ((alias, canonical) for canonical, aliases in SKILL_ALIASES.items() for alias in aliases),
    key=lambda pair: len(pair[0]), reverse=True,
)
_CONTACT = re.compile(r"@|linkedin\.com|github\.com|https?://|\+\d[\d\s-]{7,}", re.I)


def read_jd(path: str | Path) -> str:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Cannot parse JD text file {path}: {exc}") from exc
    if not text.strip():
        raise ValueError(f"Cannot parse JD text file {path}: it is empty.")
    return text


def focus_jd_text(text: str, required_only: bool = True) -> str:
    """Use the required-qualification section of a copied posting when present."""
    lines = text.splitlines()
    if required_only:
        required = [i for i, line in enumerate(lines) if re.match(r"^(?:required qualifications|requirements)\s*:?$", line.strip(), re.I)]
        if required:
            start = required[0] + 1
            stop = re.compile(r"^(?:preferred qualifications|nice to have|this position will be open|microsoft is an equal opportunity employer|insights from previous hires|similar jobs)\b", re.I)
            end = next((i for i in range(start, len(lines)) if stop.match(lines[i].strip())), len(lines))
            return "\n".join(lines[start:end])
    starts = [i for i, line in enumerate(lines) if line.strip().lower() == "responsibilities"]
    if not starts:
        return text
    start = starts[0]
    cutoff = re.compile(r"^(?:this position will be open|microsoft is an equal opportunity employer|insights from previous hires|similar jobs)\b", re.I)
    end = next((i for i in range(start + 1, len(lines)) if cutoff.match(lines[i].strip())), len(lines))
    return "\n".join(lines[start:end])


def read_resume_pdf(path: str | Path) -> str:
    path = Path(path)
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise ValueError(f"Cannot parse resume PDF {path}: {exc}") from exc
    if not text.strip():
        raise ValueError(f"Cannot parse resume PDF {path}: no selectable text found. Image-only PDFs need OCR, which v1 does not support.")
    return text


def _skill_hits(text: str):
    hits = []
    occupied = []
    for alias, canonical in _ALIASES:
        pattern = re.compile(r"(?<![\w])" + re.escape(alias) + r"(?![\w])", re.I)
        for match in pattern.finditer(text):
            if not any(match.start() < end and match.end() > start for start, end in occupied):
                hits.append((match.start(), match.end(), canonical, match.group()))
                occupied.append((match.start(), match.end()))
    return sorted(hits)


def extract_items(text: str, source: str = "jd") -> list[dict]:
    """Extract distinct named technical skills; never score full sentences."""
    if source not in {"jd", "resume"}:
        raise ValueError("source must be 'jd' or 'resume'")
    items = {}
    for raw in text.splitlines():
        if source == "resume" and _CONTACT.search(raw):
            continue
        for _, _, canonical, display in _skill_hits(raw):
            key = ("skill", canonical)
            items.setdefault(key, {"kind": "skill", "label": display, "canonical": canonical})
    return list(items.values())


def embed_items(items: list[dict], model) -> list[dict]:
    if not items:
        return items
    vectors = model.encode([item["label"] for item in items], normalize_embeddings=True)
    return [{**item, "vector": vector.tolist()} for item, vector in zip(items, vectors)]


def load_embedding_model():
    """Prefer the local cache, downloading the pretrained model on first use."""
    from sentence_transformers import SentenceTransformer
    name = "sentence-transformers/all-MiniLM-L6-v2"
    try:
        return SentenceTransformer(name, local_files_only=True)
    except (OSError, ValueError):
        return SentenceTransformer(name)


def save_extractions(jd_items: list[dict], resume_items: list[dict], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "jd": jd_items, "resume": resume_items}, indent=2, ensure_ascii=False), encoding="utf-8")


def load_extractions(path: str | Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data["schema_version"] != 1 or not isinstance(data["jd"], list) or not isinstance(data["resume"], list):
            raise ValueError("wrong schema")
        if not data["jd"]:
            raise ValueError("no JD items were extracted")
        for item in data["jd"] + data["resume"]:
            if not all(key in item for key in ("kind", "label", "canonical", "vector")):
                raise ValueError("an extracted item is incomplete")
        return data
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Cannot load extracted data from {path}: {exc}") from exc


def _credit(jd: dict, resume: dict) -> float:
    if jd["kind"] != resume["kind"]:
        return 0.0
    if jd["canonical"] == resume["canonical"]:
        return 1.0
    if jd["kind"] == "skill" and frozenset((jd["canonical"], resume["canonical"])) in RELATED_SKILLS:
        return 0.5
    return 0.0


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / ((sum(x*x for x in a) * sum(y*y for y in b)) ** 0.5 or 1)


def score(jd_items: list[dict], resume_items: list[dict], suggestion_threshold: float = 0.4) -> dict:
    if not jd_items:
        raise ValueError("Cannot score: no JD items were extracted.")
    # Deduplicate input defensively, even if scoring is called without notebook 1.
    jd_items = list({(x["kind"], x["canonical"]): x for x in reversed(jd_items)}.values())[::-1]
    resume_items = list({(x["kind"], x["canonical"]): x for x in reversed(resume_items)}.values())[::-1]
    available = set(range(len(resume_items)))
    matched = []
    unmatched = []
    pending = list(jd_items)
    # Reserve exact matches before any related skill can consume a resume item.
    for desired_credit in (1.0, 0.5):
        remaining = []
        for jd in pending:
            candidates = [index for index in available if _credit(jd, resume_items[index]) == desired_credit]
            if candidates:
                index = max(candidates, key=lambda i: _cosine(jd.get("vector", []), resume_items[i].get("vector", [])))
                available.remove(index)
                matched.append({"jd": jd["label"], "resume": resume_items[index]["label"], "credit": desired_credit})
            else:
                remaining.append(jd)
        pending = remaining
    unmatched = pending
    suggestions = []
    for jd in unmatched:
        candidates = [(resume, _cosine(jd.get("vector", []), resume.get("vector", []))) for resume in resume_items if resume["kind"] == jd["kind"] and _credit(jd, resume) == 0]
        if candidates:
            resume, similarity = max(candidates, key=lambda pair: pair[1])
            if similarity >= suggestion_threshold:
                suggestions.append({"jd": jd["label"], "resume": resume["label"], "similarity": round(similarity, 3)})
    points = sum(row["credit"] for row in matched)
    return {"score": round(100 * points / len(jd_items), 2), "points": points, "total": len(jd_items), "matched": [x for x in matched if x["credit"] == 1], "partial": [x for x in matched if x["credit"] == 0.5], "unmatched": [x["label"] for x in unmatched], "suggestions": suggestions}
