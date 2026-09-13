"""Speech-to-text with faster-whisper.

Models are auto-downloaded on first use to ``~/.cache/huggingface``.

The model name can be overridden with the ``VOICE_STT_MODEL`` environment
variable (useful for low-resource machines or testing); the default is the
high-quality ``large-v3-turbo``.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from faster_whisper import WhisperModel
from huggingface_hub.constants import HF_HUB_CACHE
from pathlib import Path

logger = logging.getLogger(__name__)

MODEL_NAME = "large-v3-turbo"

_model: WhisperModel | None = None


def _resolve_repo(name: str) -> str:
    """Resolve a bare Whisper size name to the full HuggingFace repo id."""
    from faster_whisper.utils import _MODELS

    return _MODELS.get(name, name)


def _is_cached(model_name: str) -> bool:
    """Return True if ``model_name`` already has a snapshot in the local HF cache."""
    cache_dir = Path(HF_HUB_CACHE) / f"models--{model_name.replace('/', '--')}"
    snapshots = cache_dir / "snapshots"
    return snapshots.is_dir() and any(snapshots.iterdir())


def get_model(device: str = "auto", compute_type: str = "default") -> WhisperModel:
    """Load (and cache) the Whisper model, honoring ``VOICE_STT_MODEL``."""
    global _model
    if _model is None:
        name = os.environ.get("VOICE_STT_MODEL", MODEL_NAME)
        local_files_only = _is_cached(_resolve_repo(name))
        logger.info(
            "Loading %s%s...", name, " (from local cache)" if local_files_only else " (first run downloads the model)"
        )
        _model = WhisperModel(
            name,
            device=device,
            compute_type=compute_type,
            local_files_only=local_files_only,
        )
    return _model


def transcribe(
    audio_path: str,
    lang: str | None = None,
    prompt: str | None = None,
) -> tuple[str, str, float]:
    """Transcribe ``audio_path`` and return ``(text, detected_lang, lang_prob)``."""
    model = get_model()
    segments, info = model.transcribe(
        audio_path,
        language=lang,
        beam_size=5,
        condition_on_previous_text=True,
        vad_filter=True,
        initial_prompt=prompt or None,
    )
    text = "".join(segment.text for segment in segments).strip()
    return text, info.language, info.language_probability


def reset_model() -> None:
    """Drop the cached model (mainly for tests)."""
    global _model
    _model = None


def get_model_metadata() -> dict[str, Any]:
    return {"model": os.environ.get("VOICE_STT_MODEL", MODEL_NAME)}