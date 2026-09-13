from voice_to_clipboard import cli


def test_parser_defaults():
    args = cli.build_parser().parse_args([])
    assert args.transcribe is False
    assert args.no_punct is False
    assert args.llm_fix is False
    assert args.lang is None
    assert args.prompt is None
    assert args.debug is False


def test_parser_options():
    args = cli.build_parser().parse_args(
        ["--transcribe", "--no-punct", "--lang", "fr", "--prompt", "hello", "--debug"]
    )
    assert args.transcribe is True
    assert args.no_punct is True
    assert args.lang == "fr"
    assert args.prompt == "hello"
    assert args.debug is True