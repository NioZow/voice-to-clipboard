"""End-to-end pipeline: record -> STT -> normalize -> clipboard -> notify."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

from . import normalize, stt

logger = logging.getLogger(__name__)


def _platform_commands() -> tuple[str, list[str]]:
    """Return ``(clip_cmd, [args...])``-style commands for clipboard + notify."""
    if sys.platform == "darwin":
        clip = ("pbcopy", [])
        notify = (
            "osascript",
            ["-e", 'display notification "{}" with title "Voice STT"'],
        )
    else:
        clip = ("wl-copy", [])
        notify = ("notify-send", ["Voice STT", "{}"])
    return clip, notify


def copy_to_clipboard(text: str) -> None:
    if not text:
        return
    clip_bin, _ = _platform_commands()[0]
    if not shutil.which(clip_bin):
        logger.warning("Clipboard command %r not found; skipping copy", clip_bin)
        return
    try:
        subprocess.run([clip_bin], input=text.encode("utf-8"), check=False)
        logger.info("Copied to clipboard")
    except OSError as exc:
        logger.warning("Could not copy to clipboard: %s", exc)


def notify(message: str) -> None:
    _, (notify_bin, template) = _platform_commands()[1]
    if not shutil.which(notify_bin):
        logger.warning("Notification command %r not found; skipping notification", notify_bin)
        return
    args = [part.format(message) for part in template]
    try:
        subprocess.run([notify_bin, *args], check=False)
    except OSError as exc:
        logger.warning("Could not send notification: %s", exc)


def transcribe_file(
    audio_path: str | Path,
    lang: str | None = None,
    prompt: str | None = None,
    no_punct: bool = False,
    llm_fix: bool = False,
    stdout: bool = False,
    no_notify: bool = False,
) -> tuple[str, str]:
    """Transcribe + normalize ``audio_path``; return ``(raw_text, final_text)``."""
    raw_text, detected_lang, _prob = stt.transcribe(
        str(audio_path), lang=lang, prompt=prompt
    )
    logger.info("Detected language: %s", detected_lang)

    final_text = raw_text
    if raw_text:
        if not no_punct:
            final_text = normalize.punctuate(raw_text)
        if llm_fix:
            if no_punct:
                raise ValueError("--llm-fix is incompatible with --no-punct")
            final_text = normalize.llm_fix(final_text)

    if stdout:
        return raw_text, final_text

    copy_to_clipboard(final_text)
    if not no_notify:
        notify("Transcribed!")
    return raw_text, final_text


def run_pipeline(
    audio_path: str | Path,
    lang: str | None = None,
    prompt: str | None = None,
    no_punct: bool = False,
    llm_fix: bool = False,
    stdout: bool = False,
    no_notify: bool = False,
) -> tuple[str, str]:
    """Process a recorded file; convenience wrapper over ``transcribe_file``."""
    return transcribe_file(
        audio_path,
        lang=lang,
        prompt=prompt,
        no_punct=no_punct,
        llm_fix=llm_fix,
        stdout=stdout,
        no_notify=no_notify,
    )
