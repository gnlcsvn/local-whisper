# LocalWhisper

Offline macOS menubar dictation app powered by mlx-whisper. Records audio via a global hotkey, transcribes locally on Apple Silicon, and pastes the result at the cursor position. 100% private — audio never leaves your Mac.

## Install

Download the latest `.dmg` from [Releases](../../releases), open it, and drag **LocalWhisper** to your Applications folder.

On first launch, grant **Microphone** and **Accessibility** permissions when prompted.

## Usage

Press **Ctrl+Shift+D** to start recording. Speak, then press **Ctrl+Shift+D** again. The transcribed text is pasted at your cursor.

| Menubar Icon | State |
|--------------|-------|
| Lock + waveform (static) | Ready |
| Spinning arc | Downloading model |
| Pulsing bars + red dot | Recording (with timer) |
| Spinning arc | Transcribing / pasting |

Recording auto-stops after 2 minutes.

## Menu Options

- **Model** — shows download size and cache status per model
  - `Turbo – balanced (recommended) [1.5 GB, downloaded]`
  - `Small – fast, good accuracy [460 MB]`
  - Selecting an uncached model downloads it automatically with status feedback
- **Input Language** — Deutsch / English / Français / Español / Italiano / Auto-detect
- **Translate** — toggle translation on/off (menu stays open, macOS-native toggle)
- **Output Language** — target language for translation
- **Shortcut** — Ctrl+Shift+D, Ctrl+Shift+Space, double-tap Ctrl/Cmd/Shift
- **Last transcription** — click to copy to clipboard
- Settings persist across restarts (`~/.localwhisper.json`)

## Translation

LocalWhisper supports any-to-any translation using a local LLM (Llama 3.2 3B, ~1.8 GB). Enable **Translate**, pick input and output languages, and dictate. The LLM downloads automatically on first use with status feedback. For input-to-English, Whisper's built-in translation is used instead (no LLM needed).

## Model Downloads

Models download from HuggingFace Hub on first use. The app shows download status in the menu bar and blocks recording with a notification until the model is ready.

| Model | Size | Notes |
|-------|------|-------|
| Tiny | 75 MB | Fastest, least accurate |
| Small | 460 MB | Fast, good accuracy |
| Turbo | 1.5 GB | Balanced (default) |
| Medium | 1.5 GB | Slower, better accuracy |
| Large | 3.0 GB | Slowest, best accuracy |
| Translation LLM | 1.8 GB | Downloaded on first translation |

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
- **Translation**: `mlx-lm` runs a 4-bit quantized LLM locally for any-to-any translation
- **Insertion**: Clipboard save → pbcopy → osascript Cmd+V → clipboard restore
- **Model management**: Cache checks via `huggingface_hub`, background downloads with UI feedback
- **Animated status bar**: Frame-by-frame PNG animation — lock+waveform idle icon, pulsing bars for recording, spinning arc for processing
- **State machine**: `IDLE → DOWNLOADING → RECORDING → PROCESSING → INSERTING → IDLE`, thread-safe with locks

## Notes

- First launch downloads the default model (Turbo, 1.5 GB) with progress in the status bar
- No network requests after initial model downloads
- Audio is never saved to disk
- Not signed with Apple Developer certificate — on first launch, macOS will block it. Go to **System Settings → Privacy & Security**, scroll down, and click **Open Anyway**
