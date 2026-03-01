MODEL_MAP = {
    "tiny": "mlx-community/whisper-tiny",
    "small": "mlx-community/whisper-small",
    "turbo": "mlx-community/whisper-turbo",
    "medium": "mlx-community/whisper-medium",
    "large": "mlx-community/whisper-large-v3-turbo",
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
    language: str = "de"
    model_name: str = "turbo"

    @property
    def hotkey(self) -> str:
        """Legacy compat — returns combo string for combo-type shortcuts."""
        preset = SHORTCUT_PRESETS.get(self.shortcut, {})
        return preset.get("combo", "<ctrl>+<shift>+d")

    @property
    def model_repo(self) -> str:
        return MODEL_MAP[self.model_name]
