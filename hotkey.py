from pynput import keyboard


class HotkeyListener:
    def __init__(self, hotkey: str, callback):
        self._hotkey = hotkey
        self._callback = callback
        self._listener: keyboard.GlobalHotKeys | None = None

    def start(self) -> None:
        """Blocking — run in a daemon thread."""
        self._listener = keyboard.GlobalHotKeys(
            {self._hotkey: self._safe_callback}
        )
        self._listener.start()
        self._listener.join()

    def _safe_callback(self) -> None:
        try:
            self._callback()
        except Exception:
            pass

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
