"""Model cache checking and download orchestration.

Provides fast local-only cache checks and blocking download calls
for Whisper models and the translation LLM, using huggingface_hub.
"""
import logging

from huggingface_hub import snapshot_download

from config import MODEL_MAP, MODEL_SIZES_MB, LLM_MODEL_REPO, LLM_SIZE_MB

log = logging.getLogger("LocalWhisper")


def format_size(mb: int) -> str:
    """Format megabytes as a human-readable string: '1.5 GB' or '460 MB'."""
    if mb >= 1000:
        return f"{mb / 1000:.1f} GB"
    return f"{mb} MB"


def is_model_cached(repo_id: str) -> bool:
    """Fast local-only check — True if the model is already downloaded."""
    try:
        snapshot_download(repo_id, local_files_only=True)
        return True
    except Exception:
        return False


def is_whisper_cached(model_name: str) -> bool:
    """Check if a Whisper model variant is cached."""
    repo_id = MODEL_MAP.get(model_name)
    if repo_id is None:
        return False
    return is_model_cached(repo_id)


def is_llm_cached() -> bool:
    """Check if the translation LLM is cached."""
    return is_model_cached(LLM_MODEL_REPO)


def download_model(repo_id: str) -> None:
    """Blocking download of a HuggingFace model. Run in a background thread."""
    log.info(f"Downloading model: {repo_id}")
    snapshot_download(repo_id)
    log.info(f"Download complete: {repo_id}")
