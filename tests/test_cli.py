from voice_to_clipboard import cli


def test_parser_defaults():
    args = cli.build_parser().parse_args([])
    assert args.transcribe is False
    assert args.no_punct is False
    assert args.llm_fix is False
    assert args.lang is None
    assert args.prompt is None
    assert args.debug is False
    assert args.stdout is False
    assert args.no_notify is False


def test_parser_options():
    args = cli.build_parser().parse_args(
        ["--transcribe", "--no-punct", "--lang", "fr", "--prompt", "hello", "--debug"]
    )
    assert args.transcribe is True
    assert args.no_punct is True
    assert args.lang == "fr"
    assert args.prompt == "hello"
    assert args.debug is True


def test_parser_stdout():
    assert cli.build_parser().parse_args([]).stdout is False
    assert cli.build_parser().parse_args(["--stdout"]).stdout is True


def test_parser_no_notify():
    assert cli.build_parser().parse_args([]).no_notify is False
    assert cli.build_parser().parse_args(["--no-notify"]).no_notify is True


def test_platform_notify_command_destructured():
    from voice_to_clipboard import pipeline

    notify_bin, template = pipeline._platform_commands()[1]
    assert notify_bin in ("osascript", "notify-send")
    assert isinstance(template, list)
    assert len(template) == 2


def test_stt_resolve_repo():
    from voice_to_clipboard import stt

    assert stt._resolve_repo("large-v3-turbo") == "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
    assert stt._resolve_repo("mobiuslabsgmbh/faster-whisper-large-v3-turbo") == "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
