import enum
import json
import logging
import os
import sys
import time
import threading
import traceback

import rumps

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
)
from model_manager import (
    is_whisper_cached, is_llm_cached, is_model_cached,
    download_model, format_size,
)
from recorder import AudioRecorder
from transcriber import WhisperTranscriber
from translator import LLMProcessor
from inserter import TextInserter, InsertionError
from hotkey import HotkeyListener


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
    INSERTING = "inserting"


# When using an icon, title is text shown *next to* the icon
MENUBAR_TITLES = {
    State.IDLE: "",                      # icon only
    State.DOWNLOADING: "\u2b07",         # ⬇
    State.RECORDING: "\U0001f534 Rec",   # 🔴 Rec
    State.PROCESSING: "\u23f3",          # ⏳
    State.INSERTING: "\u23f3",           # ⏳
}

STATUS_LABELS = {
    State.IDLE: "Ready",
    State.DOWNLOADING: "Downloading\u2026",
    State.RECORDING: "Recording\u2026",
    State.PROCESSING: "Processing\u2026",
    State.INSERTING: "Pasting\u2026",
}

# Build display_name -> code mapping from config's code -> name mapping
LANGUAGES = {name: code for code, name in LANG_CODES.items()}
# Output languages (no "auto-detect" — you must pick a target)
OUTPUT_LANGUAGES = {name: code for code, name in LANG_CODES.items() if code != "auto"}

MODEL_LABELS = {
    "tiny": "Tiny  \u2013  fastest, least accurate",
    "small": "Small  \u2013  fast, good accuracy",
    "turbo": "Turbo  \u2013  balanced (recommended)",
    "medium": "Medium  \u2013  slower, better accuracy",
    "large": "Large  \u2013  slowest, best accuracy",
}

SETTINGS_PATH = os.path.expanduser("~/.localwhisper.json")

# System sounds for recording feedback
_SOUND_START = "/System/Library/Sounds/Tink.aiff"
_SOUND_STOP = "/System/Library/Sounds/Pop.aiff"
_NSSound = None

# ── Custom NSView for toggle menu items that keep the menu open ──

_ToggleViewClass = None


def _make_toggle_view(title, checked, callback):
    """Create a custom view for a menu item toggle.

    NSMenuItem with a custom view does NOT close the menu when clicked,
    matching macOS system behaviour (e.g. Battery → Low Power Mode).
    """
    global _ToggleViewClass

    if _ToggleViewClass is None:
        from AppKit import (
            NSView as _NSView,
            NSFont as _NSFont,
            NSColor as _NSColor,
            NSTrackingArea as _NSTrackingArea,
            NSBezierPath as _NSBezierPath,
            NSAttributedString as _NSAttrStr,
            NSFontAttributeName as _kFont,
            NSForegroundColorAttributeName as _kColor,
        )
        from Foundation import NSMakeRect as _NSMakeRect, NSMakePoint as _NSMakePoint
        import objc as _objc

        class _ToggleView(_NSView):
            """Renders a checkmark + title, highlights on hover, toggles on click."""

            def drawRect_(self, dirty):
                bounds = self.bounds()
                highlighted = getattr(self, "_highlighted", False)
                checked_ = getattr(self, "_checked", False)

                if highlighted:
                    _NSColor.selectedMenuItemColor().setFill()
                    _NSBezierPath.fillRect_(bounds)
                    color = _NSColor.selectedMenuItemTextColor()
                else:
                    color = _NSColor.labelColor()

                font = _NSFont.menuFontOfSize_(14)
                attrs = {_kFont: font, _kColor: color}

                if checked_:
                    s = _NSAttrStr.alloc().initWithString_attributes_("\u2713", attrs)
                    s.drawAtPoint_(_NSMakePoint(6, 3))

                t = _NSAttrStr.alloc().initWithString_attributes_(
                    getattr(self, "_title", ""), attrs
                )
                t.drawAtPoint_(_NSMakePoint(22, 3))

            def mouseEntered_(self, event):
                self._highlighted = True
                self.setNeedsDisplay_(True)

            def mouseExited_(self, event):
                self._highlighted = False
                self.setNeedsDisplay_(True)

            def mouseUp_(self, event):
                cb = getattr(self, "_cb", None)
                if cb:
                    cb()

        _ToggleViewClass = _ToggleView

    from Foundation import NSMakeRect as _R
    from AppKit import NSTrackingArea as _TA

    view = _ToggleViewClass.alloc().initWithFrame_(_R(0, 0, 250, 22))
    view._title = title
    view._checked = checked
    view._highlighted = False
    view._cb = callback

    opts = 0x01 | 0x40 | 0x200  # EnteredAndExited | ActiveInActiveApp | InVisibleRect
    ta = _TA.alloc().initWithRect_options_owner_userInfo_(view.bounds(), opts, view, None)
    view.addTrackingArea_(ta)

    return view


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


def _load_settings(config: Config) -> None:
    try:
        with open(SETTINGS_PATH) as f:
            data = json.load(f)
        if data.get("model_name") in MODEL_MAP:
            config.model_name = data["model_name"]
        lang = data.get("language", "")
        if lang in LANG_CODES:
            config.language = lang
        out_lang = data.get("output_language", "")
        if out_lang in LANG_CODES and out_lang != "auto":
            config.output_language = out_lang
        if isinstance(data.get("translate"), bool):
            config.translate = data["translate"]
        shortcut = data.get("shortcut", "")
        if shortcut in SHORTCUT_PRESETS:
            config.shortcut = shortcut
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass


def _save_settings(config: Config) -> None:
    try:
        with open(SETTINGS_PATH, "w") as f:
            json.dump(
                {
                    "model_name": config.model_name,
                    "language": config.language,
                    "output_language": config.output_language,
                    "translate": config.translate,
                    "shortcut": config.shortcut,
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
        icon_path = _resource_path("statusbar_iconTemplate@2x.png")
        super().__init__(
            "LocalWhisper",
            title=MENUBAR_TITLES[State.IDLE],
            icon=icon_path if os.path.exists(icon_path) else None,
            template=True,
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
        self._hotkey_listener: HotkeyListener | None = None

        self._recorder = AudioRecorder(sample_rate=self._config.sample_rate)
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

        self._build_menu()
        self._start_hotkey()

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

        self._last_text_header = rumps.MenuItem("Last transcription:", callback=None)
        self._last_text_header.set_callback(None)
        self._last_text_item = rumps.MenuItem("\u2014", callback=None)
        self._last_text_item.set_callback(None)

        self._model_menu = rumps.MenuItem("Model")
        for name in MODEL_MAP:
            label = self._model_menu_label(name)
            item = rumps.MenuItem(label, callback=self._on_model_select)
            item._model_key = name
            item.state = name == self._config.model_name
            self._model_menu.add(item)

        # Input language (what you speak)
        self._input_lang_menu = rumps.MenuItem("Input Language")
        for display, code in LANGUAGES.items():
            item = rumps.MenuItem(display, callback=self._on_input_lang_select)
            item._lang_code = code
            item.state = code == self._config.language
            self._input_lang_menu.add(item)

        # Translation toggle — uses a custom NSView so the menu stays open
        self._translate_item = rumps.MenuItem("Translate")
        self._translate_item.set_callback(None)  # view handles clicks
        self._translate_view = _make_toggle_view(
            "Translate", self._config.translate, self._on_translate_toggle_view
        )
        self._translate_item._menuitem.setView_(self._translate_view)

        self._output_lang_menu = rumps.MenuItem("Output Language")
        for display, code in OUTPUT_LANGUAGES.items():
            item = rumps.MenuItem(display, callback=self._on_output_lang_select)
            item._lang_code = code
            item.state = code == self._config.output_language
            self._output_lang_menu.add(item)

        # Translation info display
        self._translate_info = rumps.MenuItem(
            self._translate_info_text(), callback=None
        )
        self._translate_info.set_callback(None)

        # Shortcut submenu
        self._shortcut_menu = rumps.MenuItem("Shortcut")
        for preset_id, preset_info in SHORTCUT_PRESETS.items():
            item = rumps.MenuItem(
                preset_info["label"], callback=self._on_shortcut_select
            )
            item._preset_id = preset_id
            item.state = preset_id == self._config.shortcut
            self._shortcut_menu.add(item)

        about = rumps.MenuItem("About LocalWhisper", callback=self._on_about)
        quit_item = rumps.MenuItem("Quit LocalWhisper", callback=self._on_quit)

        self.menu = [
            self._status_item,
            self._shortcut_item,
            self._translate_info,
            None,
            self._last_text_header,
            self._last_text_item,
            None,
            self._model_menu,
            self._input_lang_menu,
            None,
            self._translate_item,
            self._output_lang_menu,
            None,
            self._shortcut_menu,
            None,
            about,
            quit_item,
        ]

    def _translate_info_text(self) -> str:
        """Build the info string like 'Deutsch → English' or 'Deutsch'."""
        in_name = LANG_CODES.get(self._config.language, self._config.language)
        if self._config.translate and self._config.needs_translation:
            out_name = LANG_CODES.get(
                self._config.output_language, self._config.output_language
            )
            return f"{in_name} \u2192 {out_name}"
        return f"{in_name}"

    def _update_translate_info(self):
        self._translate_info.title = self._translate_info_text()

    def _model_menu_label(self, name: str) -> str:
        """Build a model menu label with size and cache status."""
        base = MODEL_LABELS.get(name, name)
        size = format_size(MODEL_SIZES_MB.get(name, 0))
        cached = self._model_cache_status.get(name)
        if cached is True:
            return f"{base}  [{size}, downloaded]"
        return f"{base}  [{size}]"

    def _refresh_model_menu(self):
        """Update all model menu item labels (call from main thread)."""
        for item in self._model_menu.values():
            name = getattr(item, "_model_key", None)
            if name:
                item.title = self._model_menu_label(name)

    def _check_model_cache_status(self):
        """Check cache status for all models on a background thread."""
        def _check():
            for name in MODEL_MAP:
                self._model_cache_status[name] = is_whisper_cached(name)
            log.info(f"Model cache status: {self._model_cache_status}")
            with self._pending_lock:
                if self._pending_ui is not None:
                    self._pending_ui["refresh_model_menu"] = True
                else:
                    self._pending_ui = {"refresh_model_menu": True}
        threading.Thread(target=_check, daemon=True, name="cache-check").start()

    def _on_model_select(self, sender):
        key = sender._model_key
        if key == self._config.model_name:
            return

        with self._state_lock:
            if self._state == State.DOWNLOADING:
                return  # already downloading something

        cached = self._model_cache_status.get(key)
        if cached is True:
            # Instant switch
            self._config.model_name = key
            self._transcriber.change_model(key)
            for item in self._model_menu.values():
                item.state = getattr(item, "_model_key", None) == key
            _save_settings(self._config)
        else:
            # Need to download first
            self._download_and_switch_model(key)

    def _on_input_lang_select(self, sender):
        code = sender._lang_code
        self._config.language = code
        self._transcriber.change_language(code)
        for item in self._input_lang_menu.values():
            item.state = getattr(item, "_lang_code", None) == code
        self._update_translate_info()
        _save_settings(self._config)

    def _on_output_lang_select(self, sender):
        code = sender._lang_code
        self._config.output_language = code
        for item in self._output_lang_menu.values():
            item.state = getattr(item, "_lang_code", None) == code
        self._update_translate_info()
        _save_settings(self._config)

    def _on_translate_toggle_view(self):
        """Called by the custom toggle view — menu stays open."""
        self._config.translate = not self._config.translate
        self._translate_view._checked = self._config.translate
        self._translate_view.setNeedsDisplay_(True)
        self._update_translate_info()
        _save_settings(self._config)

    def _on_shortcut_select(self, sender):
        try:
            preset_id = sender._preset_id
            log.info(f"Shortcut select: {preset_id} (current: {self._config.shortcut})")
            if preset_id == self._config.shortcut:
                return

            self._config.shortcut = preset_id
            for item in self._shortcut_menu.values():
                item.state = getattr(item, "_preset_id", None) == preset_id

            # Update display label
            preset = SHORTCUT_PRESETS[preset_id]
            self._shortcut_item.title = f"Shortcut: {preset['label']}"

            _save_settings(self._config)

            # Hot-swap shortcut detection (no listener restart needed)
            if self._hotkey_listener is not None:
                self._hotkey_listener.change_shortcut(preset)
            log.info(f"Shortcut changed to {preset_id}")
        except Exception:
            log.exception("Error in _on_shortcut_select")

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
        self._hotkey_listener = HotkeyListener(preset, self._on_hotkey)
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
                # Blink the red dot every 0.5s for visual pulse
                dot = "\U0001f534" if int(elapsed * 2) % 2 == 0 else "\u26ab"
                self.title = f"{dot} Rec"
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
            self._refresh_model_menu()
        if "active_model" in update:
            active = update["active_model"]
            for item in self._model_menu.values():
                item.state = getattr(item, "_model_key", None) == active

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
        self._set_state(State.PROCESSING)
        audio = self._recorder.stop()

        t = threading.Thread(
            target=self._transcribe_and_insert, args=(audio,), daemon=True
        )
        t.start()

    def _transcribe_and_insert(self, audio):
        try:
            cfg = self._config

            # Step 1: Transcribe (optionally with Whisper's built-in → English)
            use_whisper_translate = cfg.whisper_can_translate
            text = self._transcriber.transcribe(
                audio,
                translate_to_english=use_whisper_translate,
            )
            if not text:
                self._notify("No speech detected.")
                with self._state_lock:
                    self._set_state(State.IDLE)
                return

            # Step 2: If translation needed and Whisper didn't handle it,
            # use LLM for any-to-any translation
            if cfg.needs_translation and not use_whisper_translate:
                log.info(
                    f"LLM translation: {cfg.language} -> {cfg.output_language}"
                )

                # Download the LLM if not cached
                if not is_llm_cached():
                    size = format_size(LLM_SIZE_MB)
                    log.info(f"LLM not cached, downloading ({size})")
                    with self._state_lock:
                        self._set_state(
                            State.DOWNLOADING,
                            status=f"Downloading translation model ({size})\u2026",
                        )
                    download_model(LLM_MODEL_REPO)
                    log.info("LLM download complete")

                with self._state_lock:
                    self._set_state(
                        State.PROCESSING, status="Translating\u2026"
                    )

                # If input is auto-detect, we transcribed but don't know the
                # source lang. Use "auto" so the LLM auto-detects.
                src = cfg.language if cfg.language != "auto" else "auto"
                text = self._llm.translate(
                    text, src, cfg.output_language
                )

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
