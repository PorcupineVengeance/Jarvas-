# JARVIS Desktop

Installable macOS and Windows app that runs the JARVIS FastAPI backend locally and enables **permissioned** computer control (open apps/URLs/folders, screenshots) inside folders you authorize.

## Architecture

- **Electron** shell + system tray
- **Python FastAPI** sidecar (dev: local venv; release: PyInstaller binary)
- Same React UI as the web app, loaded from `http://127.0.0.1:<port>/`
- Preferences stored under the OS user-data directory (`desktop-settings.json`)

The hosted web app cannot control a laptop. Only this desktop build (or a trusted local `uvicorn` with `JARVIS_ENABLE_COMPUTER_CONTROL=true`) can.

## Develop

```bash
# from jarvisai/
# 1) Backend deps + frontend build
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd frontend && pnpm install && pnpm build && cd ..

# 2) Electron
cd desktop
npm install
npm run dev
```

`npm run dev` starts Electron, which launches uvicorn with `PYTHONPATH=backend` and `JARVIS_DESKTOP=1`.

## Build installers

```bash
# Current OS only (recommended — sidecar is OS-native)
bash desktop/scripts/build-desktop.sh

# Explicit targets
bash desktop/scripts/build-desktop.sh mac
bash desktop/scripts/build-desktop.sh win   # must run on Windows (or GitHub Actions)
```

Do **not** cross-build Windows from macOS for shipping: the Python sidecar is a native binary and will not run on the other OS. Use `.github/workflows/release-desktop.yml` (Actions → Release Desktop) to produce both `JARVIS-mac.dmg` and `JARVIS-win.exe`.

Artifacts land in `desktop/release/`:

- `JARVIS-mac.dmg`
- `JARVIS-win.exe`

### Publishing download links

1. Run the **Release Desktop** GitHub Action (or upload both installers to a GitHub Release / CDN).
2. Filenames must be `JARVIS-mac.dmg` and `JARVIS-win.exe`.
3. Set on the **web** deploy / local `.env`:

```bash
JARVIS_DESKTOP_DOWNLOAD_BASE=https://github.com/PorcupineVengeance/Jarvas-/releases/latest/download
```

Sign-in, Settings → Get Desktop, and Home “Get Desktop” then show macOS + Windows download buttons.

### Code signing

Unsigned builds are fine for personal use. For distribution outside your machine:

- **macOS:** Developer ID + notarization (`codesign`, `notarytool`)
- **Windows:** Authenticode certificate

This repo does not automate signing.

## First-run permissions

On first launch JARVIS Desktop enables computer control with:

- `~/Desktop`
- `~/Documents`
- `~/Downloads`

Change these anytime in **Settings → Desktop permissions**. Destructive tools still require confirmation.

## Safety

- Loopback-only API (`127.0.0.1`)
- Folder allow-list enforced by the backend
- Hosted/cloud JARVIS must keep `JARVIS_ENABLE_COMPUTER_CONTROL=false` and `JARVIS_DESKTOP=false`
