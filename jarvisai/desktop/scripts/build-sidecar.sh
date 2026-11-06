#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

PYTHON=""
for candidate in \
  "${ROOT}/.venv/bin/python3" \
  "${ROOT}/.venv/bin/python" \
  "${ROOT}/.venv/Scripts/python.exe" \
  "${ROOT}/.venv/Scripts/python" \
  "$(command -v python3 || true)" \
  "$(command -v python || true)"
do
  if [[ -n "$candidate" && -x "$candidate" ]]; then
    PYTHON="$candidate"
    break
  fi
  # Windows Git Bash: -x can fail on .exe; -f is enough
  if [[ -n "$candidate" && -f "$candidate" ]]; then
    PYTHON="$candidate"
    break
  fi
done
if [[ -z "$PYTHON" ]]; then
  echo "Python not found for sidecar build." >&2
  exit 1
fi

"$PYTHON" -m pip install -q -r requirements.txt 'pyinstaller>=6.3'
"$PYTHON" -m PyInstaller desktop/jarvis-sidecar.spec --noconfirm --distpath desktop/resources/sidecar --workpath desktop/build/pyinstaller

# Flatten one-file output into resources/sidecar/
mkdir -p desktop/resources/sidecar
if [[ -f desktop/resources/sidecar/jarvis-sidecar ]]; then
  chmod +x desktop/resources/sidecar/jarvis-sidecar
elif [[ -f desktop/resources/sidecar/jarvis-sidecar.exe ]]; then
  true
else
  echo "Sidecar binary not found after PyInstaller build." >&2
  exit 1
fi

echo "Sidecar ready under desktop/resources/sidecar/"
