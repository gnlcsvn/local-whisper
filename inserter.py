import logging
import time

log = logging.getLogger("LocalWhisper")


class InsertionError(Exception):
    """Raised when text insertion fails."""


def _get_clipboard() -> str:
    """Read current clipboard text using NSPasteboard."""
    try:
        from AppKit import NSPasteboard, NSPasteboardTypeString
        pb = NSPasteboard.generalPasteboard()
        return pb.stringForType_(NSPasteboardTypeString) or ""
    except Exception:
        return ""


def _set_clipboard(text: str) -> None:
    """Write text to clipboard using NSPasteboard."""
    from AppKit import NSPasteboard, NSPasteboardTypeString
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)


def _simulate_cmd_v() -> None:
    """Simulate Cmd+V keystroke using Quartz CGEvent (no subprocess)."""
    from Quartz import (
        CGEventCreateKeyboardEvent,
        CGEventPost,
        CGEventSetFlags,
        kCGHIDEventTap,
        kCGEventFlagMaskCommand,
    )

    # macOS virtual keycode for 'v' is 0x09
    V_KEYCODE = 0x09

    # Key down
    event_down = CGEventCreateKeyboardEvent(None, V_KEYCODE, True)
    CGEventSetFlags(event_down, kCGEventFlagMaskCommand)
    CGEventPost(kCGHIDEventTap, event_down)

    # Key up
    event_up = CGEventCreateKeyboardEvent(None, V_KEYCODE, False)
    CGEventSetFlags(event_up, kCGEventFlagMaskCommand)
    CGEventPost(kCGHIDEventTap, event_up)


class TextInserter:
    def __init__(self, restore_delay: float = 0.15):
        self._restore_delay = restore_delay

    def insert(self, text: str) -> None:
        """Insert text at cursor via clipboard + Cmd+V. No subprocesses."""
        if not text:
            return

        # Save current clipboard
        old_clipboard = _get_clipboard()

        try:
            # Set transcribed text to clipboard
            _set_clipboard(text)

            # Small delay to ensure clipboard is ready
            time.sleep(0.05)

            # Simulate Cmd+V
            _simulate_cmd_v()

            # Wait for paste to complete, then restore old clipboard
            time.sleep(self._restore_delay)
            _set_clipboard(old_clipboard)

        except Exception as e:
            log.exception("Insertion failed")
            # Try to restore clipboard
            try:
                _set_clipboard(old_clipboard)
            except Exception:
                pass
            raise InsertionError(f"Failed to paste text: {e}") from e
