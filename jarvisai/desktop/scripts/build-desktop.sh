#!/usr/bin/env bash
# Build installers for the current host OS (and optionally cross-build Windows on CI).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
TARGET="${1:-current}"

echo "==> Building frontend"
(
  cd frontend
  export CI=true
  corepack prepare pnpm@11.25.0 --activate
  pnpm install --frozen-lockfile
  pnpm build
)

echo "==> Staging frontend into desktop/resources/frontend"
rm -rf desktop/resources/frontend
mkdir -p desktop/resources/frontend
cp -R frontend/dist/. desktop/resources/frontend/

echo "==> Building Python sidecar"
bash desktop/scripts/build-sidecar.sh

# Ensure a tray/app icon exists
if [[ ! -f desktop/resources/icon.png ]]; then
  python3 - <<'PY'
from pathlib import Path
import struct, zlib

def chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)

# Solid signal-red 64x64 PNG
w = h = 64
raw = b''.join(b'\x00' + (b'\xf0\x18\x3c\xff' * w) for _ in range(h))
ihdr = struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)
png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')
Path('desktop/resources/icon.png').write_bytes(png)
print('Wrote desktop/resources/icon.png')
PY
fi

echo "==> Installing Electron deps"
(
  cd desktop
  npm install
)

case "$TARGET" in
  mac|macos)
    (cd desktop && npm run dist:mac)
    ;;
  win|windows)
    (cd desktop && npm run dist:win)
    ;;
  both)
    (cd desktop && npm run dist)
    ;;
  current|*)
    if [[ "$(uname -s)" == "Darwin" ]]; then
      (cd desktop && npm run dist:mac)
    else
      (cd desktop && npm run dist:win)
    fi
    ;;
esac

echo "Artifacts in desktop/release/"
ls -la desktop/release/ || true
