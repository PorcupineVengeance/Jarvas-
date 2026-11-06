# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the JARVIS desktop sidecar.

Build from jarvisai/:
  .venv/bin/pyinstaller desktop/jarvis-sidecar.spec --noconfirm
"""

from pathlib import Path

block_cipher = None
root = Path(SPECPATH).resolve().parent
backend = root / "backend"

a = Analysis(
    [str(root / "desktop" / "sidecar_entry.py")],
    pathex=[str(backend), str(root)],
    binaries=[],
    datas=[
        (str(backend / "app"), "backend/app"),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "app.main",
        "sqlalchemy.dialects.sqlite",
        "pydantic_settings",
        "ddgs",
        "multipart",
        "email_validator",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="jarvis-sidecar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
