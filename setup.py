from setuptools import setup

APP = ["main.py"]
DATA_FILES = []
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "LSUIElement": True,  # Hide from Dock (menubar-only app)
        "CFBundleName": "WhisperType",
        "CFBundleDisplayName": "WhisperType",
        "CFBundleIdentifier": "com.whispertype.app",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "NSMicrophoneUsageDescription": "WhisperType needs microphone access to record audio for transcription.",
    },
    "packages": [
        "rumps",
        "pynput",
        "sounddevice",
        "numpy",
        "mlx",
        "mlx_whisper",
        "mlx_metal",
        "torch",
        "scipy",
        "numba",
        "tiktoken",
        "huggingface_hub",
        "tqdm",
        "certifi",
        "cffi",
        "AVFoundation",
        "ApplicationServices",
        "objc",
    ],
    "includes": [
        "config",
        "recorder",
        "transcriber",
        "inserter",
        "hotkey",
    ],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
