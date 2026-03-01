import enum
import json
import os
import time
import threading

import rumps

from config import Config, MODEL_MAP
from recorder import AudioRecorder
from transcriber import WhisperTranscriber
from inserter import TextInserter, InsertionError
from hotkey import HotkeyListener


class State(enum.Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    INSERTING = "inserting"


MENUBAR_TITLES = {
    State.IDLE: "\U0001f3a4",           # 🎤
    State.RECORDING: "\U0001f534 Rec",   # 🔴 Rec
    State.PROCESSING: "\u23f3",          # ⏳
    State.INSERTING: "\u23f3",           # ⏳
}

STATUS_LABELS = {
    State.IDLE: "Ready",
    State.RECORDING: "Recording\u2026",
    State.PROCESSING: "Transcribing\u2026",
    State.INSERTING: "Pasting\u2026",
}

LANGUAGES = {
    "Deutsch": "de",
    "English": "en",
    "Fran\u00e7ais": "fr",
    "Espa\u00f1ol": "es",
    "Italiano": "it",
    "Auto-detect": "auto",
}

MODEL_LABELS = {
    "tiny": "Tiny  \u2013  fastest, least accurate",
    "small": "Small  \u2013  fast, good accuracy",
    "turbo": "Turbo  \u2013  balanced (recommended)",
    "medium": "Medium  \u2013  slower, better accuracy",
    "large": "Large  \u2013  slowest, best accuracy",
}

SETTINGS_PATH = os.path.expanduser("~/.localwhisper.json")


def _load_settings(config: Config) -> None:
    """Load persisted settings into config, if available."""
    try:
        with open(SETTINGS_PATH) as f:
            data = json.load(f)
        if data.get("model_name") in MODEL_MAP:
            config.model_name = data["model_name"]
        lang = data.get("language", "")
        if lang in LANGUAGES.values():
            config.language = lang
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass


def _save_settings(config: Config) -> None:
    """Persist current model and language choice."""
    try:
        with open(SETTINGS_PATH, "w") as f:
            json.dump(
                {"model_name": config.model_name, "language": config.language},
                f,
            )
    except OSError:
        pass


def _check_microphone_permission() -> bool:
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeAudio

        status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio)
        if status == 0:  # AVAuthorizationStatusNotDetermined
            granted = [None]
            event = threading.Event()

            def handler(g):
                granted[0] = g
                event.set()

            AVCaptureDevice.requestAccessForMediaType_completionHandler_(
                AVMediaTypeAudio, handler
            )
            event.wait(timeout=10)
            return bool(granted[0])
        return status == 3  # AVAuthorizationStatusAuthorized
    except Exception:
        return True


def _check_accessibility_permission() -> bool:
    try:
        from ApplicationServices import AXIsProcessTrusted

        return AXIsProcessTrusted()
    except Exception:
        return True


class LocalWhisperApp(rumps.App):
    def __init__(self):
        super().__init__(
            "LocalWhisper",
            title=MENUBAR_TITLES[State.IDLE],
            quit_button=None,
        )

        self._config = Config()
        _load_settings(self._config)

        self._state = State.IDLE
        self._state_lock = threading.Lock()
        self._pending_ui: dict | None = None
        self._pending_lock = threading.Lock()
        self._pending_notification: tuple[str, str] | None = None
        self._max_timer: threading.Timer | None = None
        self._recording_start: float = 0
        self._last_transcription: str = ""

        self._recorder = AudioRecorder(sample_rate=self._config.sample_rate)
        self._transcriber = WhisperTranscriber(
            model_name=self._config.model_name,
            language=self._config.language,
        )
        self._inserter = TextInserter()

        self._build_menu()
        self._check_permissions()
        self._start_hotkey()

    # ── Menu ──────────────────────────────────────────────

    def _build_menu(self):
        self._status_item = rumps.MenuItem("Ready", callback=None)
        self._status_item.set_callback(None)

        self._shortcut_item = rumps.MenuItem(
            "Shortcut: \u2303\u21e7D  (Ctrl+Shift+D)", callback=None
        )
        self._shortcut_item.set_callback(None)

        self._last_text_header = rumps.MenuItem("Last transcription:", callback=None)
        self._last_text_header.set_callback(None)
        self._last_text_item = rumps.MenuItem("\u2014", callback=None)
        self._last_text_item.set_callback(None)

        self._model_menu = rumps.MenuItem("Model")
        for name in MODEL_MAP:
            label = MODEL_LABELS.get(name, name)
            item = rumps.MenuItem(label, callback=self._on_model_select)
            item._model_key = name
            item.state = name == self._config.model_name
            self._model_menu.add(item)

        self._lang_menu = rumps.MenuItem("Language")
        for display, code in LANGUAGES.items():
            item = rumps.MenuItem(display, callback=self._on_language_select)
            item._lang_code = code
            item.state = code == self._config.language
            self._lang_menu.add(item)

        about = rumps.MenuItem("About LocalWhisper", callback=self._on_about)
        quit_item = rumps.MenuItem("Quit LocalWhisper", callback=self._on_quit)

        self.menu = [
            self._status_item,
            self._shortcut_item,
            None,
            self._last_text_header,
            self._last_text_item,
            None,
            self._model_menu,
            self._lang_menu,
            None,
            about,
            quit_item,
        ]

    def _on_model_select(self, sender):
        key = sender._model_key
        self._config.model_name = key
        self._transcriber.change_model(key)
        for item in self._model_menu.values():
            item.state = getattr(item, "_model_key", None) == key
        _save_settings(self._config)

    def _on_language_select(self, sender):
        code = sender._lang_code
        self._config.language = code
        self._transcriber.change_language(code)
        for item in self._lang_menu.values():
            item.state = getattr(item, "_lang_code", None) == code
        _save_settings(self._config)

    def _on_copy_last(self, _):
        if self._last_transcription:
            import subprocess

            subprocess.run(
                ["pbcopy"], input=self._last_transcription, text=True, timeout=2
            )
            rumps.notification(
                title="LocalWhisper",
                subtitle="",
                message="Copied to clipboard!",
            )

    def _on_about(self, _):
        rumps.alert(
            title="LocalWhisper",
            message=(
                "Offline voice-to-text for macOS.\n"
                "Powered by mlx-whisper on Apple Silicon.\n\n"
                "100% private \u2013 audio never leaves your Mac.\n\n"
                "Press Ctrl+Shift+D to start/stop dictation.\n"
                "Text is automatically pasted at your cursor."
            ),
        )

    def _on_quit(self, _):
        # Cancel max-duration timer if recording
        with self._state_lock:
            if self._max_timer is not None:
                self._max_timer.cancel()
                self._max_timer = None
            # Stop recorder if active
            if self._state == State.RECORDING:
                try:
                    self._recorder.stop()
                except Exception:
                    pass
        self._hotkey_listener.stop()
        rumps.quit_application()

    # ── Permissions ───────────────────────────────────────

    def _check_permissions(self):
        if not _check_microphone_permission():
            rumps.alert(
                title="Microphone Access Required",
                message=(
                    "LocalWhisper needs microphone access to record audio.\n\n"
                    "Open System Settings \u2192 Privacy & Security \u2192 Microphone "
                    "and grant access to LocalWhisper."
                ),
            )

        if not _check_accessibility_permission():
            rumps.alert(
                title="Accessibility Access Required",
                message=(
                    "LocalWhisper needs Accessibility access to paste text "
                    "at your cursor position.\n\n"
                    "Open System Settings \u2192 Privacy & Security \u2192 Accessibility "
                    "and grant access to LocalWhisper."
                ),
            )

    # ── Hotkey ────────────────────────────────────────────

    def _start_hotkey(self):
        self._hotkey_listener = HotkeyListener(
            self._config.hotkey, self._on_hotkey
        )
        t = threading.Thread(target=self._hotkey_listener.start, daemon=True)
        t.start()

    # ── UI timer (main thread) ────────────────────────────

    @rumps.timer(0.1)
    def _poll_ui(self, _):
        # Send pending notification (must happen on main thread)
        with self._pending_lock:
            notif = self._pending_notification
            self._pending_notification = None
        if notif is not None:
            rumps.notification(
                title="LocalWhisper", subtitle="", message=notif[1]
            )

        # Apply pending UI update
        with self._pending_lock:
            update = self._pending_ui
            self._pending_ui = None

        if update is None:
            # Update recording duration while recording
            with self._state_lock:
                is_recording = self._state == State.RECORDING
            if is_recording:
                elapsed = int(time.time() - self._recording_start)
                mins, secs = divmod(elapsed, 60)
                self._status_item.title = f"Recording\u2026  {mins}:{secs:02d}"
            return

        if "title" in update:
            self.title = update["title"]
        if "status" in update:
            self._status_item.title = update["status"]
        if "last_text" in update:
            text = update["last_text"]
            self._last_transcription = text
            truncated = (text[:60] + "\u2026") if len(text) > 60 else text
            self._last_text_item.title = f"\u201c{truncated}\u201d"
            self._last_text_item.set_callback(self._on_copy_last)

    # ── State machine ─────────────────────────────────────

    def _set_state(self, state: State, **extra):
        """Set state and queue a UI update. Caller MUST hold _state_lock."""
        self._state = state
        update = {
            "title": MENUBAR_TITLES[state],
            "status": STATUS_LABELS[state],
        }
        update.update(extra)
        with self._pending_lock:
            self._pending_ui = update

    def _notify(self, message: str) -> None:
        """Queue a notification to be shown on the main thread."""
        with self._pending_lock:
            self._pending_notification = ("LocalWhisper", message)

    def _on_hotkey(self):
        with self._state_lock:
            if self._state == State.IDLE:
                self._set_state(State.RECORDING)
                self._start_recording()
            elif self._state == State.RECORDING:
                self._stop_and_transcribe()
            # Ignore during PROCESSING / INSERTING

    def _start_recording(self):
        """Start recording. Caller MUST hold _state_lock."""
        self._recording_start = time.time()
        self._recorder.start()
        self._max_timer = threading.Timer(
            self._config.max_recording_seconds, self._on_max_duration
        )
        self._max_timer.daemon = True
        self._max_timer.start()

    def _on_max_duration(self):
        with self._state_lock:
            if self._state == State.RECORDING:
                self._stop_and_transcribe()

    def _stop_and_transcribe(self):
        """Stop recording and start transcription. Caller MUST hold _state_lock."""
        if self._max_timer is not None:
            self._max_timer.cancel()
            self._max_timer = None

        self._set_state(State.PROCESSING)
        audio = self._recorder.stop()

        t = threading.Thread(
            target=self._transcribe_and_insert, args=(audio,), daemon=True
        )
        t.start()

    def _transcribe_and_insert(self, audio):
        try:
            text = self._transcriber.transcribe(audio)
            if not text:
                self._notify("No speech detected.")
                with self._state_lock:
                    self._set_state(State.IDLE)
                return

            with self._state_lock:
                self._set_state(State.INSERTING)

            self._inserter.insert(text)

            with self._state_lock:
                self._set_state(State.IDLE, last_text=text)
            return

        except InsertionError as e:
            self._notify(f"Paste failed: {e}")
        except Exception as e:
            self._notify(f"Transcription failed: {type(e).__name__}")

        with self._state_lock:
            self._set_state(State.IDLE)


if __name__ == "__main__":
    LocalWhisperApp().run()
