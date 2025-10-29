# AGI_Assistant.spec (Paths Corrected)

# -*- mode: python ; coding: utf-8 -*-

import sys
import os
import site

# --- Helper to find site-packages in venv ---
# (Keep this section as corrected before)
try:
    venv_path = sys.prefix
    site_packages_paths = site.getsitepackages()
    site_packages_path = next((p for p in site_packages_paths if 'site-packages' in p and venv_path in p), None)
    if not site_packages_path:
        site_packages_path = os.path.join(venv_path, 'Lib', 'site-packages')
        if not os.path.exists(site_packages_path):
            raise Exception("Could not automatically determine site-packages path in .venv.")
    print(f"Detected site-packages path: {site_packages_path}")
except Exception as e:
    print(f"Error detecting site-packages path: {e}")
    site_packages_path = os.path.abspath(os.path.join('.venv', 'Lib', 'site-packages'))
    print(f"Using fallback site-packages path: {site_packages_path}")
    if not os.path.exists(site_packages_path):
        raise FileNotFoundError("Fallback site-packages path not found.")
# --- ---


block_cipher = None

a = Analysis(
    ['gui_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        # --- Add ALL necessary data files ---
        # Format: ('FULL/SOURCE/path/on/disk', 'destination/folder/in/bundle')

        # 1. LLM Model File (Using relative path assuming run from project root)
        ('models/Phi-3-mini-4k-instruct-q4.gguf', 'models'),

        # 2. Whisper Model File (Using relative path assuming run from project root)
        ('models/ggml-base.en.bin', 'models'), # <<< ADDED Whisper model

        # 3. Whisper-CLI Executable and required DLLs (Relative paths, assuming in project root)
        ('whisper-cli.exe', '.'),
        ('whisper.dll', '.'),
        ('ggml.dll', '.'),
        ('ggml-base.dll', '.'),
        ('ggml-cpu.dll', '.'),
        ('SDL2.dll', '.'),
        # !! VERIFY these files EXIST in C:\projects\agi-assistant !!

        # 4. Tesseract OCR Data (TESSDATA) - Using EXACT path provided
        ('C:/Program Files/Tesseract-OCR/tessdata', 'tessdata'), # <<< Using your path

        # 5. llama.dll from llama-cpp-python - Using EXACT path provided
        #    Note: Adjusted destination to match potential library expectations
        (os.path.join(site_packages_path, 'llama_cpp/llama.dll'), 'llama_cpp'), # <<< Using your path, adjusted destination slightly

        # 6. Add template images folder if using OpenCV fallback
        # ('templates', 'templates'),

    ],
    hiddenimports=[
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        'sounddevice',
        '_sounddevice_data',
        'tkinter',
        'PIL._tkinter_finder',
        'scipy',
        'scipy.io.wavfile',
        'scipy.signal',
        'numpy',
        'mss',
        'mss.windows',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    [],
    exclude_binaries=True,
    name='AGI_Assistant',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False, # GUI App
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='path/to/icon.ico'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas, # Include datas
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AGI_Assistant_App' # Output folder name
)