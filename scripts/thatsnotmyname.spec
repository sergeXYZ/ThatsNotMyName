# -*- mode: python ; coding: utf-8 -*-
"""Windows bundle. Run from the repo root: pyinstaller scripts/thatsnotmyname.spec"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hidden = ["web_ui", "mtx_job", "set_mtx_input_names", "tkinter", "tkinter.filedialog"]
for package in ("webview", "openpyxl", "numbers_parser", "flask", "jinja2", "werkzeug", "clr"):
    try:
        hidden.extend(collect_submodules(package))
    except Exception:
        hidden.append(package)

datas = [
    ("assets/logo-header.png", "assets"),
    ("assets/bg-rays.png", "assets"),
    ("assets/warning-dd.png", "assets"),
    ("assets/thats-not-my-name-bg.png", "assets"),
]
datas += collect_data_files("numbers_parser")
datas += collect_data_files("openpyxl")

a = Analysis(
    ["macos/desktop.py"],
    pathex=["."],
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
    icon="build/app-icon.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ThatsNotMyName",
)
