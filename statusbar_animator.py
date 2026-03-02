"""
Animated statusbar icon for LocalWhisper.

Cycles through frame PNGs via rumps.App.icon to animate the
menubar icon for recording, processing, and downloading states.
"""

import os
import threading
import time

ICONS_DIR = "icons"


class StatusBarAnimator:
    """
    Animates the macOS menubar icon for LocalWhisper.

    Uses frame-by-frame PNG swapping via rumps.App.icon property.
    Template images (black + alpha) — macOS auto-tints for light/dark mode.

    States:
        idle:       Static lock+waveform icon
        recording:  6 frames, pulsing bars + red dot, ~8 FPS
        processing: 8 frames, rotating arc, ~6 FPS
        downloading: reuses processing frames (spinner)
    """

    def __init__(self, app, resource_path_fn):
        """
        Args:
            app: rumps.App instance
            resource_path_fn: callable that resolves relative paths
                              (handles PyInstaller bundling)
        """
        self.app = app
        self._rp = resource_path_fn
        self._thread = None
        self._running = False

        # Precompute frame paths
        self._idle_icon = self._rp(os.path.join(ICONS_DIR, "statusbar_idleTemplate.png"))
        self._rec_frames = [
            self._rp(os.path.join(ICONS_DIR, f"statusbar_rec_{i}Template.png"))
            for i in range(6)
        ]
        self._proc_frames = [
            self._rp(os.path.join(ICONS_DIR, f"statusbar_proc_{i}Template.png"))
            for i in range(8)
        ]

    def start_recording(self):
        """Start the recording animation (pulsing bars + red dot)."""
        self._start_animation(self._rec_frames, fps=8)

    def start_processing(self):
        """Start the processing animation (rotating arc)."""
        self._start_animation(self._proc_frames, fps=6)

    def start_downloading(self):
        """Start the downloading animation (reuses processing spinner)."""
        self._start_animation(self._proc_frames, fps=6)

    def stop(self):
        """Stop animation and return to idle icon."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        self.app.icon = self._idle_icon

    def _start_animation(self, frames, fps):
        """Start a frame animation loop in a background thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)

        self._running = True
        self._thread = threading.Thread(
            target=self._animate_loop,
            args=(frames, fps),
            daemon=True,
        )
        self._thread.start()

    def _animate_loop(self, frames, fps):
        """Cycle through frames at the given FPS."""
        interval = 1.0 / fps
        idx = 0
        while self._running:
            self.app.icon = frames[idx]
            idx = (idx + 1) % len(frames)
            time.sleep(interval)
