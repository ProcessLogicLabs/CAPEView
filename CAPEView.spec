# -*- mode: python ; coding: utf-8 -*-
"""CAPEView PyInstaller Spec File.

Build:
    pyinstaller CAPEView.spec
"""

import os
import sys

block_cipher = None

capeview_dir = os.path.join(os.path.dirname(os.path.abspath(SPEC)), "CAPEView")

python_dir = os.path.dirname(sys.executable)
python_dlls = []
for dll_name in ("python3.dll", "python312.dll", "python311.dll",
                 "python310.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
    dll_path = os.path.join(python_dir, dll_name)
    if os.path.exists(dll_path):
        python_dlls.append((dll_path, "."))

datas = []
resources_dir = os.path.join(capeview_dir, "Resources")
if os.path.isdir(resources_dir):
    datas.append((resources_dir, "Resources"))


a = Analysis(
    [os.path.join(capeview_dir, "cape_view.py")],
    pathex=[os.path.dirname(os.path.abspath(SPEC))],
    binaries=python_dlls,
    datas=datas,
    hiddenimports=[
        "PyQt5",
        "PyQt5.QtCore",
        "PyQt5.QtGui",
        "PyQt5.QtWidgets",
        "openpyxl",
        "openpyxl.styles",
        "pandas",
        "requests",
        "sqlite3",
        # CAPEView modules
        "CAPEView",
        "CAPEView.cape_view",
        "CAPEView.cape_database",
        "CAPEView.theme",
        "CAPEView.animated_splash",
        "CAPEView.auto_update",
        "CAPEView.workbook_export",
        "CAPEView.claims_csv_ingest",
        "CAPEView.version",
        "CAPEView.views",
        "CAPEView.views.dashboard",
        "CAPEView.views.table_view",
        "CAPEView.views.reports",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "IPython", "jupyter", "notebook"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CAPEView",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(resources_dir, "icon.ico") if os.path.exists(
        os.path.join(resources_dir, "icon.ico")) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CAPEView",
)
