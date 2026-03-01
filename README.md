# LocalWhisper

Offline macOS menubar dictation app powered by mlx-whisper. Records audio via a global hotkey, transcribes locally on Apple Silicon, and pastes the result at the cursor position. 100% private — audio never leaves your Mac.

## Install

Download the latest `.dmg` from [Releases](../../releases), open it, and drag **LocalWhisper** to your Applications folder.

On first launch, grant **Microphone** and **Accessibility** permissions when prompted.

## Usage

Press **Ctrl+Shift+D** to start recording. Speak, then press **Ctrl+Shift+D** again. The transcribed text is pasted at your cursor.

| Menubar | State |
|---------|-------|
| 🎤 | Ready |
| 🔴 Rec | Recording (with timer) |
| ⏳ | Transcribing / pasting |

Recording auto-stops after 2 minutes.

## Menu Options

- **Model** — Tiny / Small / Turbo (default) / Medium / Large
- **Language** — Deutsch / English / Français / Español / Italiano / Auto-detect
- **Last transcription** — click to copy to clipboard
- Settings persist across restarts (`~/.localwhisper.json`)

## Build from Source

Requires macOS 13+, Apple Silicon, Python 3.10+, ffmpeg.

```bash
brew install ffmpeg
cd whispertype
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install pyinstaller

# Build .app
pyinstaller LocalWhisper.spec --noconfirm

# Output at dist/LocalWhisper.app
```

## How It Works

- **Recording**: `sounddevice` captures 16kHz float32 mono audio in memory — no disk I/O
- **Transcription**: `mlx-whisper` runs Whisper models natively on Apple Silicon GPU
- **Insertion**: Clipboard save → pbcopy → osascript Cmd+V → clipboard restore
- **State machine**: `IDLE → RECORDING → PROCESSING → INSERTING → IDLE`, thread-safe with locks

## Notes

- First transcription downloads the model from HuggingFace (~80MB for tiny, ~3GB for large)
- No network requests after initial model download
- Audio is never saved to disk
- Not signed with Apple Developer certificate — right-click → Open on first launch
