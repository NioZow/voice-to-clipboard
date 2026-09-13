"""Command-line interface for voice-to-clipboard."""

from __future__ import annotations

import argparse
import logging
import signal
import sys

from . import pipeline, recorder

logger = logging.getLogger("voice_to_clipboard")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="voice-to-clipboard",
        description=(
            "Local voice transcription to clipboard. "
            "Default (toggle): first press records, second press stops and transcribes. "
            "Models are auto-downloaded on first run."
        ),
    )
    parser.add_argument(
        "--transcribe",
        action="store_true",
        help="Foreground mode: record until Ctrl+C, then transcribe.",
    )
    parser.add_argument(
        "--no-punct",
        action="store_true",
        help="Disable automatic punctuation/casing. "
        "Punctuation is on by default; pass --no-punct to turn it off.",
    )
    parser.add_argument(
        "--llm-fix",
        action="store_true",
        help="Enable tiny-LLM homophone/grammar fix. "
        "Off by default; requires the 'llm' extra and is incompatible with --no-punct.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print the transcription to stdout instead of copying it to the clipboard.",
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="Disable desktop notifications for recording start/stop.",
    )
    parser.add_argument(
        "--lang",
        default=None,
        metavar="CODE",
        help="Force transcription language (default: auto-detect). E.g. 'en', 'fr'.",
    )
    parser.add_argument(
        "--prompt",
        default=None,
        metavar="TEXT",
        help="Initial prompt for vocabulary bias.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging.",
    )
    parser.add_argument(
        "--record-bg",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser


def _setup_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    logger.setLevel(level)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.debug)

    if args.llm_fix and args.no_punct:
        logger.error("--llm-fix is incompatible with --no-punct")
        return 2

    if args.record_bg:
        # Hidden background recorder: write audio, terminate on SIGTERM.
        path = recorder.record_until_signal(recorder.audio_path())
        logger.debug("Background recording finished -> %s", path)
        return 0

    if args.transcribe:
        path = recorder.record_until_signal(recorder.audio_path(), signals=(signal.SIGINT,))
        _process(path, args)
        return 0

    if recorder.is_recording():
        logger.info("Toggle stop requested")
        recorder.stop_background_recorder()
        _process(recorder.audio_path(), args)
        return 0

    logger.info("Toggle start requested")
    recorder.start_background_recorder()
    if not args.no_notify:
        pipeline.notify("Recording...")
    return 0


def _process(path, args) -> None:
    try:
        raw, final = pipeline.transcribe_file(
            path,
            lang=args.lang,
            prompt=args.prompt,
            no_punct=args.no_punct,
            llm_fix=args.llm_fix,
            stdout=args.stdout,
            no_notify=args.no_notify,
        )
    except Exception as exc:  # noqa: BLE001 - surface any pipeline error
        logger.error("Pipeline failed: %s", exc)
        if args.debug:
            logger.exception(exc)
        return

    if args.stdout:
        print(final)
        return

    if args.debug:
        print("\n=== RAW ===")
        print(raw)
        print("\n=== FINAL ===")
        print(final)
        print()


if __name__ == "__main__":
    sys.exit(main())