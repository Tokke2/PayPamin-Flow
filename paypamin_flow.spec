# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build for PayPamin Flow on Windows, macOS and Linux."""
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve()
sys.path.insert(0, str(ROOT))
from app_info import APP_AUTHOR, APP_COPYRIGHT, APP_ID, APP_NAME, APP_VERSION

is_windows = sys.platform.startswith("win")
is_macos = sys.platform == "darwin"
binary_name = APP_NAME if is_windows else "paypamin-flow"

analysis = Analysis(
    [str(ROOT / "paypamin_flow.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ROOT / "assets"), "assets"), (str(ROOT / "NOTICE"), ".")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)

exe_kwargs = {}
if is_windows:
    exe_kwargs.update(
        icon=str(ROOT / "assets" / "paypamin_flow.ico"),
        version=str(ROOT / "packaging" / "windows_version_info.txt"),
    )

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name=binary_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    **exe_kwargs,
)

if is_macos:
    app = BUNDLE(
        exe,
        name=f"{APP_NAME}.app",
        icon=str(ROOT / "assets" / "paypamin_flow.icns"),
        bundle_identifier=APP_ID,
        info_plist={
            "CFBundleDisplayName": APP_NAME,
            "CFBundleName": APP_NAME,
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": APP_VERSION,
            "NSHumanReadableCopyright": APP_COPYRIGHT,
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.finance",
        },
    )
