import enum
import json
import logging
import os
import sys
import time
import threading
import rumps
import sounddevice as sd

# File logging for crash debugging
_LOG_PATH = os.path.expanduser("~/localwhisper.log")
logging.basicConfig(
    filename=_LOG_PATH,
    level=logging.DEBUG,
    format="%(asctime)s [%(threadName)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("LocalWhisper")

from config import (
    Config, MODEL_MAP, MODEL_SIZES_MB, LLM_MODEL_REPO, LLM_SIZE_MB,
    SHORTCUT_PRESETS, LANGUAGES as LANG_CODES,
    RECORDING_DURATIONS,
)
from model_manager import (
    is_whisper_cached, is_llm_cached,
    download_model, format_size,
    delete_cached_model, get_total_cache_size_str,
)
from recorder import AudioRecorder
from transcriber import WhisperTranscriber
from translator import LLMProcessor
from inserter import TextInserter, InsertionError
from hotkey import HotkeyListener
from overlay import OverlayWindow
from settings_window import SettingsWindow


def _resource_path(relative: str) -> str:
    """Get path to bundled resource (works for dev and PyInstaller)."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative)


class State(enum.Enum):
    IDLE = "idle"
    DOWNLOADING = "downloading"
    RECORDING = "recording"
    PROCESSING = "processing"
    TRANSLATING = "translating"
    INSERTING = "inserting"


# When using an icon, title is text shown *next to* the icon
MENUBAR_TITLES = {
    State.IDLE: "",
    State.DOWNLOADING: "",
    State.RECORDING: "",
    State.PROCESSING: "",
    State.TRANSLATING: "",
    State.INSERTING: "",
}

STATUS_LABELS = {
    State.IDLE: "Ready",
    State.DOWNLOADING: "Downloading\u2026",
    State.RECORDING: "Recording\u2026",
    State.PROCESSING: "Processing\u2026",
    State.TRANSLATING: "Translating\u2026",
    State.INSERTING: "Pasting\u2026",
}

SETTINGS_PATH = os.path.expanduser("~/.localwhisper.json")

# System sounds for recording feedback
_SOUND_START = "/System/Library/Sounds/Tink.aiff"
_SOUND_STOP = "/System/Library/Sounds/Pop.aiff"
_NSSound = None


def _play_sound(path: str) -> None:
    """Play a system sound. Must be called from main thread or via pending_sound."""
    global _NSSound
    try:
        if _NSSound is None:
            from AppKit import NSSound as _NS
            _NSSound = _NS
        sound = _NSSound.alloc().initWithContentsOfFile_byReference_(path, True)
        if sound:
            sound.play()
    except Exception:
        pass


def _get_input_devices() -> list[dict]:
    """Return input-capable audio devices as [{"index": int, "name": str}, ...]."""
    try:
        devices = sd.query_devices()
        return [
            {"index": i, "name": d["name"]}
            for i, d in enumerate(devices)
            if d["max_input_channels"] > 0
        ]
    except Exception:
        log.exception("Failed to query audio devices")
        return []


def _resolve_device_name(name: str | None) -> int | None:
    """Resolve a saved device name to its current index. None if not found."""
    if name is None:
        return None
    try:
        devices = sd.query_devices()
        for i, d in enumerate(devices):
            if d["max_input_channels"] > 0 and d["name"] == name:
                return i
    except Exception:
        log.exception("Failed to resolve device name")
    return None


def _load_settings(config: Config) -> None:
    try:
        with open(SETTINGS_PATH) as f:
            data = json.load(f)
        if data.get("model_name") in MODEL_MAP:
            config.model_name = data["model_name"]
        lang = data.get("language", "")
        if lang in LANG_CODES:
            config.language = lang

        # New fields
        if isinstance(data.get("translate_to_english"), bool):
            config.translate_to_english = data["translate_to_english"]
        if isinstance(data.get("cleanup"), bool):
            config.cleanup = data["cleanup"]

        # Migration from old settings
        if "translate_to_english" not in data:
            if data.get("translate") and data.get("output_language") == "en":
                config.translate_to_english = True
            if data.get("text_style", "off") != "off":
                config.cleanup = True

        shortcut = data.get("shortcut", "")
        if shortcut in SHORTCUT_PRESETS:
            config.shortcut = shortcut
        max_rec = data.get("max_recording_seconds")
        if isinstance(max_rec, int) and max_rec in RECORDING_DURATIONS:
            config.max_recording_seconds = max_rec
        input_dev = data.get("input_device")
        if input_dev is None or isinstance(input_dev, str):
            config.input_device = input_dev
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass


def _save_settings(config: Config) -> None:
    try:
        with open(SETTINGS_PATH, "w") as f:
            json.dump(
                {
                    "model_name": config.model_name,
                    "language": config.language,
                    "translate_to_english": config.translate_to_english,
                    "cleanup": config.cleanup,
                    "max_recording_seconds": config.max_recording_seconds,
                    "shortcut": config.shortcut,
                    "input_device": config.input_device,
                },
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
            icon=None,
            template=True,
            quit_button=None,
        )

        # Custom lock+waveform vector icon (template, auto-tints for light/dark)
        self._set_menubar_icon()

        self._overlay = OverlayWindow(_resource_path)

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
        self._hotkey_listener: HotkeyListener | None = None

        self._recorder = AudioRecorder(sample_rate=self._config.sample_rate)
        # Resolve saved microphone
        device_index = _resolve_device_name(self._config.input_device)
        if device_index is None and self._config.input_device is not None:
            log.warning(f"Saved input device '{self._config.input_device}' not found, using system default")
            self._config.input_device = None
            _save_settings(self._config)
        self._recorder.change_device(device_index)

        self._transcriber = WhisperTranscriber(
            model_name=self._config.model_name,
            language=self._config.language,
        )
        self._llm = LLMProcessor()  # lazy-loaded on first use
        self._inserter = TextInserter()

        self._permissions_checked = False
        self._default_model_ensured = False
        # Cache status per model name: True = cached, False = not, None = unknown
        self._model_cache_status: dict[str, bool | None] = {
            name: None for name in MODEL_MAP
        }
        self._llm_cache_status: bool | None = None
        self._last_input_devices: list[dict] = _get_input_devices()
        self._device_poll_counter: int = 0

        self._build_menu()
        self._settings_window = SettingsWindow(self)
        self._start_hotkey()

    # ── Menubar icon ─────────────────────────────────────

    def _set_menubar_icon(self) -> None:
        """Load the lock+waveform menubar template icon (PNG, auto-tints)."""
        try:
            from AppKit import NSImage

            # Load the @2x template PNG (Retina)
            icon_path = _resource_path("menubarTemplate@2x.png")
            image = NSImage.alloc().initByReferencingFile_(icon_path)
            if image is None or image.isValid() == False:
                log.warning(f"Menubar icon not found at {icon_path}")
                return

            # Set size to 22x22pt (the @2x PNG is 44x44px)
            from Foundation import NSMakeSize
            image.setSize_(NSMakeSize(22, 22))
            image.setTemplate_(True)

            # Bypass rumps file-based icon path — set NSImage directly
            self._icon_nsimage = image
            self._icon = "menubar"  # keep rumps happy
            try:
                self._nsapp.setStatusBarIcon()
            except AttributeError:
                pass  # not yet initialized, will be set in initializeStatusBar
        except Exception:
            log.exception("Failed to load menubar icon")

    # ── Menu ──────────────────────────────────────────────

    def _build_menu(self):
        self._status_item = rumps.MenuItem("Ready", callback=None)
        self._status_item.set_callback(None)

        # Shortcut display (updated dynamically)
        preset = SHORTCUT_PRESETS.get(self._config.shortcut, {})
        self._shortcut_item = rumps.MenuItem(
            f"Shortcut: {preset.get('label', '?')}", callback=None
        )
        self._shortcut_item.set_callback(None)

        # Translation info display
        self._processing_info = rumps.MenuItem(
            self._processing_info_text(), callback=None
        )
        self._processing_info.set_callback(None)

        self._last_text_header = rumps.MenuItem("Last transcription:", callback=None)
        self._last_text_header.set_callback(None)
        self._last_text_item = rumps.MenuItem("\u2014", callback=None)
        self._last_text_item.set_callback(None)

        settings_item = rumps.MenuItem("Settings\u2026", callback=self._on_open_settings)
        # Add Cmd+, shortcut
        settings_item._menuitem.setKeyEquivalent_(",")

        about = rumps.MenuItem("About LocalWhisper", callback=self._on_about)
        quit_item = rumps.MenuItem("Quit LocalWhisper", callback=self._on_quit)

        self.menu = [
            self._status_item,
            self._shortcut_item,
            self._processing_info,
            None,
            self._last_text_header,
            self._last_text_item,
            None,
            settings_item,
            None,
            about,
            quit_item,
        ]

    def _processing_info_text(self) -> str:
        """Build the info string like 'Deutsch → English · Clean up'."""
        in_name = LANG_CODES.get(self._config.language, self._config.language)
        if self._config.use_whisper_translate:
            parts = [f"{in_name} \u2192 English"]
        else:
            parts = [in_name]
        if self._config.cleanup:
            parts.append("Clean up")
        return " \u00b7 ".join(parts)

    def _update_processing_info(self):
        self._processing_info.title = self._processing_info_text()

    def _on_open_settings(self, _):
        log.info("_on_open_settings callback fired")
        self._settings_window.show()

    def _check_model_cache_status(self):
        """Check cache status for all models on a background thread."""
        def _check():
            for name in MODEL_MAP:
                self._model_cache_status[name] = is_whisper_cached(name)
            self._llm_cache_status = is_llm_cached()
            log.info(f"Model cache status: {self._model_cache_status}, LLM: {self._llm_cache_status}")
            with self._pending_lock:
                if self._pending_ui is not None:
                    self._pending_ui["refresh_model_menu"] = True
                else:
                    self._pending_ui = {"refresh_model_menu": True}
        threading.Thread(target=_check, daemon=True, name="cache-check").start()

    # ── Settings window callbacks ────────────────────────────

    def on_settings_model_select(self, model_key):
        if model_key == self._config.model_name:
            return
        self._config.model_name = model_key
        self._transcriber.change_model(model_key)
        _save_settings(self._config)

    def on_settings_download_model(self, model_key):
        with self._state_lock:
            if self._state == State.DOWNLOADING:
                return
        self._download_and_switch_model(model_key)

    def on_settings_delete_model(self, model_key):
        """Delete a cached whisper model (not the active one)."""
        if model_key == self._config.model_name:
            return
        repo_id = MODEL_MAP.get(model_key)
        if not repo_id:
            return

        def _do():
            if delete_cached_model(repo_id):
                self._model_cache_status[model_key] = False
                log.info(f"Deleted model {model_key}")
            else:
                self._notify(f"Failed to delete {model_key}")
            with self._pending_lock:
                if self._pending_ui is not None:
                    self._pending_ui["refresh_model_menu"] = True
                else:
                    self._pending_ui = {"refresh_model_menu": True}

        threading.Thread(target=_do, daemon=True, name="model-del").start()

    def on_settings_download_llm(self):
        with self._state_lock:
            if self._state == State.DOWNLOADING:
                return
        size = format_size(LLM_SIZE_MB)
        with self._state_lock:
            self._set_state(
                State.DOWNLOADING,
                status=f"Downloading cleanup model ({size})\u2026",
            )

        def _do():
            try:
                download_model(LLM_MODEL_REPO)
                self._llm_cache_status = True
                with self._state_lock:
                    self._set_state(State.IDLE)
                self._notify("Cleanup model ready!")
                with self._pending_lock:
                    if self._pending_ui is not None:
                        self._pending_ui["refresh_model_menu"] = True
                    else:
                        self._pending_ui = {"refresh_model_menu": True}
            except Exception:
                log.exception("Failed to download LLM")
                self._notify("Cleanup model download failed")
                with self._state_lock:
                    self._set_state(State.IDLE)
                with self._pending_lock:
                    if self._pending_ui is not None:
                        self._pending_ui["llm_download_error"] = True
                    else:
                        self._pending_ui = {"llm_download_error": True}

        threading.Thread(target=_do, daemon=True, name="llm-dl").start()

    def on_settings_delete_llm(self):
        """Delete the cached cleanup LLM."""
        def _do():
            if delete_cached_model(LLM_MODEL_REPO):
                self._llm_cache_status = False
                log.info("Deleted cleanup LLM")
            else:
                self._notify("Failed to delete cleanup model")
            with self._pending_lock:
                if self._pending_ui is not None:
                    self._pending_ui["refresh_model_menu"] = True
                else:
                    self._pending_ui = {"refresh_model_menu": True}

        threading.Thread(target=_do, daemon=True, name="llm-del").start()

    def _refresh_storage_info(self):
        """Update the storage info in settings on a background thread."""
        def _do():
            text = f"Models stored in ~/.cache/huggingface/hub \u00b7 {get_total_cache_size_str()} total"
            self._settings_window.update_storage_info(text)
        threading.Thread(target=_do, daemon=True, name="storage-info").start()

    def on_settings_input_lang(self, code):
        self._config.language = code
        self._transcriber.change_language(code)
        self._update_processing_info()
        _save_settings(self._config)

    def on_settings_translate_to_english(self, enabled):
        self._config.translate_to_english = enabled
        self._update_processing_info()
        _save_settings(self._config)

    def on_settings_cleanup_toggle(self, enabled):
        self._config.cleanup = enabled
        self._update_processing_info()
        _save_settings(self._config)

    def on_settings_shortcut(self, preset_id):
        try:
            if preset_id == self._config.shortcut:
                return
            self._config.shortcut = preset_id
            preset = SHORTCUT_PRESETS[preset_id]
            self._shortcut_item.title = f"Shortcut: {preset['label']}"
            _save_settings(self._config)
            if self._hotkey_listener is not None:
                self._hotkey_listener.change_shortcut(preset)
            log.info(f"Shortcut changed to {preset_id}")
        except Exception:
            log.exception("Error in on_settings_shortcut")

    def on_settings_max_recording(self, seconds):
        self._config.max_recording_seconds = seconds
        _save_settings(self._config)
        log.info(f"Max recording length changed to {seconds}s")

    def on_settings_mic_select(self, device_name, device_index):
        if device_name == self._config.input_device:
            return
        self._config.input_device = device_name
        self._recorder.change_device(device_index)
        _save_settings(self._config)
        log.info(f"Microphone changed to: {device_name or 'System Default'} (index={device_index})")

    def _check_device_changes(self):
        """Refresh mic list if the available devices changed."""
        current = _get_input_devices()
        if current == self._last_input_devices:
            return

        log.info(f"Audio devices changed: {len(self._last_input_devices or [])} -> {len(current)}")

        if self._config.input_device is not None:
            available_names = {d["name"] for d in current}
            if self._config.input_device not in available_names:
                log.warning(f"Selected device '{self._config.input_device}' disappeared, falling back to system default")
                self._config.input_device = None
                self._recorder.change_device(None)
                _save_settings(self._config)

        self._last_input_devices = current
        self._settings_window.refresh_devices(current)

    def _on_copy_last(self, _):
        if self._last_transcription:
            from inserter import _set_clipboard
            _set_clipboard(self._last_transcription)
            rumps.notification(
                title="LocalWhisper",
                subtitle="",
                message="Copied to clipboard!",
            )

    def _on_about(self, _):
        preset = SHORTCUT_PRESETS.get(self._config.shortcut, {})
        shortcut_label = preset.get("label", "Ctrl+Shift+D")
        rumps.alert(
            title="LocalWhisper",
            message=(
                "Offline voice-to-text for macOS.\n"
                "Powered by mlx-whisper on Apple Silicon.\n\n"
                "100% private \u2013 audio never leaves your Mac.\n\n"
                f"Press {shortcut_label} to start/stop dictation.\n"
                "Text is automatically pasted at your cursor."
            ),
        )

    def _on_quit(self, _):
        with self._state_lock:
            if self._max_timer is not None:
                self._max_timer.cancel()
                self._max_timer = None
            if self._state == State.RECORDING:
                try:
                    self._recorder.stop()
                except Exception:
                    pass
        if self._hotkey_listener is not None:
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
                    "and grant access to LocalWhisper.\n\n"
                    "Then restart the app."
                ),
            )

        if not _check_accessibility_permission():
            rumps.alert(
                title="Permissions Required",
                message=(
                    "LocalWhisper needs two permissions to work:\n\n"
                    "1. Accessibility \u2013 to paste text at your cursor\n"
                    "2. Input Monitoring \u2013 to detect keyboard shortcuts\n\n"
                    "Open System Settings \u2192 Privacy & Security and enable "
                    "LocalWhisper in BOTH:\n"
                    "  \u2022 Accessibility\n"
                    "  \u2022 Input Monitoring\n\n"
                    "If LocalWhisper is already listed but not working, "
                    "remove it and re-add it (the app binary changed).\n\n"
                    "Then restart the app."
                ),
            )

    # ── Hotkey ────────────────────────────────────────────

    def _start_hotkey(self):
        preset = SHORTCUT_PRESETS.get(self._config.shortcut)
        if preset is None:
            preset = SHORTCUT_PRESETS["ctrl_shift_d"]
        log.info(f"Starting hotkey listener: type={preset.get('type')}, preset={self._config.shortcut}")
        self._hotkey_listener = HotkeyListener(preset, self._on_hotkey, cancel_callback=self._on_cancel)
        t = threading.Thread(target=self._hotkey_listener.start, daemon=True, name="hotkey")
        t.start()
        log.info("Hotkey thread started")

    # ── UI timer (main thread) ────────────────────────────

    @rumps.timer(0.1)
    def _poll_ui(self, _):
        # Defer permission checks until the run loop is active
        if not self._permissions_checked:
            self._permissions_checked = True
            self._check_permissions()

        # After permissions, ensure the default model is downloaded
        if not self._default_model_ensured:
            self._default_model_ensured = True
            threading.Thread(
                target=self._ensure_default_model, daemon=True, name="ensure-default"
            ).start()

        # Poll for audio device changes every ~3 seconds
        self._device_poll_counter += 1
        if self._device_poll_counter >= 30:
            self._device_poll_counter = 0
            self._check_device_changes()

        with self._pending_lock:
            notif = self._pending_notification
            self._pending_notification = None
        if notif is not None:
            rumps.notification(
                title="LocalWhisper", subtitle="", message=notif[1]
            )

        with self._pending_lock:
            update = self._pending_ui
            self._pending_ui = None

        if update is None:
            with self._state_lock:
                is_recording = self._state == State.RECORDING
            if is_recording:
                elapsed = time.time() - self._recording_start
                mins, secs = divmod(int(elapsed), 60)
                self._status_item.title = f"Recording\u2026  {mins}:{secs:02d}"
            return

        if "title" in update:
            self.title = update["title"]
        if "status" in update:
            self._status_item.title = update["status"]
        if "sound" in update:
            _play_sound(update["sound"])
        if "last_text" in update:
            text = update["last_text"]
            self._last_transcription = text
            truncated = (text[:60] + "\u2026") if len(text) > 60 else text
            self._last_text_item.title = f"\u201c{truncated}\u201d"
            self._last_text_item.set_callback(self._on_copy_last)
        if update.get("refresh_model_menu"):
            active = self._config.model_name
            for name in MODEL_MAP:
                cached = self._model_cache_status.get(name, False)
                self._settings_window.update_model_status(
                    name, is_cached=bool(cached), is_active=(name == active)
                )
            self._settings_window.update_llm_status(
                is_cached=bool(self._llm_cache_status)
            )
            self._refresh_storage_info()
        if "active_model" in update:
            self._settings_window.update_model_selection(update["active_model"])
        if update.get("settings_download_failed"):
            key = update["settings_download_failed"]
            self._settings_window.update_model_status(
                key, is_cached=False, is_downloading=False,
                error_message="Download failed"
            )
        if update.get("llm_download_error"):
            self._settings_window.update_llm_status(
                is_cached=False, error_message="Download failed"
            )

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

        # Drive the floating overlay animation
        if state == State.IDLE:
            self._overlay.hide()
        elif state == State.DOWNLOADING:
            self._overlay.show_processing()
        elif state == State.RECORDING:
            self._overlay.show_recording()
        elif state == State.TRANSLATING:
            self._overlay.show_translating()
        elif state == State.PROCESSING:
            self._overlay.show_processing()
        # INSERTING: keep current overlay (paste is near-instant)

    def _notify(self, message: str) -> None:
        with self._pending_lock:
            self._pending_notification = ("LocalWhisper", message)

    def _queue_sound(self, path: str) -> None:
        """Queue a sound to be played on the main thread."""
        with self._pending_lock:
            if self._pending_ui is not None:
                self._pending_ui["sound"] = path
            else:
                self._pending_ui = {"sound": path}

    def _download_and_switch_model(self, model_name: str):
        """Download an uncached Whisper model, then switch to it."""
        repo_id = MODEL_MAP[model_name]
        size = format_size(MODEL_SIZES_MB.get(model_name, 0))

        with self._state_lock:
            self._set_state(
                State.DOWNLOADING,
                status=f"Downloading {model_name} ({size})\u2026",
            )

        def _do_download():
            try:
                download_model(repo_id)
                self._model_cache_status[model_name] = True
                self._config.model_name = model_name
                self._transcriber.change_model(model_name)
                _save_settings(self._config)

                with self._state_lock:
                    self._set_state(State.IDLE)
                self._notify(f"{model_name.title()} model ready!")
                with self._pending_lock:
                    if self._pending_ui is not None:
                        self._pending_ui["refresh_model_menu"] = True
                        self._pending_ui["active_model"] = model_name
                    else:
                        self._pending_ui = {
                            "refresh_model_menu": True,
                            "active_model": model_name,
                        }
            except Exception:
                log.exception(f"Failed to download model {model_name}")
                self._notify(f"Download failed for {model_name}")
                with self._state_lock:
                    self._set_state(State.IDLE)
                with self._pending_lock:
                    if self._pending_ui is not None:
                        self._pending_ui["settings_download_failed"] = model_name
                    else:
                        self._pending_ui = {"settings_download_failed": model_name}

        threading.Thread(target=_do_download, daemon=True, name="model-dl").start()

    def _ensure_default_model(self):
        """On first launch, download the default model if not cached."""
        model = self._config.model_name
        if is_whisper_cached(model):
            self._model_cache_status[model] = True
            log.info(f"Default model '{model}' already cached")
            # Kick off full cache check in background
            self._check_model_cache_status()
            return

        repo_id = MODEL_MAP[model]
        size = format_size(MODEL_SIZES_MB.get(model, 0))
        log.info(f"First launch: downloading {model} ({size})")

        with self._state_lock:
            self._set_state(
                State.DOWNLOADING,
                status=f"First launch: downloading {model} ({size})\u2026",
            )

        def _do_download():
            try:
                download_model(repo_id)
                self._model_cache_status[model] = True
                log.info(f"Default model '{model}' downloaded")
                with self._state_lock:
                    self._set_state(State.IDLE)
                self._notify(f"{model.title()} model ready!")
                with self._pending_lock:
                    if self._pending_ui is not None:
                        self._pending_ui["refresh_model_menu"] = True
                    else:
                        self._pending_ui = {"refresh_model_menu": True}
            except Exception:
                log.exception(f"Failed to download default model {model}")
                self._notify(f"Download failed for {model}. Restart to retry.")
                with self._state_lock:
                    self._set_state(State.IDLE)
            # Check remaining models' cache status
            self._check_model_cache_status()

        threading.Thread(target=_do_download, daemon=True, name="default-dl").start()

    def _on_cancel(self):
        with self._state_lock:
            if self._state != State.RECORDING:
                return
            if self._max_timer is not None:
                self._max_timer.cancel()
                self._max_timer = None
            self._recorder.stop()  # discard audio
            self._queue_sound(_SOUND_STOP)
            self._set_state(State.IDLE)
        log.info("Recording cancelled via Escape")

    def _on_hotkey(self):
        with self._state_lock:
            if self._state == State.DOWNLOADING:
                self._notify("Please wait, model is downloading\u2026")
                return
            if self._state == State.IDLE:
                self._set_state(State.RECORDING)
                self._start_recording()
            elif self._state == State.RECORDING:
                self._stop_and_transcribe()

    def _start_recording(self):
        """Start recording. Caller MUST hold _state_lock."""
        self._recording_start = time.time()
        self._recorder.start()
        self._queue_sound(_SOUND_START)
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

        self._queue_sound(_SOUND_STOP)
        if self._config.use_whisper_translate:
            self._set_state(State.TRANSLATING)
        else:
            self._set_state(State.PROCESSING)
        audio = self._recorder.stop()

        t = threading.Thread(
            target=self._transcribe_and_insert, args=(audio,), daemon=True
        )
        t.start()

    def _ensure_llm_downloaded(self):
        """Download the LLM if not cached. Caller is on a background thread."""
        if is_llm_cached():
            return
        size = format_size(LLM_SIZE_MB)
        log.info(f"LLM not cached, downloading ({size})")
        with self._state_lock:
            self._set_state(
                State.DOWNLOADING,
                status=f"Downloading language model ({size})\u2026",
            )
        download_model(LLM_MODEL_REPO)
        log.info("LLM download complete")

    def _transcribe_and_insert(self, audio):
        try:
            cfg = self._config

            # Step 1: Transcribe (optionally with Whisper's built-in → English)
            translate = cfg.use_whisper_translate
            text = self._transcriber.transcribe(
                audio,
                translate_to_english=translate,
            )
            if not text:
                self._notify("No speech detected.")
                with self._state_lock:
                    self._set_state(State.IDLE)
                return

            # Step 2: LLM cleanup (grammar, filler words, false starts)
            if cfg.cleanup:
                cleanup_lang = "en" if translate else cfg.language
                log.info(f"LLM cleanup: lang={cleanup_lang}")
                self._ensure_llm_downloaded()
                with self._state_lock:
                    self._set_state(State.PROCESSING, status="Processing\u2026")
                text = self._llm.cleanup(text, language=cleanup_lang)

            with self._state_lock:
                self._set_state(State.INSERTING)

            self._inserter.insert(text)

            with self._state_lock:
                self._set_state(State.IDLE, last_text=text)
            return

        except InsertionError as e:
            self._notify(f"Paste failed: {e}")
        except Exception as e:
            log.exception("Transcription/translation failed")
            self._notify(f"Failed: {type(e).__name__}")

        with self._state_lock:
            self._set_state(State.IDLE)


_LOCK_PATH = os.path.expanduser("~/.localwhisper.lock")


def _acquire_instance_lock():
    """Try to acquire single-instance lock. Returns lock file or None."""
    import fcntl
    lock_file = open(_LOCK_PATH, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        return lock_file
    except (BlockingIOError, OSError):
        lock_file.close()
        return None


if __name__ == "__main__":
    log.info("=== LocalWhisper starting (build 2) ===")
    lock = _acquire_instance_lock()
    if lock is None:
        log.info("Another instance is already running — exiting.")
        sys.exit(0)
    try:
        LocalWhisperApp().run()
    except Exception:
        log.exception("FATAL: uncaught exception")
        raise
    finally:
        lock.close()
        try:
            os.unlink(_LOCK_PATH)
        except OSError:
            pass
