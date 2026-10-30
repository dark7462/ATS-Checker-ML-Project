"""Local upload API and static frontend for the JD–resume vector matcher."""

from __future__ import annotations

import json
import logging
import os
import threading
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from matcher import (
    embed_items, extract_items, focus_jd_text, load_embedding_model,
    project_items, read_resume_pdf_bytes, score,
)


ROOT = Path(__file__).parent
FRONTEND = ROOT / "frontend"
MAX_JD_BYTES = 250_000
MAX_RESUME_BYTES = 5_000_000
MAX_REQUEST_BYTES = MAX_JD_BYTES + MAX_RESUME_BYTES + 20_000


class InputError(ValueError):
    """A file or its extracted content cannot be scored."""


def parse_multipart_upload(content_type: str, body: bytes) -> dict:
    if not content_type.lower().startswith("multipart/form-data;"):
        raise InputError("Upload must contain JD and resume files.")
    envelope = (f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n").encode() + body
    message = BytesParser(policy=policy.default).parsebytes(envelope)
    if not message.is_multipart():
        raise InputError("Invalid file upload.")
    files = {}
    for part in message.iter_parts():
        field = part.get_param("name", header="content-disposition")
        if field in {"jd", "resume"} and field not in files:
            files[field] = (part.get_filename() or "", part.get_payload(decode=True) or b"")
    if set(files) != {"jd", "resume"}:
        raise InputError("Upload both a JD .txt file and a resume PDF.")
    return files


def analyze_upload(jd_name: str, jd_bytes: bytes, resume_name: str, resume_bytes: bytes, model) -> dict:
    if Path(jd_name).suffix.lower() != ".txt":
        raise InputError("JD must be a .txt file.")
    if Path(resume_name).suffix.lower() != ".pdf":
        raise InputError("Resume must be a PDF file.")
    if len(jd_bytes) > MAX_JD_BYTES or len(resume_bytes) > MAX_RESUME_BYTES:
        raise InputError("One of the files is too large. Limit the JD to 250 KB and resume to 5 MB.")
    try:
        jd_text = jd_bytes.decode("utf-8-sig")
    except UnicodeError as exc:
        raise InputError("JD must contain UTF-8 text.") from exc
    if not jd_text.strip():
        raise InputError("JD file is empty.")
    if not resume_bytes:
        raise InputError("Resume PDF is empty.")
    try:
        resume_text = read_resume_pdf_bytes(resume_bytes)
    except ValueError as exc:
        raise InputError(str(exc)) from exc

    jd_items = extract_items(focus_jd_text(jd_text))
    resume_items = extract_items(resume_text, source="resume")
    if not jd_items:
        raise InputError("No supported technical skills found in the JD's qualifications or skills section.")
    if not hasattr(model, "encode"):
        model = model()
    jd_items = embed_items(jd_items, model)
    resume_items = embed_items(resume_items, model)
    return {
        **score(jd_items, resume_items),
        "points_3d": project_items(jd_items, resume_items),
        "resume_skill_count": len(resume_items),
    }


def make_server(address=("127.0.0.1", 8000), model_loader=load_embedding_model):
    model = None
    model_lock = threading.Lock()

    def get_model():
        nonlocal model
        with model_lock:
            if model is None:
                model = model_loader()
        return model

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, content_type: str):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, data: dict):
            self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            route = urlsplit(self.path).path
            assets = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/results": ("index.html", "text/html; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/scene.mjs": ("scene.mjs", "text/javascript; charset=utf-8"),
                "/score-format.mjs": ("score-format.mjs", "text/javascript; charset=utf-8"),
                "/styles.css": ("styles.css", "text/css; charset=utf-8"),
                "/favicon.svg": ("favicon.svg", "image/svg+xml"),
            }
            if route == "/api/health":
                self._json(200, {"status": "ok"})
                return
            asset = assets.get(route)
            if not asset:
                self._json(404, {"detail": "Not found."})
                return
            filename, content_type = asset
            self._send(200, (FRONTEND / filename).read_bytes(), content_type)

        def do_POST(self):
            if urlsplit(self.path).path != "/api/analyze":
                self._json(404, {"detail": "Not found."})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size <= 0:
                    raise InputError("Upload is empty.")
                if size > MAX_REQUEST_BYTES:
                    self._json(413, {"detail": "Upload is too large."})
                    return
                files = parse_multipart_upload(self.headers.get("Content-Type", ""), self.rfile.read(size))
                jd_name, jd_bytes = files["jd"]
                resume_name, resume_bytes = files["resume"]
                self._json(200, analyze_upload(jd_name, jd_bytes, resume_name, resume_bytes, get_model))
            except InputError as exc:
                self._json(400, {"detail": str(exc)})
            except (ValueError, TypeError):
                self._json(400, {"detail": "Invalid file upload."})
            except Exception:
                logging.exception("Analysis failed")
                self._json(500, {"detail": "Analysis failed. Please try again."})

    return ThreadingHTTPServer(address, Handler)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    server = make_server(("127.0.0.1", port))
    print(f"JD–Resume Matcher running at http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
