import logging

import numpy as np
import mlx_whisper

from config import (
    MODEL_MAP,
    LANGUAGES,
    TRANSLATION_CAPABLE_MODELS,
    TRANSLATION_FALLBACK_MODEL,
)

log = logging.getLogger("LocalWhisper")


class TranscriptionError(Exception):
    """Raised when transcription fails."""


class WhisperTranscriber:
    def __init__(self, model_name: str = "turbo", language: str = "de"):
        self._model_name = model_name
        self._language = language

    def transcribe(
        self,
        audio: np.ndarray,
        *,
        translate_to_english: bool = False,
    ) -> str:
        """Transcribe audio. Optionally translate to English via Whisper.

        Args:
            audio: float32 numpy array of audio samples
            translate_to_english: if True, use Whisper's task="translate"
                (outputs English regardless of input language)
        """
        if audio.size == 0:
            return ""

        # Pick model: turbo can't translate, fall back to medium
        model_name = self._model_name
        if translate_to_english and model_name not in TRANSLATION_CAPABLE_MODELS:
            model_name = TRANSLATION_FALLBACK_MODEL
            log.info(
                f"Model '{self._model_name}' can't translate, "
                f"using '{model_name}' for translation"
            )

        task = "translate" if translate_to_english else "transcribe"
        lang = self._language if self._language != "auto" else None

        log.info(
            f"Whisper: model={model_name}, task={task}, "
            f"language={lang or 'auto'}"
        )

        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=MODEL_MAP[model_name],
            language=lang,
            task=task,
        )
        return result["text"].strip()

    def change_model(self, model_name: str) -> None:
        self._model_name = model_name

    def change_language(self, language: str) -> None:
        self._language = language
