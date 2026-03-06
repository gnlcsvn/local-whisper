"""Model cache checking, download, and deletion via huggingface_hub."""
import logging
import threading

from huggingface_hub import snapshot_download, scan_cache_dir

from config import MODEL_MAP, MODEL_SIZES_MB, LLM_MODEL_REPO, LLM_SIZE_MB

log = logging.getLogger("LocalWhisper")

# Protects scan_cache_dir / delete_revisions from concurrent access
_cache_lock = threading.Lock()


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
    """Check if the cleanup LLM is cached."""
    return is_model_cached(LLM_MODEL_REPO)


def download_model(repo_id: str) -> None:
    """Blocking download of a HuggingFace model. Run in a background thread."""
    log.info(f"Downloading model: {repo_id}")
    snapshot_download(repo_id)
    log.info(f"Download complete: {repo_id}")


def get_total_cache_size_str() -> str:
    """Return human-readable total size of all cached models."""
    try:
        with _cache_lock:
            info = scan_cache_dir()
        mb = info.size_on_disk / 1_000_000
        return format_size(int(mb))
    except Exception:
        log.exception("Failed to get cache size")
        return "unknown"


def delete_cached_model(repo_id: str) -> bool:
    """Delete a cached model by repo_id. Returns True on success."""
    try:
        with _cache_lock:
            info = scan_cache_dir()
            hashes = []
            for repo in info.repos:
                if repo.repo_id == repo_id:
                    for rev in repo.revisions:
                        hashes.append(rev.commit_hash)
                    break
            if not hashes:
                log.warning(f"Model {repo_id} not found in cache")
                return False
            strategy = info.delete_revisions(*hashes)
            log.info(f"Deleting {repo_id}: will free {strategy.expected_freed_size / 1e6:.0f} MB")
            strategy.execute()
        log.info(f"Deleted {repo_id}")
        return True
    except Exception:
        log.exception(f"Failed to delete {repo_id}")
        return False
