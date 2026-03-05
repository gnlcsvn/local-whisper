# LocalWhisper

Offline macOS menubar dictation app powered by mlx-whisper. Records audio via a global hotkey, transcribes locally on Apple Silicon, and pastes the result at the cursor position. 100% private — audio never leaves your Mac.

## Install

Download the latest `.dmg` from [Releases](../../releases), open it, and drag **LocalWhisper** to your Applications folder.

On first launch, grant **Microphone** and **Accessibility** permissions when prompted.

## Usage

Press **Ctrl+Shift+D** (default) to start recording. Speak, then press the shortcut again. The transcribed text is pasted at your cursor.

A floating lock overlay shows the current state:

| Overlay | State |
|---------|-------|
| Red pulsing bars | Recording |
| Purple spinner | Processing / transcribing |
| Teal dual arcs | Translating |
| Hidden | Idle |

Recording auto-stops after the configured max duration (default: 2 minutes).

## Settings

Open **Settings...** (⌘,) from the menubar menu. All settings persist across restarts (`~/.localwhisper.json`).

- **Model** — select and download Whisper models (see table below)
- **Language** — input language, translate toggle, output language
- **Text Processing** — Off / Clean up / Formal / Casual (uses local LLM)
- **Audio** — microphone selection, max recording duration
- **Shortcut** — Ctrl+Shift+D, Ctrl+Shift+Space, double-tap Ctrl/Cmd/Shift

## Translation

LocalWhisper supports any-to-any translation using a local LLM (Llama 3.2 3B, ~1.8 GB). Enable **Translate**, pick input and output languages, and dictate. The LLM downloads automatically on first use. For input-to-English, Whisper's built-in translation is used instead (no LLM needed) — this works with Tiny, Small, and Medium models.

## Text Processing

When a text style is enabled (Clean up, Formal, or Casual), a local LLM post-processes the transcription to fix grammar, punctuation, and tone — while preserving the original meaning and language. The LLM (~1.8 GB) downloads automatically on first use.

## Model Downloads

Models download from HuggingFace Hub on first use. The app shows download status in the menu bar and blocks recording with a notification until the model is ready.

| Model | Size | Notes |
|-------|------|-------|
| Tiny | 75 MB | Fastest, least accurate |
| Small | 460 MB | Fast, good accuracy |
| Turbo | 1.5 GB | Balanced (default) |
| Medium | 1.5 GB | Slower, better accuracy |
| Large | 3.0 GB | Slowest, best accuracy |
| Translation LLM | 1.8 GB | Downloaded on first translation or text processing |

## Build from Source

Requires macOS 13+, Apple Silicon, Python 3.10+, ffmpeg.

```bash
brew install ffmpeg
git clone https://github.com/gnlcsvn/local-whisper.git
cd local-whisper
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
- **Translation**: `mlx-lm` runs a 4-bit quantized LLM locally for any-to-any translation
- **Text processing**: Same LLM cleans up, formalizes, or casualizes transcriptions
- **Insertion**: Clipboard save → pbcopy → Quartz CGEvent Cmd+V → clipboard restore
- **Settings**: WKWebView + HTML/CSS branded dark UI (same approach as overlay)
- **Overlay**: Floating WKWebView with animated SVG lock — no background, just the lock icon
- **State machine**: `IDLE → DOWNLOADING → RECORDING → PROCESSING → TRANSLATING → INSERTING → IDLE`, thread-safe with locks

## Notes

- First launch downloads the default model (Turbo, 1.5 GB) with progress in the status bar
- No network requests after initial model downloads
- Audio is never saved to disk
- Not signed with Apple Developer certificate — on first launch, macOS will block it. Go to **System Settings → Privacy & Security**, scroll down, and click **Open Anyway**
