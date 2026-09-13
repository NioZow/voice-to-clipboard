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
    overlay = final: prev: let
      python = final.python3;

      # `deepmultilingualpunctuation` is not packaged in nixpkgs, so vendor it
      # from its pure-Python PyPI wheel (buildPythonPackage pattern from
      # chutes-litellm-proxy).  It only declares `torch` and `transformers`, both
      # of which ship as prebuilt binaries in the nixpkgs cache.
      deepmultilingualpunctuation = python.pkgs.buildPythonPackage {
        pname = "deepmultilingualpunctuation";
        version = "1.0.1";
        format = "wheel";
        src = final.fetchurl {
          url = "https://files.pythonhosted.org/packages/dc/a7/505f531c23aa2c381b597c9e59a62c20d9e6294f32ad7d06e4eaa2f3d438/deepmultilingualpunctuation-1.0.1-py3-none-any.whl";
          hash = "sha256-80Y3itvs3O+ExjphRn91XXU4VVnQJg9gvvQxW1+zpU8=";
        };
        propagatedBuildInputs = with python.pkgs; [
          torch
          transformers
        ];
        # Prebuilt wheel: no build/compile step.
        dontBuild = true;
        doCheck = false;
      };
    in {
      inherit deepmultilingualpunctuation;

      voice-to-clipboard = python.pkgs.buildPythonApplication {
        pname = "voice-to-clipboard";
        version = "0.2.0";
        src = self;
        format = "pyproject";

        nativeBuildInputs = with python.pkgs; [
          hatchling
          pythonRelaxDepsHook
        ];

        # These come pinned on PyPI; relax so pip/nix can resolve.
        pythonRelaxDeps = [
          "torch"
          "transformers"
        ];

        # All runtime dependencies from pyproject.toml, plus the vendored
        # deepmultilingualpunctuation.  Without these the wheel's METADATA lists
        # them as missing and pythonRuntimeDepsCheckHook fails the build.
        propagatedBuildInputs = with python.pkgs; [
          faster-whisper
          deepmultilingualpunctuation
          sounddevice
          numpy
          huggingface-hub
          transformers
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