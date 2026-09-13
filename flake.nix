{
  description = "Voice to Clipboard: Voice transcription to clipboard";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = {
    self,
    nixpkgs,
    flake-utils,
  }: let
    overlay = final: prev: {
      voice-to-clipboard = final.python3.pkgs.buildPythonApplication {
        pname = "voice-to-clipboard";
        version = "0.2.0";
        src = self;
        format = "pyproject";

        nativeBuildInputs = with final.python3.pkgs; [
          hatchling
          pythonRelaxDepsHook
        ];

        # These come pinned on PyPI; relax so pip can resolve.
        pythonRelaxDeps = [
          "torch"
          "transformers"
        ];

        # sounddevice needs PortAudio at runtime; clipboard + notify on Linux.
        # macOS uses the system `pbcopy`/`osascript`, so no extra inputs there.
        buildInputs = [final.portaudio]
        ++ final.lib.optionals final.stdenv.isLinux [final.wl-clipboard final.dunst];

        meta = with final.lib; {
          description = "Local voice transcription to clipboard";
          license = licenses.mit;
          platforms = platforms.unix;
        };
      };
    };
  in
    flake-utils.lib.eachDefaultSystem (
      system: let
        pkgs = import nixpkgs {
          inherit system;
          overlays = [overlay];
        };
      in {
        packages.default = pkgs.voice-to-clipboard;
        apps.default = {
          type = "app";
          program = "${pkgs.voice-to-clipboard}/bin/voice-to-clipboard";
        };

        devShells.default = pkgs.mkShell {
          name = "voice-to-clipboard";
          packages = [
            pkgs.uv
            pkgs.python3
            pkgs.portaudio
          ] ++ pkgs.lib.optionals pkgs.stdenv.isLinux [
            pkgs.wl-clipboard
            pkgs.dunst
          ];
          shellHook = ''
            # Bootstrap a uv venv (contaibox pattern) if missing.
            if [[ ! -d .venv ]]; then
              uv venv
            fi
            source .venv/bin/activate
            uv pip install -e ".[dev]"
          '';
        };
      }
    )
    // {
      overlays.default = overlay;
    };
}