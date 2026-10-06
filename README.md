# JD–Resume Matcher (v1)

This local project extracts **technical skills only** from a job description and a selectable-text resume PDF. For a JD with a `Required Qualifications` section, only skills in that section count. It stores skill embeddings, then scores conservative matches out of 100.

## Setup

Use Python 3.10 or newer from the repository root. If you already created `my-venv` with uv, activate that environment; otherwise create one:

```bash
uv venv my-venv
source my-venv/bin/activate
python -m pip install -r requirements.txt
python -m jupyter lab
```

The sentence embedding model downloads automatically on the first run and is cached locally.

## Run

1. Place the JD in `input/JD.txt` (UTF-8 text) and the resume in `input/resume.pdf` (selectable text).
2. Run all cells in `01_extract_and_store.ipynb`. Inspect the displayed skill lists. Data, including vectors, is saved to `output/extracted.json`.
3. Run all cells in `02_match_and_score.ipynb`. Read the full, partial, and unmatched lists and the score. The same result is saved to `output/score.json`.

Run notebooks from the repository root so their relative paths resolve. The input and output folders are local and ignored by Git. If a file is absent, corrupt, empty, or the PDF has no selectable text, notebook 1 raises a clear parsing error. OCR is outside v1.

## Scoring

Each distinct **required JD technical skill** has equal weight. Exact normalized wording or a curated alias earns 1 point. AWS/Azure/GCP cross-platform matches earn 0.5 point. Other pairs earn 0. One resume skill can be used once, with full matches reserved before partial ones. Embedding similarity only suggests possible related skills for manual review; it awards no points. Score = `100 × points / required JD skill count`.

The skill alias and related-skill lists live in `matcher.py`. Preferred qualifications, eligibility statements, responsibilities, and full sentences do not enter this JD's score. Review the displayed lists: v1 uses a curated technical-skill vocabulary and may miss skills that have not been added to it.

Run dependency-free checks with `python -m unittest discover -s tests -v`.
# ATS-Checker-ML-Project
