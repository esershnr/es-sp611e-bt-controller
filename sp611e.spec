# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: builds a single-file sp611e.exe.

Usage:
    pip install -e ".[build]"
    pyinstaller sp611e.spec

The web dashboard assets are bundled under sp611e_cli/web so that
server.WEB_DIR (Path(__file__).parent / "web") resolves inside the bundle.
"""

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ["src/sp611e_cli/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=[("src/sp611e_cli/web", "sp611e_cli/web")],
    # bleak picks its backend at runtime; make sure the WinRT backend is bundled.
    # openrgb-python is imported lazily inside the `openrgb` command; include it explicitly.
    hiddenimports=collect_submodules("bleak") + collect_submodules("winrt") + collect_submodules("openrgb"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name="sp611e",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
