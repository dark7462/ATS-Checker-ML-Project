# Matchspace — JD–Resume Skill Matcher

A local two-screen app: upload a job description (`.txt`) and a selectable-text resume (`.pdf`), then explore the skill matches on an animated, rotatable 3D map. The score uses the embedding vectors in their original dimensions. The 3D map is a PCA projection for display only.

## Run the app

From this repository's root:

```bash
./start.sh
```

Open the local address printed by the script (normally [http://127.0.0.1:8000](http://127.0.0.1:8000); it chooses the next free port through 8010 if needed). The script sets up a Python 3.10+ environment and dependencies if needed, then starts the server. The same server handles the API and frontend, so there is no separate frontend process or Node build. Press Ctrl+C to stop it. The first analysis may download the pretrained embedding model if it is not already cached. Files are processed in memory and are not saved by the app.

The JD must be UTF-8 `.txt` (up to 250 KB). The resume must be a selectable-text PDF (up to 5 MB); image-only PDFs need OCR, which is not included. The extractor recognizes a curated list of technical skills in `matcher.py`, including SRE concepts such as automation, troubleshooting, incident management, observability, Bash, and containerization. PDF text is read in layout mode so multiword skills stay together. If the JD has a `Required Qualifications` or `Requirements` section, that section takes priority. Otherwise, a named technical-skills section is used when present. Review the extracted labels because unlisted or ambiguous skills can be missed. An explanatory article is not a substitute for a specific employer's job description.

## How scoring works

Each distinct JD skill and resume skill is embedded with `sentence-transformers/all-MiniLM-L6-v2`. Opaque abbreviations such as `ML` and `K8s` are expanded before embedding so they can match their full names; Docker is embedded with containerization context to allow a partial conceptual match. Visible labels stay as uploaded. The matcher compares complete vectors with cosine similarity. Each resume skill can match at most one JD skill, and the pairing maximizes total points. Re-run notebook 1 after a matcher update to regenerate stored vectors.

For each pair, `credit = clamp((cosine - 0.60) / 0.40, 0, 1)`. Similarity at or below `0.60` earns zero; identical vectors earn one point. The overall score is `100 × total credit / number of JD skills`. For example, the local model gave React.js ↔ React a cosine of about `0.883`, which earns about `0.71` points. This is a calibrated score for this model, not a probability of hiring or a universal semantic-match percentage. The cutoff is intentionally conservative because unrelated short labels can be deceptively similar.

The result screen draws JD skills in blue, resume skills in red, and scored pairs as purple connections and midpoint markers. The projection can distort distances, so purple is determined by the full-vector score, never by whether two screen dots literally overlap. Drag to rotate, scroll to zoom, pause rotation, and hover to inspect points.

## Notebooks

The original notebook workflow remains available: place files at `input/JD.txt` and `input/resume.pdf`, run `01_extract_and_store.ipynb`, then `02_match_and_score.ipynb`. Extracted vectors are saved to `output/extracted.json`; the score is saved to `output/score.json`. Run notebooks from the repository root.

## Checks

```bash
my-venv/bin/python -m unittest discover -s tests -v
node --test frontend/*.test.mjs
node --check frontend/app.js
```
