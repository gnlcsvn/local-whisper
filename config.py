MODEL_MAP = {
    "tiny": "mlx-community/whisper-tiny",
    "small": "mlx-community/whisper-small",
    "turbo": "mlx-community/whisper-turbo",
    "medium": "mlx-community/whisper-medium",
    "large": "mlx-community/whisper-large-v3-turbo",
}

MODEL_SIZES_MB = {"tiny": 75, "small": 460, "turbo": 1500, "medium": 1500, "large": 3000}

DEFAULT_MODEL = "turbo"

LLM_MODEL_REPO = "mlx-community/Llama-3.2-3B-Instruct-4bit"
LLM_SIZE_MB = 1800

# Models that support translation (turbo variants were NOT trained on translation data)
TRANSLATION_CAPABLE_MODELS = {"tiny", "small", "medium"}
# Best model for translation when user's selected model can't translate
TRANSLATION_FALLBACK_MODEL = "medium"

# Supported languages with their codes
LANGUAGES = {
    "de": "Deutsch",
    "en": "English",
    "fr": "Fran\u00e7ais",
    "es": "Espa\u00f1ol",
    "it": "Italiano",
    "pt": "Portugu\u00eas",
    "nl": "Nederlands",
    "pl": "Polski",
    "ja": "\u65e5\u672c\u8a9e",
    "zh": "\u4e2d\u6587",
    "ko": "\ud55c\uad6d\uc5b4",
    "ru": "\u0420\u0443\u0441\u0441\u043a\u0438\u0439",
    "auto": "Auto-detect",
}

# Max recording duration presets (seconds -> display label)
RECORDING_DURATIONS = {
    30: "30 seconds",
    60: "1 minute",
    120: "2 minutes",
    300: "5 minutes",
    600: "10 minutes",
}

# Text processing styles (LLM post-processing of transcription)
TEXT_STYLES = {
    "off": "Off",
    "clean": "Clean up",
    "formal": "Formal",
    "casual": "Casual",
}

# Shortcut presets: id -> (display_label, type, config)
SHORTCUT_PRESETS = {
    "ctrl_shift_d": {
        "label": "\u2303\u21e7D  (Ctrl+Shift+D)",
        "type": "combo",
        "combo": "<ctrl>+<shift>+d",
    },
    "ctrl_shift_space": {
        "label": "\u2303\u21e7Space  (Ctrl+Shift+Space)",
        "type": "combo",
        "combo": "<ctrl>+<shift>+<space>",
    },
    "double_ctrl": {
        "label": "Double-tap Left Ctrl",
        "type": "double_tap",
        "key": "ctrl_l",
        "interval": 0.4,
    },
    "double_cmd": {
        "label": "Double-tap Right \u2318  (Cmd)",
        "type": "double_tap",
        "key": "cmd_r",
        "interval": 0.4,
    },
    "double_shift": {
        "label": "Double-tap Left Shift",
        "type": "double_tap",
        "key": "shift_l",
        "interval": 0.4,
    },
}


class Config:
    shortcut: str = "ctrl_shift_d"
    sample_rate: int = 16_000
    max_recording_seconds: int = 120
    language: str = "de"           # input language (what you speak)
    output_language: str = "de"    # output language (what gets typed)
    translate: bool = False        # enable translation mode
    text_style: str = "off"        # off, clean, formal, casual
    model_name: str = "turbo"
    input_device: str | None = None  # None = system default; otherwise device name

    @property
    def hotkey(self) -> str:
        """Legacy compat — returns combo string for combo-type shortcuts."""
        preset = SHORTCUT_PRESETS.get(self.shortcut, {})
        return preset.get("combo", "<ctrl>+<shift>+d")

    @property
    def model_repo(self) -> str:
        return MODEL_MAP[self.model_name]

    @property
    def needs_translation(self) -> bool:
        """True if translate is on and input != output."""
        return self.translate and self.language != self.output_language

    @property
    def whisper_can_translate(self) -> bool:
        """True if Whisper can handle the translation natively (→ English only)."""
        return self.needs_translation and self.output_language == "en"

    @property
    def needs_text_processing(self) -> bool:
        """True if LLM text processing (clean/formal/casual) is enabled."""
        return self.text_style != "off"

    @property
    def needs_llm(self) -> bool:
        """True if any LLM processing is needed (style or translation)."""
        return self.needs_text_processing or (self.needs_translation and not self.whisper_can_translate)
