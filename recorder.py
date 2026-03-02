import logging
import threading

import numpy as np
import sounddevice as sd

log = logging.getLogger("LocalWhisper")


class AudioRecorder:
    def __init__(self, sample_rate: int = 16_000):
        self._sample_rate = sample_rate
        self._device: int | None = None  # None = system default
        self._lock = threading.Lock()
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None

    def change_device(self, device_index: int | None) -> None:
        """Set the input device. None = system default."""
        self._device = device_index

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if status:
            log.warning(f"Audio callback status: {status}")
        with self._lock:
            self._frames.append(indata[:, 0].copy())

    def start(self) -> None:
        with self._lock:
            self._frames.clear()
        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="float32",
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        with self._lock:
            if not self._frames:
                return np.array([], dtype=np.float32)
            audio = np.concatenate(self._frames)
            self._frames.clear()

        return audio
