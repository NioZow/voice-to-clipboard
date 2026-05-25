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
      voice-to-clipboard = final.callPackage (
        {
          stdenv,
          lib,
          makeWrapper,
          sox,
          whisper-cpp,
          ollama,
          python3,
          wl-clipboard,
          dunst,
        }:
          stdenv.mkDerivation (finalAttrs: {
            pname = "voice-to-clipboard";
            version = "0.1.0";
            src = ./.;

            nativeBuildInputs = [makeWrapper];

            buildInputs =
              [sox whisper-cpp ollama python3]
              ++ lib.optional stdenv.isLinux wl-clipboard
              ++ lib.optional stdenv.isLinux dunst;

            installPhase = ''
              mkdir -p $out/bin $out/share/voice-to-clipboard

              cp scripts/normalize.py $out/share/voice-to-clipboard/normalize.py
              cp scripts/record.sh $out/bin/voice-to-clipboard
              chmod +x $out/bin/voice-to-clipboard

              substituteInPlace $out/bin/voice-to-clipboard \
                --replace-fail 'local normalizer="$script_dir/normalize.py"' \
                "local normalizer=\"$out/share/voice-to-clipboard/normalize.py\""

              wrapProgram $out/bin/voice-to-clipboard \
                --prefix PATH : ${lib.makeBinPath finalAttrs.buildInputs}
            '';

            meta = with lib; {
              description = "Local voice transcription to clipboard";
              license = licenses.mit;
              platforms = platforms.unix;
            };
          })
      ) {};
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
      }
    )
    // {
      overlays.default = overlay;
    };
}
