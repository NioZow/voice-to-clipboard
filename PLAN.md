# Plan: Adapt `voice-to-clipboard` to a self-contained local STT tool

**Confirmed choices:** `faster-whisper` (auto-download) · `deepmultilingualpunctuation`
(punctuation, ON by default) · `llama-cpp-python` in-process (optional `--llm-fix`, OFF) ·
`sounddevice` recording · `uv` + `pyproject` + `flake.nix` (contaibox pattern) · remove Ollama.

## Goal

Remove Ollama; auto-download models on first run; "just run, nothing to do"; Python-native
pipeline; support EN+FR; toggle + transcribe-until-Ctrl+C modes; all features
argparse-toggleable.

## 1. Restructure into a Python package

```
voice-to-clipboard/
├── pyproject.toml
├── flake.nix               # rebuilt on the contaibox pattern
├── README.md               # rewritten (no ollama, no manual downloads)
├── src/voice_to_clipboard/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py              # argparse
│   ├── recorder.py         # sounddevice toggle/foreground + PID file
│   ├── stt.py              # faster-whisper tuned decoding
│   ├── normalize.py        # punctuation (+ optional tiny LLM)
│   └── pipeline.py         # record→STT→normalize→clipboard→notify
└── tests/
```

`console_scripts`: `voice-to-clipboard`. Delete `scripts/record.sh` and `scripts/normalize.py`.

## 2. CLI (argparse)

- `voice-to-clipboard` — toggle (default): record start/stop via PID file
- `--transcribe` — foreground, record until Ctrl+C then process
- `--no-punct` — disable punctuation (default ON)
- `--llm-fix` — enable tiny-LLM homophone/grammar fix (default OFF)
- `--lang CODE` (default auto), `--prompt "…"` (vocab bias), `--debug`, `--help`

## 3. STT (`stt.py`)

`WhisperModel("large-v3-turbo")` with `beam_size=5`, `condition_on_previous_text=True`,
`vad_filter=True`, optional `initial_prompt` + forced language. Auto-downloads on first run
to `~/.cache/huggingface`.

## 4. Normalization (`normalize.py`) — replaces Ollama

- `PunctuationModel("oliverguhr/fullstop-punctuation-multilingual-sonar-base")` → EN+FR
  punctuation/casing (default).
- Optional `--llm-fix`: `llama-cpp-python` loads a small GGUF (Qwen2.5-0.5B-Instruct)
  **in-process**, prompted to lightly fix transcription/homophones, preserving
  language/meaning. Incompatible with `--no-punct`.

## 5. Recording (`recorder.py`)

`sounddevice` → temp WAV + PID file for toggle; blocks on Ctrl+C in foreground.
Auto-select input device.

## 6. Packaging

**`pyproject.toml`**

```toml
[project]
dependencies = ["faster-whisper", "deepmultilingualpunctuation", "sounddevice", "numpy", "huggingface-hub"]
[project.optional-dependencies]
llm = ["llama-cpp-python"]
```

**`flake.nix`** — port contaibox pattern: `buildPythonApplication`, `format="pyproject"`,
`pythonRelaxDepsHook` (for torch/transformers pins), add `portaudio` (sounddevice),
`wl-clipboard`/`dunst` (Linux), `pbcopy`/`osascript` (macOS).

## 7. Verification

- `uv venv && uv pip install -e ".[dev]"`, run CLI with `--help`, `--no-punct`, `--debug`
  on a test clip; `--llm-fix` in the `[llm]` extra.
- `nix build` / `nix develop` in devShell (uv venv bootstrap, per example).

## Risks

- `deepmultilingualpunctuation` pulls `torch`+`transformers` (heavy) → may need a nix
  overlay if attrs are missing from nixpkgs.
- `faster-whisper`/`deepmultilingualpunctuation` may not be nixpkgs attrs → build from pypi
  in the flake.
- `sounddevice` needs PortAudio at runtime on Linux → `portaudio` in buildInputs.