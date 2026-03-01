"""Local LLM for translation and text processing via mlx-lm.

Uses a small instruction-tuned model (Llama-3.2-3B-Instruct, ~1.8GB 4-bit)
for translation, rephrasing, and text cleanup. Lazy-loaded on first use.
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
    """Lazy-loaded local LLM for text processing tasks."""

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

    def _generate(self, prompt: str, max_tokens: int = 256) -> str:
        """Run a prompt through the LLM and return the response."""
        self._ensure_loaded()
        from mlx_lm import generate

        messages = [{"role": "user", "content": prompt}]
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
        return response.strip()

    # ── Translation ──────────────────────────────────────

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Translate text between languages.

        For source_lang="auto", the LLM will auto-detect.
        """
        if not text.strip() or source_lang == target_lang:
            return text

        src_name = _LANG_NAMES.get(source_lang, source_lang)
        tgt_name = _LANG_NAMES.get(target_lang, target_lang)

        if source_lang == "auto":
            prompt = (
                f"Translate the following text to {tgt_name}. "
                f"Output ONLY the translation, nothing else.\n\n{text}"
            )
        else:
            prompt = (
                f"Translate the following {src_name} text to {tgt_name}. "
                f"Output ONLY the translation, nothing else.\n\n{text}"
            )

        result = self._generate(prompt, max_tokens=len(text) * 3)
        log.info(f"Translation ({src_name}->{tgt_name}): {result[:80]}")
        return result

    # ── Rephrase / cleanup (for future use) ──────────────

    def rephrase(self, text: str, style: str = "clean") -> str:
        """Rephrase or clean up transcribed text.

        Styles:
            clean   - fix punctuation, capitalization, minor errors
            formal  - rewrite in formal/professional tone
            casual  - rewrite in casual/friendly tone
            concise - condense to key points
        """
        if not text.strip():
            return text

        style_instructions = {
            "clean": (
                "Clean up this transcribed speech. Fix punctuation, "
                "capitalization, and obvious transcription errors. "
                "Keep the original meaning and language. "
                "Output ONLY the cleaned text."
            ),
            "formal": (
                "Rewrite this text in a formal, professional tone. "
                "Keep the same language. Output ONLY the rewritten text."
            ),
            "casual": (
                "Rewrite this text in a casual, friendly tone. "
                "Keep the same language. Output ONLY the rewritten text."
            ),
            "concise": (
                "Condense this text to its key points. "
                "Keep the same language. Output ONLY the condensed text."
            ),
        }

        instruction = style_instructions.get(style, style_instructions["clean"])
        prompt = f"{instruction}\n\n{text}"

        result = self._generate(prompt, max_tokens=len(text) * 2)
        log.info(f"Rephrase ({style}): {result[:80]}")
        return result
