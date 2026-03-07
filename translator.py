"""Local LLM for text cleanup via mlx-lm.

Uses a small instruction-tuned model (Llama-3.2-3B-Instruct, ~1.8GB 4-bit)
for cleaning up transcribed text. Lazy-loaded on first use.
"""
import logging

from config import LLM_MODEL_REPO

log = logging.getLogger("LocalWhisper")

# Language display names for prompts
_LANG_NAMES = {
    "de": "German",
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "ja": "Japanese",
    "zh": "Chinese",
    "ko": "Korean",
    "ru": "Russian",
}


class LLMProcessor:
    """Lazy-loaded local LLM for text cleanup."""

    def __init__(self, model_repo: str = LLM_MODEL_REPO):
        self._model_repo = model_repo
        self._model = None
        self._tokenizer = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return

        log.info(f"Loading LLM: {self._model_repo}")
        from mlx_lm import load

        self._model, self._tokenizer = load(self._model_repo)
        log.info("LLM loaded")

    _SYSTEM_MSG = (
        "You are a text processing assistant. "
        "Reply with ONLY the requested text. "
        "Never add introductions, explanations, labels, or commentary."
    )

    def _generate(self, prompt: str, max_tokens: int = 256) -> str:
        """Run a prompt through the LLM and return the response."""
        self._ensure_loaded()
        from mlx_lm import generate

        messages = [
            {"role": "system", "content": self._SYSTEM_MSG},
            {"role": "user", "content": prompt},
        ]
        chat_prompt = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

        response = generate(
            self._model,
            self._tokenizer,
            prompt=chat_prompt,
            max_tokens=max_tokens,
            verbose=False,
        )
        return self._strip_preamble(response.strip())

    @staticmethod
    def _strip_preamble(text: str) -> str:
        """Remove common LLM preamble patterns from the output."""
        import re
        # Strip lines like "Here is the cleaned text...:" etc.
        text = re.sub(
            r'^(?:Here(?:\'s| is) (?:the |a |my )?(?:rewritten|translated|cleaned|corrected|formal|casual)[\w\s,]*?[.:]\s*\n?)',
            '', text, flags=re.IGNORECASE
        )
        # Strip leading/trailing quotes the LLM sometimes wraps output in
        if len(text) > 2 and text[0] == '"' and text[-1] == '"':
            text = text[1:-1]
        return text.strip()

    def cleanup(self, text: str, language: str = "en") -> str:
        """Clean up transcribed text: fix grammar, remove fillers and false starts."""
        if not text.strip():
            return text

        lang_name = _LANG_NAMES.get(language, language)
        prompt = (
            f"Minimally clean up this {lang_name} transcription. "
            "Keep the speaker's exact words and sentence structure. "
            "ONLY do these things:\n"
            "- Remove filler words (um, uh, ah, like, you know)\n"
            "- Remove false starts and repeated words\n"
            "- Fix punctuation, capitalization, and spelling\n"
            "Do NOT rephrase, restructure, or reword anything. "
            f"Output ONLY the cleaned text.\n\n{text}"
        )

        result = self._generate(prompt, max_tokens=len(text) * 2)
        log.info(f"Cleanup ({lang_name}): {result[:80]}")
        return result
