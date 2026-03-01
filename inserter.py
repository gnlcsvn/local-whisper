import subprocess
import time


class InsertionError(Exception):
    """Raised when text insertion fails."""


class TextInserter:
    def __init__(self, restore_delay: float = 0.1):
        self._restore_delay = restore_delay

    def insert(self, text: str) -> None:
        """Insert text at cursor. Raises InsertionError on failure."""
        if not text:
            return

        # Save current clipboard
        try:
            old_clipboard = subprocess.run(
                ["pbpaste"], capture_output=True, text=True, timeout=2
            ).stdout
        except Exception:
            old_clipboard = ""

        try:
            # Set new text to clipboard
            subprocess.run(
                ["pbcopy"], input=text, text=True, timeout=2, check=True
            )

            # Simulate Cmd+V
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to keystroke "v" using command down',
                ],
                timeout=5,
                check=True,
            )

            # Wait then restore old clipboard
            time.sleep(self._restore_delay)
            subprocess.run(
                ["pbcopy"], input=old_clipboard, text=True, timeout=2
            )
        except subprocess.CalledProcessError as e:
            # Restore clipboard before raising
            try:
                subprocess.run(
                    ["pbcopy"], input=old_clipboard, text=True, timeout=2
                )
            except Exception:
                pass
            raise InsertionError(
                f"Failed to paste text: {e}"
            ) from e
        except subprocess.TimeoutExpired as e:
            try:
                subprocess.run(
                    ["pbcopy"], input=old_clipboard, text=True, timeout=2
                )
            except Exception:
                pass
            raise InsertionError(
                "Paste timed out \u2013 check Accessibility permissions"
            ) from e
