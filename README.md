# Voice To Clipboard

A self-contained, local voice-to-clipboard tool. Press a hotkey, speak, press the
hotkey again — the transcribed, punctuated text lands on your clipboard. No server,
no cloud, no Ollama. Models are auto-downloaded on first run; there is nothing to do.

## Features

- **Local STT**: `faster-whisper` (`large-v3-turbo`), auto-downloaded to
  `~/.cache/huggingface` on first run.
- **Punctuation & casing**: `deepmultilingualpunctuation` (EN + FR), **on by default**.
- **Optional tiny LLM fix** (`--llm-fix`): an in-process `Qwen2.5-0.5B-Instruct`
  GGUF lightly fixes homophones/grammar. Requires the `llm` extra.
- **Cross-platform**: `wl-copy`/`notify-send` on Linux, `pbcopy`/`osascript` on macOS.
- **Toggle or foreground**: bind to a hotkey for start/stop, or run in the
  foreground and press `Ctrl+C`.

## Installation

### uv (recommended for development)

```sh
uv venv
uv pip install -e ".[dev]"        # core
uv pip install -e ".[llm]"        # optional --llm-fix support
```

### Nix flake

```sh
nix build                       # build the package
nix develop                     # dev shell (uv venv bootstrap)
```

You can also consume it as a flake input via `overlays.default` and add
`pkgs.voice-to-clipboard` to your `home.packages`.

## Usage

### Toggle (hotkey-friendly)

Bind `voice-to-clipboard` to a key in your window manager or desktop environment:

- **First press**: starts recording.
- **Second press**: stops recording, transcribes, punctuates, and copies the result
  to the clipboard.

### Foreground mode

```sh
voice-to-clipboard --transcribe   # record until Ctrl+C, then process
```

### Options

```text
voice-to-clipboard [options]

  --transcribe      Foreground mode: record until Ctrl+C, then transcribe
  --no-punct        Disable automatic punctuation/casing (off by default)
  --llm-fix         Enable tiny-LLM homophone/grammar fix (off by default)
  --stdout          Print the transcription to stdout instead of the clipboard
  --lang CODE       Force transcription language (default: auto), e.g. en, fr
  --prompt TEXT     Initial prompt for vocabulary bias
  --debug           Verbose logging and raw/final output
  --help            Show this message
```

**Defaults:** Punctuation & casing are **on by default**; pass `--no-punct` to disable
them. `--llm-fix` is **off by default**; pass it to enable (it requires the `llm` extra
and is incompatible with `--no-punct`). By default the result is copied to the clipboard
and a desktop notification is shown; pass `--stdout` to print the text to stdout instead
(no clipboard copy, no notification).

**Flow:** `Hotkey` → `Record` → `faster-whisper` → `Punctuation` → (`LLM fix`?) →
(`Clipboard` + `Notification`) or `stdout`.

Simply press `Ctrl+V` (or `Cmd+V`) to paste your transcribed text.

## Environment variables

- `VOICE_STT_MODEL` — override the Whisper model (default `large-v3-turbo`), e.g.
  `small` for low-resource machines. Models are auto-downloaded on first use.