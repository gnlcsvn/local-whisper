# LocalWhisper

Offline macOS menubar dictation app powered by mlx-whisper on Apple Silicon. Press a hotkey, speak, and text appears at your cursor. 100% private — audio never leaves your Mac.

## Install

Download the latest `.dmg` from [Releases](../../releases), open it, and drag **LocalWhisper** to your Applications folder.

> **Note:** The app is not signed with an Apple Developer certificate. On first launch macOS will block it — go to **System Settings → Privacy & Security**, scroll down, and click **Open Anyway**.

On first launch, grant **Microphone**, **Accessibility**, and **Input Monitoring** permissions when prompted.

## Usage

1. Double-tap your shortcut key (default: **Left Ctrl**) — recording starts, a floating overlay appears
2. Keep working normally — switch apps, browse, type. Recording runs in the background
3. Double-tap again — your speech is transcribed and pasted at your cursor

Or use **Hold mode** (Right ⌘ or Right ⌥) — hold the key while speaking, release to transcribe.

Not in a text field? No problem — the transcription is saved in the menubar menu so you can copy it later. Press **Escape** while recording to cancel.

## Settings

Open **Settings…** (⌘,) from the menubar menu. Everything persists in `~/.localwhisper.json`.

- **Model** — choose from 5 Whisper models (Tiny to Large), downloaded on demand
- **Language** — pick your input language or use auto-detect
- **Translate to English** — uses Whisper's built-in translation (no extra model needed)
- **Clean up text** — removes filler words ("um", "uh"), false starts, and fixes punctuation using a local LLM, without rephrasing your words
- **Audio** — microphone selection, max recording duration (30s – 10min)
- **Shortcut** — double-tap (Ctrl, Cmd, Shift) or hold (Right ⌘, Right ⌥)

## Build from Source

Requires macOS 13+, Apple Silicon, Python 3.10+, and ffmpeg.

```bash
brew install ffmpeg
git clone https://github.com/gnlcsvn/local-whisper.git
cd local-whisper
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run directly
python main.py

# Or build a .app bundle
pip install pyinstaller
pyinstaller LocalWhisper.spec --noconfirm
# Output at dist/LocalWhisper.app
```

### Let your coding agent build it

If you use a coding agent (Claude Code, Cursor, Copilot, etc.), you can paste this prompt and let it handle the rest:

> Clone https://github.com/gnlcsvn/local-whisper.git, create a Python 3.10+ venv, install requirements.txt, then run `python main.py` to verify it starts. If I want a .app bundle, also install pyinstaller and run `pyinstaller LocalWhisper.spec --noconfirm`.

## How It Works

- **Recording** — `sounddevice` captures 16kHz mono audio in memory (never written to disk)
- **Transcription** — `mlx-whisper` runs Whisper natively on Apple Silicon GPU
- **Cleanup** — optional local LLM (Llama 3.2 3B, 4-bit via `mlx-lm`) cleans up grammar and removes filler words
- **Insertion** — clipboard save → paste via Quartz CGEvent Cmd+V → clipboard restore
- **UI** — `rumps` menubar app + floating WKWebView overlay with animated SVG states

## Privacy

- No network requests after initial model downloads
- Audio is captured in RAM and immediately discarded after transcription
- No analytics, no telemetry, no accounts
- Fully open source — audit every line
