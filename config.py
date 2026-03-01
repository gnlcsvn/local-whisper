MODEL_MAP = {
    "tiny": "mlx-community/whisper-tiny",
    "small": "mlx-community/whisper-small",
    "turbo": "mlx-community/whisper-turbo",
    "medium": "mlx-community/whisper-medium",
    "large": "mlx-community/whisper-large-v3-turbo",
}


class Config:
    hotkey: str = "<ctrl>+<shift>+d"
    sample_rate: int = 16_000
    max_recording_seconds: int = 120
    language: str = "de"
    model_name: str = "turbo"

    @property
    def model_repo(self) -> str:
        return MODEL_MAP[self.model_name]
