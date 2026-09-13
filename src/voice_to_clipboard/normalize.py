"""Text normalization: punctuation/casing, plus an optional tiny LLM fix.

Punctuation uses ``deepmultilingualpunctuation`` (EN+FR). The optional
``--llm-fix`` loads a small GGUF (Qwen2.5-0.5B-Instruct) in-process via
``llama-cpp-python`` to lightly fix transcription homophones/grammar.
"""

from __future__ import annotations

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

PUNCT_MODEL_NAME = "oliverguhr/fullstop-punctuation-multilingual-sonar-base"
LLM_REPO = "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
LLM_FILENAME = "qwen2.5-0.5b-instruct-q4_k_m.gguf"

_LLM_FIX_SYSTEM = (
    "You are a careful transcription editor. Fix obvious speech-to-text errors, "
    "homophones and grammar, preserving the original language and meaning exactly. "
    "Do not translate, rephrase, or add commentary. Output only the corrected text."
)


@lru_cache(maxsize=1)
def _get_punct_model():
    from deepmultilingualpunctuation import PunctuationModel

    logger.info("Loading punctuation model %s...", PUNCT_MODEL_NAME)
    return PunctuationModel(model=PUNCT_MODEL_NAME)


def punctuate(text: str) -> str:
    """Restore punctuation and casing for ``text`` (supports EN+FR)."""
    if not text:
        return text
    try:
        return _get_punct_model().restore_punctuation(text)
    except Exception as exc:  # noqa: BLE001 - never abort the pipeline
        logger.warning("Punctuation failed (%s); returning raw text", exc)
        return text


@lru_cache(maxsize=1)
def _get_llm(model_path: str):
    from llama_cpp import Llama

    logger.info("Loading LLM from %s...", model_path)
    return Llama(model_path=model_path, n_ctx=1024, n_threads=None, verbose=False)


def llm_model_path() -> str:
    from huggingface_hub import hf_hub_download

    return hf_hub_download(LLM_REPO, LLM_FILENAME)


def llm_fix(text: str, model_path: str | None = None) -> str:
    """Lightly fix ``text`` with an in-process tiny LLM."""
    if not text:
        return text
    path = model_path or llm_model_path()
    llm = _get_llm(path)
    prompt = f"{_LLM_FIX_SYSTEM}\n\nTranscription:\n{text}\n\nCorrected text:"
    out = llm(prompt, max_tokens=256, temperature=0.1, top_p=0.9, repeat_penalty=1.1)
    corrected = out["choices"][0]["text"].strip()
    return corrected or text


def reset_models() -> None:
    _get_punct_model.cache_clear()
    _get_llm.cache_clear()