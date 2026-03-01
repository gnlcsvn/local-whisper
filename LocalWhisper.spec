# -*- mode: python ; coding: utf-8 -*-
import os
import site

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

site_packages = site.getsitepackages()[0]

# Collect data files for packages that need them
mlx_datas = collect_data_files("mlx")
sounddevice_datas = collect_data_files("_sounddevice_data")
tiktoken_datas = collect_data_files("tiktoken")
mlx_whisper_datas = collect_data_files("mlx_whisper")
certifi_datas = collect_data_files("certifi")

# Status bar icon template images
statusbar_datas = [
    ("statusbar_iconTemplate.png", "."),
    ("statusbar_iconTemplate@2x.png", "."),
]

all_datas = mlx_datas + sounddevice_datas + tiktoken_datas + mlx_whisper_datas + certifi_datas + statusbar_datas

# Collect all submodules for tricky packages
mlx_imports = collect_submodules("mlx")
mlx_whisper_imports = collect_submodules("mlx_whisper")
pynput_imports = collect_submodules("pynput")
numba_imports = collect_submodules("numba")
scipy_imports = collect_submodules("scipy")

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=all_datas,
    hiddenimports=[
        "config",
        "recorder",
        "transcriber",
        "inserter",
        "hotkey",
        "rumps",
        "sounddevice",
        "numpy",
        "torch",
        "scipy",
        "scipy.signal",
        "tiktoken",
        "tiktoken_ext",
        "tiktoken_ext.openai_public",
        "huggingface_hub",
        "tqdm",
        "certifi",
        "cffi",
        "AVFoundation",
        "ApplicationServices",
        "AppKit",
        "Quartz",
        "objc",
        "_sounddevice_data",
    ] + mlx_imports + mlx_whisper_imports + pynput_imports + numba_imports + scipy_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "PIL",
        "tkinter",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LocalWhisper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    target_arch="arm64",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="LocalWhisper",
)

app = BUNDLE(
    coll,
    name="LocalWhisper.app",
    icon="LocalWhisper.icns",
    bundle_identifier="com.localwhisper.app",
    info_plist={
        "LSUIElement": True,
        "CFBundleName": "LocalWhisper",
        "CFBundleDisplayName": "LocalWhisper",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "NSMicrophoneUsageDescription": "LocalWhisper needs microphone access to record audio for transcription.",
    },
)
