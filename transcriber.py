import numpy as np
import mlx_whisper

from config import MODEL_MAP


class TranscriptionError(Exception):
    """Raised when transcription fails."""


class WhisperTranscriber:
    def __init__(self, model_name: str = "turbo", language: str = "de"):
        self._model_name = model_name
        self._language = language

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio. Returns text, or raises TranscriptionError."""
        if audio.size == 0:
            return ""
        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=MODEL_MAP[self._model_name],
            language=self._language if self._language != "auto" else None,
        )
        return result["text"].strip()

    def change_model(self, model_name: str) -> None:
        self._model_name = model_name

    def change_language(self, language: str) -> None:
        self._language = language
