# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# ✅ Корень проекта (рядом со spec)
PROJECT_DIR = Path.cwd()

# ---------------------------
# 1) Project resources (datas)
# ---------------------------
datas = []
binaries = []
hiddenimports = []

# ✅ templates (иконки лежат внутри templates/icons)
templates_dir = PROJECT_DIR / "templates"
if templates_dir.exists():
    datas.append((str(templates_dir), "templates"))
# ---------------------------
# 2) Collect packages (Qt, etc)
# ---------------------------
for pkg in ("PySide6", "qasync", "sqlalchemy", "playwright"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# ---------------------------
# 3) Analysis
# ---------------------------
a = Analysis(
    ["main.py"],
    pathex=[str(PROJECT_DIR)],   # ✅ ВАЖНО: чтобы всегда видел твой проект
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# ---------------------------
# 4) PYZ
# ---------------------------
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ---------------------------
# 5) EXE (without binaries -> COLLECT will place them)
# ---------------------------
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MarketBuyer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

# ---------------------------
# 6) COLLECT (onedir)
# ---------------------------
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="MarketBuyer",
)
