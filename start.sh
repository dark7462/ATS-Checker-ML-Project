#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ ! -e my-venv ]]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv my-venv
  else
    python3 -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10 or newer is required"'
    python3 -m venv my-venv
  fi
fi

if [[ ! -x my-venv/bin/python ]]; then
  echo "The my-venv environment is incomplete. Recreate it, then run ./start.sh again." >&2
  exit 1
fi

if ! my-venv/bin/python -c 'import importlib.util; assert all(importlib.util.find_spec(name) for name in ("sentence_transformers", "pypdf", "numpy", "scipy"))' >/dev/null 2>&1; then
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python my-venv/bin/python -r requirements.txt
  else
    my-venv/bin/python -m pip install -r requirements.txt
  fi
fi

if [[ -z "${PORT:-}" ]]; then
  PORT="$(my-venv/bin/python - <<'PY'
import socket

for port in range(8000, 8011):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            continue
        print(port)
        break
else:
    raise SystemExit("No free local port from 8000 to 8010.")
PY
)"
  export PORT
fi

echo "Starting Matchspace at http://127.0.0.1:$PORT"
exec my-venv/bin/python server.py
