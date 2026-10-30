"""Extraction, storage, and conservative JD-to-resume scoring for v1."""

from __future__ import annotations

import json
import re
from io import BytesIO
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
    "bash": ("bash", "shell scripting"),
    "automation": ("automation", "process automation"),
    "troubleshooting": ("troubleshooting", "troubleshoot"),
    "containerization": ("containerization", "containerisation", "containerized", "containerised"),
    "monitoring": ("monitoring", "system monitoring"),
    "logging": ("logging", "log management"),
    "observability": ("observability",),
    "incident management": ("incident management", "incident response"),
    "root cause analysis": ("root cause analysis", "rca"),
    "postmortem": ("postmortem", "post-mortem", "postmortems", "pir"),
    "disaster recovery": ("disaster recovery",),
    "on-call": ("on-call", "on call"),
    "slo": ("slo", "slos", "service level objective", "service level objectives"),
    "terraform": ("terraform",),
    "prometheus": ("prometheus",),
    "grafana": ("grafana",),
    "splunk": ("splunk",),
    "gitops": ("gitops",),
    "jira": ("jira",),
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
# Short labels can be semantically weak in the embedding model. Expand only
# opaque aliases; ordinary variants such as React.js/React keep measured distance.
EMBEDDING_EXPANSIONS = {
    "aws": "amazon web services",
    "ml": "machine learning",
    "ts": "typescript",
    "k8s": "kubernetes",
    "sklearn": "scikit-learn",
    "oop": "object-oriented programming",
    "nlp": "natural language processing",
    "gcp": "google cloud platform",
    "spark": "apache spark",
    "docker": "Docker containerization",
    "ci/cd": "continuous integration and continuous deployment",
    "continuous integration": "continuous integration and continuous deployment",
    "continuous deployment": "continuous integration and continuous deployment",
    "rca": "root cause analysis",
    "pir": "postmortem",
    "slo": "service level objective",
    "slos": "service level objective",
}
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
    """Prefer explicit required qualifications or a named technical-skills section."""
    lines = text.splitlines()
    if required_only:
        required = [i for i, line in enumerate(lines) if re.match(r"^(?:required qualifications|requirements)\s*:?$", line.strip(), re.I)]
        if required:
            start = required[0] + 1
            stop = re.compile(r"^(?:preferred qualifications|nice to have|this position will be open|microsoft is an equal opportunity employer|insights from previous hires|similar jobs)\b", re.I)
            end = next((i for i in range(start, len(lines)) if stop.match(lines[i].strip())), len(lines))
            return "\n".join(lines[start:end])
    skill_head = re.compile(r"^(?:(?:technical|key|core) skills|.+\bskills to (?:kick-start|start)\b.+)\s*:?$", re.I)
    skill_sections = [i for i, line in enumerate(lines) if skill_head.match(line.strip())]
    if skill_sections:
        start = skill_sections[0] + 1
        stop = re.compile(r"^(?:ready to start|apply now|similar jobs|see an error)\b", re.I)
        end = next((i for i in range(start, len(lines)) if stop.match(lines[i].strip())), len(lines))
        editorial_link = re.compile(r"^\((?:related reading|learn (?:more )?about)\b", re.I)
        return "\n".join(line for line in lines[start:end] if not editorial_link.match(line.strip()))
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
        text = _pdf_text(reader)
    except Exception as exc:
        raise ValueError(f"Cannot parse resume PDF {path}: {exc}") from exc
    if not text.strip():
        raise ValueError(f"Cannot parse resume PDF {path}: no selectable text found. Image-only PDFs need OCR, which v1 does not support.")
    return text


def read_resume_pdf_bytes(data: bytes) -> str:
    """Extract selectable text from an uploaded PDF without saving the file."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(data))
        text = _pdf_text(reader)
    except Exception as exc:
        raise ValueError(f"Cannot parse resume PDF: {exc}") from exc
    if not text.strip():
        raise ValueError("Cannot parse resume PDF: no selectable text found. Image-only PDFs need OCR, which v1 does not support.")
    return text


def _pdf_text(reader) -> str:
    pages = []
    for page in reader.pages:
        try:
            text = page.extract_text(extraction_mode="layout")
        except TypeError:
            text = page.extract_text()
        pages.append("\n".join(" ".join(line.split()) for line in (text or "").splitlines()))
    return "\n".join(pages)


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
    labels = [EMBEDDING_EXPANSIONS.get(item["label"].casefold(), item["label"]) for item in items]
    vectors = model.encode(labels, normalize_embeddings=True)
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


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    length = (sum(x*x for x in a) * sum(y*y for y in b)) ** 0.5
    if not length:
        return 0.0
    return max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b)) / length))


def score(jd_items: list[dict], resume_items: list[dict], similarity_floor: float = 0.6) -> dict:
    """Score one-to-one skill pairs from full embedding cosine similarities.

    The floor is calibrated for the current short-label embedding model. A
    cosine at or below it earns zero; a cosine of 1 earns one point.
    """
    if not jd_items:
        raise ValueError("Cannot score: no JD items were extracted.")
    if not 0 <= similarity_floor < 1:
        raise ValueError("similarity_floor must be between 0 and 1.")
    import numpy as np
    from scipy.optimize import linear_sum_assignment

    # Deduplicate input defensively while keeping the first index for visual links.
    def unique(items):
        seen = set()
        output = []
        for item in items:
            key = (item["kind"], item["canonical"])
            if key not in seen:
                seen.add(key)
                output.append(item)
        return output

    jd_items = unique(jd_items)
    resume_items = unique(resume_items)
    matched = []
    raw_points = 0.0
    if resume_items:
        similarities = np.array([
            [_cosine(jd.get("vector", []), resume.get("vector", [])) if jd["kind"] == resume["kind"] else 0.0
             for resume in resume_items]
            for jd in jd_items
        ])
        credits = np.clip((similarities - similarity_floor) / (1 - similarity_floor), 0, 1)
        # Dummy columns let any JD skill remain unmatched without consuming a resume skill.
        costs = np.concatenate((-credits, np.zeros((len(jd_items), len(jd_items)))), axis=1)
        jd_indices, resume_indices = linear_sum_assignment(costs)
        for jd_index, resume_index in zip(jd_indices, resume_indices):
            if resume_index >= len(resume_items) or credits[jd_index, resume_index] <= 0:
                continue
            raw_points += float(credits[jd_index, resume_index])
            matched.append({
                "jd_index": int(jd_index), "resume_index": int(resume_index),
                "jd": jd_items[jd_index]["label"], "resume": resume_items[resume_index]["label"],
                "similarity": round(float(similarities[jd_index, resume_index]), 3),
                "credit": round(float(credits[jd_index, resume_index]), 4),
            })
    matched_indices = {row["jd_index"] for row in matched}
    return {
        "score": round(100 * raw_points / len(jd_items), 2),
        "points": round(raw_points, 4), "total": len(jd_items),
        "matched": matched,
        "unmatched": [item["label"] for index, item in enumerate(jd_items) if index not in matched_indices],
    }


def project_items(jd_items: list[dict], resume_items: list[dict]) -> dict:
    """Project both sets into the same three-dimensional PCA display space."""
    import numpy as np

    combined = jd_items + resume_items
    if not combined:
        return {"jd": [], "resume": []}
    vectors = np.asarray([item["vector"] for item in combined], dtype=float)
    if vectors.ndim != 2 or not np.isfinite(vectors).all():
        raise ValueError("Cannot project invalid embedding vectors.")
    centered = vectors - vectors.mean(axis=0)
    _, _, axes = np.linalg.svd(centered, full_matrices=False)
    projected = centered @ axes[:3].T
    projected = np.pad(projected, ((0, 0), (0, max(0, 3 - projected.shape[1]))))
    radius = np.max(np.linalg.norm(projected, axis=1))
    if radius:
        projected = 2.5 * projected / radius
    def make_points(items, start, source):
        return [
            {"id": f"{source}-{index}", "label": item["label"],
             "position": [round(float(value), 4) for value in projected[start + index]]}
            for index, item in enumerate(items)
        ]
    return {"jd": make_points(jd_items, 0, "jd"), "resume": make_points(resume_items, len(jd_items), "resume")}
