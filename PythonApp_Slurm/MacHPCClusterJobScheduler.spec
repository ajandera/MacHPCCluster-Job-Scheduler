# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
import os

# --- 1. COLLECT DEPENDENCIES ---
datas = []
binaries = []
hiddenimports = ['matplotlib.backends.backend_qt5agg']

# Collect all files for core dependencies
# PyInstaller hooks handle the complex dependencies for these modules
tmp_ret = collect_all('pyqt5')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

tmp_ret = collect_all('matplotlib')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

tmp_ret = collect_all('paramiko')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


# --- 2. MANUALLY ADD QT PLATFORM PLUGINS ---
# FIX 1: Ensure you are correctly appending the mandatory PyQt5 platform plugins
# NOTE: You MUST verify that this path (the source) is correct for your virtual environment!
# The destination path ('PyQt5/Qt5/plugins/platforms') tells the app where to find the plugins inside the bundle.
# Assuming the current working directory for PyInstaller is where the venv is located:
qt_plugins_path = os.path.join(os.getcwd(), 'venv/lib/python3.14/site-packages/PyQt5/Qt5/plugins/platforms')
datas.append((qt_plugins_path, 'PyQt5/Qt5/plugins/platforms'))


# --- 3. ANALYSIS ---
a = Analysis(
    ['MacHPCClusterJobScheduler.py'], # Use the actual script name from your logs
    pathex=[],
    binaries=binaries,
    datas=datas, # This now contains all collected and manually added datas
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)


# --- 4. EXECUTABLE ---
exe = EXE(
    pyz,
    a.scripts,
    a.binaries, # FIX 2: Include a.binaries here to link dynamic libs
    a.zipfiles,
    a.datas, # FIX 3: Include a.datas here
    name='MacHPCClusterJobScheduler',
    exclude_binaries=True,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False, # CRITICAL: Must be False for GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)


# --- 5. BUNDLE (APP Creation) ---
# FIX 4: Remove the redundant COLLECT step (coll) and use EXE directly.
app = BUNDLE(
    exe, # CRITICAL: Passes the executable and its dependencies to the bundle structure
    name='MacHPCClusterJobScheduler.app', # Final application name
    icon='HPCDashboard.icns', # The icon file must be in the PyInstaller execution directory
    bundle_identifier=None,
)