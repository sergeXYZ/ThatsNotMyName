# -*- mode: python ; coding: utf-8 -*-
"""Windows bundle. Run from the repo root: pyinstaller scripts/thatsnotmyname.spec"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent

hidden = ["web_ui", "mtx_job", "set_mtx_input_names", "tkinter", "tkinter.filedialog"]
for package in ("webview", "openpyxl", "numbers_parser", "flask", "jinja2", "werkzeug", "clr"):
    try:
        hidden.extend(collect_submodules(package))
    except Exception:
        hidden.append(package)

datas = [
    (str(ROOT / "assets" / name), "assets")
    for name in (
        "logo-header.png",
        "bg-rays.png",
        "warning-dd.png",
        "thats-not-my-name-bg.png",
    )
]
datas += collect_data_files("numbers_parser")
datas += collect_data_files("openpyxl")

a = Analysis(
    [str(ROOT / "macos" / "desktop.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ThatsNotMyName",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "build" / "app-icon.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ThatsNotMyName",
)
