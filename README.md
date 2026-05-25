# Voice To Clipboard

A local, high-performance voice transcription tool that captures audio, transcribes it via Whisper, normalizes it using a local LLM, and copies the result to the system clipboard.

## Features

- **Local STT**: Uses `whisper-cpp` for near-instant transcription.
- **Technical Normalization**: Uses `Ollama` (Llama 3.2) to fix software engineering homophones.
- **Least Privilege**: Runs entirely on the host; no container access required.
- **Cross-Platform**: Native support for NixOS (Wayland/Dunst) and macOS.

## Prerequisites

1. **Whisper Model**: Download the turbo model to `~/.local/share/whisper-cpp/`:

```sh
mkdir -p ~/.local/share/whisper-cpp
curl -L -o ~/.local/share/whisper-cpp/ggml-large-v3-turbo-q5_0.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin
```

2. **Ollama**: Ensure Ollama is running with `llama3.2:1b` pulled:

```sh
ollama pull llama3.2:1b
```

## Installation

### Nix Flake (recommended)

Add this repo as a flake input:

```nix
{
  inputs.voice-to-clipboard.url = "github:niozow/voice-to-clipboard";

  # Example: home-manager
  outputs = { self, nixpkgs, home-manager, voice-to-clipboard, ... }:
    let
      system = "x86_64-linux"; # or aarch64-linux, aarch64-darwin, x86_64-darwin
      pkgs = import nixpkgs {
        inherit system;
        overlays = [ voice-to-clipboard.overlays.default ];
      };
    in {
      homeConfigurations.user = home-manager.lib.homeManagerConfiguration {
        inherit pkgs;
        modules = [{
          home.packages = [ pkgs.voice-to-clipboard ];
        }];
      };
    };
}
```

After rebuilding, `voice-to-clipboard` is available in your `PATH`.

### Manual

Clone the repo and run `scripts/record.sh` directly. Ensure `sox`, `whisper-cli`, `ollama`, and `python3` are in your `PATH` (plus `wl-copy` on Linux or `pbcopy` on macOS).

## Usage

Bind `voice-to-clipboard` to a key in your window manager or desktop environment. The script works as a **toggle**:

- **First press**: starts recording.
- **Second press**: stops recording, transcribes, normalizes, and copies the result to the clipboard.

You can also run it in attached/foreground mode:

```sh
voice-to-clipboard --attached   # press Ctrl+C to stop and transcribe
```

**Flow:**
`Keybind` → `sox Record` → `Whisper Transcribe` → `Ollama Normalize` → `Clipboard` → `Notification`.

Simply press `Ctrl+V` (or `Cmd+V`) to paste your transcribed text.
