import logging
import time
import threading

from pynput import keyboard

log = logging.getLogger("LocalWhisper")

# Map config key names to pynput Key objects
_KEY_MAP = {
    "ctrl_l": keyboard.Key.ctrl_l,
    "ctrl_r": keyboard.Key.ctrl_r,
    "cmd_l": keyboard.Key.cmd_l,
    "cmd_r": keyboard.Key.cmd_r,
    "shift_l": keyboard.Key.shift_l,
    "shift_r": keyboard.Key.shift_r,
    "alt_l": keyboard.Key.alt_l,
    "alt_r": keyboard.Key.alt_r,
}

# Map pynput Key objects to modifier names used in combo strings
_MODIFIER_KEYS = {
    keyboard.Key.ctrl_l: "ctrl",
    keyboard.Key.ctrl_r: "ctrl",
    keyboard.Key.cmd_l: "cmd",
    keyboard.Key.cmd_r: "cmd",
    keyboard.Key.shift_l: "shift",
    keyboard.Key.shift_r: "shift",
    keyboard.Key.alt_l: "alt",
    keyboard.Key.alt_r: "alt",
}


def _parse_combo(combo_str: str):
    """Parse a combo like '<ctrl>+<shift>+d' into (frozenset of modifiers, trigger_char)."""
    parts = combo_str.lower().split("+")
    modifiers = set()
    trigger = None
    for p in parts:
        p = p.strip().strip("<>")
        if p in ("ctrl", "shift", "alt", "cmd"):
            modifiers.add(p)
        elif p == "space":
            trigger = keyboard.Key.space
        else:
            trigger = p  # single character like 'd'
    return frozenset(modifiers), trigger


class HotkeyListener:
    """Single persistent keyboard listener that supports hot-swapping shortcuts.

    Uses one keyboard.Listener for the lifetime of the app.
    Changing shortcuts only swaps internal detection logic — no event tap teardown.
    """

    def __init__(self, shortcut_config: dict, callback, cancel_callback=None, release_callback=None):
        self._callback = callback
        self._cancel_callback = cancel_callback
        self._release_callback = release_callback
        self._lock = threading.Lock()  # protects config fields
        self._listener: keyboard.Listener | None = None
        self._stop_event = threading.Event()

        # Current pressed modifiers
        self._pressed_modifiers: set[str] = set()

        # Configure initial shortcut
        self._apply_config(shortcut_config)

    def _apply_config(self, config: dict) -> None:
        """Set detection mode from config. Caller must hold _lock or be in __init__."""
        self._mode = config.get("type", "combo")

        if self._mode == "push_to_talk":
            key_name = config.get("key", "ctrl_l")
            self._ptt_key = _KEY_MAP.get(key_name)
            self._ptt_held = False
            # Clear other fields
            self._combo_modifiers = frozenset()
            self._combo_trigger = None
            self._tap_key = None
            self._last_release_time = 0.0
        elif self._mode == "double_tap":
            key_name = config.get("key", "ctrl_l")
            self._tap_key = _KEY_MAP.get(key_name)
            self._tap_interval = config.get("interval", 0.4)
            self._last_release_time = 0.0
            # Combo fields not used
            self._combo_modifiers = frozenset()
            self._combo_trigger = None
            self._ptt_key = None
            self._ptt_held = False
        else:
            combo_str = config.get("combo", "<ctrl>+<shift>+d")
            self._combo_modifiers, self._combo_trigger = _parse_combo(combo_str)
            # Double-tap fields not used
            self._tap_key = None
            self._tap_interval = 0.4
            self._last_release_time = 0.0
            self._ptt_key = None
            self._ptt_held = False

        log.info(f"Shortcut config applied: mode={self._mode}")

    def change_shortcut(self, config: dict) -> None:
        """Hot-swap shortcut without restarting the listener."""
        with self._lock:
            self._pressed_modifiers.clear()
            self._apply_config(config)

    def start(self) -> None:
        """Blocking — run in a daemon thread."""
        log.info("HotkeyListener.start() — creating single persistent Listener")
        try:
            self._listener = keyboard.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
            )
            self._listener.start()
            log.info("keyboard.Listener started, waiting on stop_event")
            self._stop_event.wait()
            log.info("stop_event set, cleaning up")
            try:
                self._listener.stop()
            except Exception:
                log.exception("Error stopping Listener")
        except Exception:
            log.exception("Error in HotkeyListener.start()")
        log.info("HotkeyListener.start() exiting")

    def stop(self) -> None:
        """Signal the listener to stop. Safe to call from any thread."""
        log.info("HotkeyListener.stop() called")
        self._stop_event.set()
        listener = self._listener
        if listener is not None:
            try:
                listener.stop()
            except Exception:
                log.exception("Error in listener.stop()")
            try:
                listener.join(timeout=2.0)
            except Exception:
                log.exception("Error in listener.join()")
        log.info("HotkeyListener.stop() done")

    # ── Event handlers ───────────────────────────────────

    def _on_press(self, key) -> None:
        # Log first few events to confirm listener is receiving input
        if not hasattr(self, "_event_count"):
            self._event_count = 0
        if self._event_count < 5:
            self._event_count += 1
            log.info(f"Key press event received: {key} (mode={self._mode})")

        # Escape always cancels, independent of shortcut mode
        if key == keyboard.Key.esc and self._cancel_callback is not None:
            try:
                self._cancel_callback()
            except Exception:
                log.exception("Error in cancel callback")
            return

        with self._lock:
            # Track modifier state
            mod = _MODIFIER_KEYS.get(key)
            if mod:
                self._pressed_modifiers.add(mod)

            if self._mode == "combo":
                self._check_combo(key)
            elif self._mode == "push_to_talk":
                self._check_ptt_press(key)

    def _on_release(self, key) -> None:
        with self._lock:
            if self._mode == "double_tap":
                self._check_doubletap(key)
            elif self._mode == "push_to_talk":
                self._check_ptt_release(key)

            # Untrack modifier
            mod = _MODIFIER_KEYS.get(key)
            if mod:
                self._pressed_modifiers.discard(mod)

    # ── Combo detection ──────────────────────────────────

    def _check_combo(self, key) -> None:
        """Check if current key press + held modifiers match the combo."""
        if not self._combo_modifiers:
            return

        # Check if the trigger key matches
        trigger = self._combo_trigger
        if trigger is None:
            return

        key_matches = False
        if isinstance(trigger, keyboard.Key):
            key_matches = (key == trigger)
        elif isinstance(trigger, str):
            try:
                key_matches = (hasattr(key, "char") and key.char == trigger)
            except AttributeError:
                pass

        if key_matches and self._pressed_modifiers >= self._combo_modifiers:
            self._fire()

    # ── Double-tap detection ─────────────────────────────

    def _check_doubletap(self, key) -> None:
        """Check if key release is a double-tap of the configured key."""
        if key != self._tap_key:
            return

        now = time.monotonic()
        elapsed = now - self._last_release_time

        if elapsed < self._tap_interval:
            self._last_release_time = 0.0  # reset to avoid triple-tap
            self._fire()
        else:
            self._last_release_time = now

    # ── Push-to-talk detection ────────────────────────────

    def _check_ptt_press(self, key) -> None:
        """Start recording on key press (ignore key-repeat)."""
        if key != self._ptt_key:
            return
        if self._ptt_held:
            return  # suppress key repeat
        self._ptt_held = True
        self._fire()

    def _check_ptt_release(self, key) -> None:
        """Stop recording on key release."""
        if key != self._ptt_key:
            return
        if not self._ptt_held:
            return
        self._ptt_held = False
        if self._release_callback is not None:
            try:
                self._release_callback()
            except Exception:
                log.exception("Error in release callback")

    # ── Callback ─────────────────────────────────────────

    def _fire(self) -> None:
        try:
            self._callback()
        except Exception:
            log.exception("Error in hotkey callback")
