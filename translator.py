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
        # Strip lines like "Here is the rewritten text...:" or "Here's the translation:"
        text = re.sub(
            r'^(?:Here(?:\'s| is) (?:the |a |my )?(?:rewritten|translated|cleaned|corrected|formal|casual)[\w\s,]*?[.:]\s*\n?)',
            '', text, flags=re.IGNORECASE
        )
        # Strip leading/trailing quotes the LLM sometimes wraps output in
        if len(text) > 2 and text[0] == '"' and text[-1] == '"':
            text = text[1:-1]
        return text.strip()

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

    # ── Text processing ─────────────────────────────────

    _STYLE_INSTRUCTIONS = {
        "clean": (
            "Fix punctuation, capitalization, spelling, and grammar in this {lang} text. "
            "Do not change the meaning or add new content. "
            "Reply in {lang} only."
        ),
        "formal": (
            "Make the tone of this {lang} text slightly more polished and professional. "
            "Fix punctuation, spelling, and grammar. "
            "Do not change the meaning, do not add or remove sentences. "
            "Reply in {lang} only."
        ),
        "casual": (
            "Make the tone of this {lang} text slightly more conversational. "
            "Fix punctuation, spelling, and grammar. "
            "Do not change the meaning, do not add or remove sentences. "
            "Reply in {lang} only."
        ),
    }

    _STYLE_TRANSLATE_INSTRUCTIONS = {
        "clean": (
            "Translate the following text to {target}. "
            "Fix punctuation, capitalization, spelling, and grammar errors. "
            "Output ONLY the translated and cleaned text."
        ),
        "formal": (
            "Translate the following text to {target} in a formal, professional tone. "
            "Fix any errors. Output ONLY the result."
        ),
        "casual": (
            "Translate the following text to {target} in a casual, conversational tone. "
            "Fix any errors. Output ONLY the result."
        ),
    }

    def rephrase(self, text: str, style: str = "clean", language: str = "en") -> str:
        """Rephrase or clean up transcribed text (same language)."""
        if not text.strip():
            return text

        lang_name = _LANG_NAMES.get(language, language)
        template = self._STYLE_INSTRUCTIONS.get(style, self._STYLE_INSTRUCTIONS["clean"])
        instruction = template.format(lang=lang_name)
        prompt = f"{instruction}\n\n{text}"

        result = self._generate(prompt, max_tokens=len(text) * 2)
        log.info(f"Rephrase ({style}, {lang_name}): {result[:80]}")
        return result

    def translate_and_rephrase(self, text: str, source_lang: str,
                                target_lang: str, style: str) -> str:
        """Translate and apply text style in a single LLM call."""
        if not text.strip():
            return text

        tgt_name = _LANG_NAMES.get(target_lang, target_lang)
        template = self._STYLE_TRANSLATE_INSTRUCTIONS.get(
            style, self._STYLE_TRANSLATE_INSTRUCTIONS["clean"]
        )
        instruction = template.format(target=tgt_name)

        src_name = _LANG_NAMES.get(source_lang, source_lang)
        if source_lang != "auto":
            instruction = instruction.replace(
                "the following text",
                f"the following {src_name} text",
            )

        prompt = f"{instruction}\n\n{text}"
        result = self._generate(prompt, max_tokens=len(text) * 3)
        log.info(f"Translate+rephrase ({src_name}->{tgt_name}, {style}): {result[:80]}")
        return result
