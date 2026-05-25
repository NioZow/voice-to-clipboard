#!/usr/bin/env bash
set -uo pipefail

# ─── Defaults ───────────────────────────────────────────────────────
DEBUG=false
WHISPER_LANG="auto"

# Force UTF-8 locale for clipboard and text handling
export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8

# ─── Colors ─────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ─── Logging helpers ────────────────────────────────────────────────
log_info() { echo -e "${BLUE}[*]${NC} $1" >&2; }
log_ok() { echo -e "${GREEN}[+]${NC} $1" >&2; }
log_warn() { echo -e "${YELLOW}[-]${NC} $1" >&2; }
log_err() { echo -e "${RED}[!]${NC} $1" >&2; }
log_debug() { [[ "$DEBUG" == true ]] && echo -e "${CYAN}[D]${NC} $1" >&2; }

# ─── Configuration ──────────────────────────────────────────────────
MODEL_PATH="$HOME/.local/share/whisper-cpp/ggml-large-v3-turbo-q5_0.bin"
TEMP_DIR="$HOME/.cache/voice-to-clipboard"
TEMP_AUDIO="$TEMP_DIR/voice_record.wav"
WHISPER_BIN="whisper-cli"
PID_FILE="$TEMP_DIR/voice_record.pid"

log_debug "TEMP_AUDIO=$TEMP_AUDIO"
log_debug "PID_FILE=$PID_FILE"

# ─── Sanity checks ──────────────────────────────────────────────────
if ! command -v sox >/dev/null 2>&1; then
  log_err "sox not found in PATH"
  exit 1
fi
log_ok "sox found"

if ! command -v python3 >/dev/null 2>&1; then
  log_err "python3 not found in PATH"
  exit 1
fi
log_ok "python3 found"

if ! command -v "$WHISPER_BIN" >/dev/null 2>&1; then
  log_err "$WHISPER_BIN not found in PATH"
  exit 1
fi
log_ok "$WHISPER_BIN found"

if [[ ! -f "$MODEL_PATH" ]]; then
  log_err "Whisper model not found: $MODEL_PATH"
  exit 1
fi
log_ok "Model found: $MODEL_PATH"

# ─── Ensure secure temp directory exists ────────────────────────────
mkdir -p "$TEMP_DIR"
chmod 700 "$TEMP_DIR"
umask 0077

# ─── Platform detection ─────────────────────────────────────────────
if [[ "$OSTYPE" == "darwin"* ]]; then
  CLIP_CMD="pbcopy"
  NOTIFY_CMD=("osascript" "-e" "display notification \"Recording...\" with title \"Voice STT\"")
  NOTIFY_END=("osascript" "-e" "display notification \"Transcribed!\" with title \"Voice STT\"")
else
  CLIP_CMD="wl-copy"
  NOTIFY_CMD=("dunstify" "Voice STT" "🔴 Recording...")
  NOTIFY_END=("dunstify" "Voice STT" "✅ Transcribed!")
fi

# ─── Audio recording helper ─────────────────────────────────────────
start_recording() {
  log_info "Starting audio recording…"
  rm -f "$TEMP_AUDIO"
  sox -d -r 16000 -c 1 -b 16 "$TEMP_AUDIO" >/dev/null 2>&1 &
  local pid=$!
  echo "$pid" >"$PID_FILE"
  log_ok "Recording started (PID $pid) → $TEMP_AUDIO"
}

stop_recording() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid=$(cat "$PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
      log_info "Stopping recorder (PID $pid)…"
      kill -TERM "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      log_ok "Recorder stopped"
    else
      log_warn "PID $pid is not running"
    fi
    rm -f "$PID_FILE"
  else
    log_warn "No PID file found; nothing to stop"
  fi
}

# ─── Transcription & normalization ──────────────────────────────────
process_audio() {
  log_info "Beginning transcription pipeline…"

  if [[ ! -f "$TEMP_AUDIO" ]]; then
    log_err "Audio file missing: $TEMP_AUDIO"
    return 1
  fi

  local size
  size=$(stat -f%z "$TEMP_AUDIO" 2>/dev/null || stat -c%s "$TEMP_AUDIO" 2>/dev/null || echo "?")
  log_info "Audio file size: ${size} bytes"

  if [[ "$size" == "0" || "$size" == "?" ]]; then
    log_err "Audio file is empty or unreadable"
    return 1
  fi

  # 1. Transcribe with Whisper
  log_info "Running whisper-cli (lang=$WHISPER_LANG)…"
  local raw_text
  if [[ "$WHISPER_LANG" == "auto" ]]; then
    raw_text=$("$WHISPER_BIN" -m "$MODEL_PATH" -f "$TEMP_AUDIO" -l auto -nt 2>&1)
  else
    raw_text=$("$WHISPER_BIN" -m "$MODEL_PATH" -f "$TEMP_AUDIO" -l "$WHISPER_LANG" -nt 2>&1)
  fi
  local whisper_exit=$?

  log_debug "whisper-cli exit code: $whisper_exit"

  if [[ $whisper_exit -ne 0 ]]; then
    log_err "whisper-cli failed (exit $whisper_exit)"
    log_err "Output: $raw_text"
    return 1
  fi

  # Strip whisper debug lines
  raw_text=$(echo "$raw_text" | sed '/^whisper_/d;/^ggml_/d;/^system_info:/d;/^main:/d')
  raw_text=$(echo "$raw_text" | sed '/^$/d')

  if [[ -z "${raw_text// /}" ]]; then
    log_warn "Whisper produced empty transcription"
    raw_text=""
  else
    log_ok "Whisper raw text:"
    echo "    $raw_text"
  fi

  # 2. Normalize via Python helper
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local normalizer="$script_dir/normalize.py"

  log_info "Running normalizer ($normalizer)…"
  local final_text
  final_text=$(echo "$raw_text" | python3 "$normalizer" "-" 2>&1)
  local norm_exit=$?

  log_debug "normalizer exit code: $norm_exit"

  if [[ $norm_exit -ne 0 ]]; then
    log_warn "Normalizer failed (exit $norm_exit); using raw text"
    log_warn "Normalizer error: $final_text"
    final_text="$raw_text"
  fi

  if [[ -z "${final_text// /}" ]]; then
    log_warn "Final text is empty; nothing to copy"
    final_text=""
  else
    log_ok "Normalized text:"
    echo "    $final_text"
  fi

  # 3. Debug output
  if [[ "$DEBUG" == true ]]; then
    echo
    echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║           DEBUG  OUTPUT              ║${NC}"
    echo -e "${CYAN}╠══════════════════════════════════════╣${NC}"
    echo -e "${GREEN}RAW WHISPER:${NC}"
    echo "$raw_text"
    echo
    echo -e "${GREEN}LLM NORMALIZED:${NC}"
    echo "$final_text"
    echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
    echo
  fi

  # 4. Copy to clipboard
  if [[ -n "$final_text" ]]; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
      # Fix pbcopy UTF-8 encoding on macOS
      __CF_USER_TEXT_ENCODING=0x1F5:0x8000100:0x8000100 printf '%s' "$final_text" | pbcopy
    else
      printf '%s\n' "$final_text" | $CLIP_CMD
    fi
    log_ok "Copied to clipboard"
  fi

  # 5. Notify end
  "${NOTIFY_END[@]}"
  log_ok "Done."
}

# ─── Help ───────────────────────────────────────────────────────────
show_help() {
  cat <<EOF
Usage: $(basename "$0") [options]

Options:
  -h, --help     Show this help message
  --attached     Run in foreground mode. Recording stops on Ctrl+C
  --debug        Print raw and normalized text to stdout
  --lang CODE    Language code for transcription (default: auto)
                 Use 'auto' for auto-detection, or e.g. 'fr', 'en', 'de'
EOF
}

# ─── Parse arguments ────────────────────────────────────────────────
ATTACHED=false
while [[ "$#" -gt 0 ]]; do
  case "$1" in
  -h | --help)
    show_help
    exit 0
    ;;
  --attached) ATTACHED=true ;;
  --debug) DEBUG=true ;;
  --lang)
    if [[ -n "${2:-}" && ! "$2" =~ ^- ]]; then
      WHISPER_LANG="$2"
      shift
    else
      log_err "--lang requires a language code (e.g., fr, en, auto)"
      exit 1
    fi
    ;;
  *)
    log_err "Unknown option: $1"
    show_help
    exit 1
    ;;
  esac
  shift
done

# ─── Attached mode ──────────────────────────────────────────────────
if [[ "$ATTACHED" == true ]]; then
  log_info "Attached mode — press Ctrl+C to stop recording"
  "${NOTIFY_CMD[@]}"

  # Trap SIGINT to gracefully stop and transcribe
  trap 'echo; log_info "SIGINT caught"; stop_recording; process_audio; exit 0' SIGINT

  start_recording

  # Wait for the recorder process
  rec_pid=$(cat "$PID_FILE")
  if [[ -n "$rec_pid" ]]; then
    wait "$rec_pid" 2>/dev/null || true
  fi

  # If sox exits on its own (unlikely), still process
  log_info "Recorder exited; running transcription…"
  process_audio
  exit 0
fi

# ─── Toggle logic (background mode) ─────────────────────────────────
if [[ -f "$PID_FILE" ]]; then
  log_info "Toggle stop requested"
  stop_recording
  process_audio
  exit 0
fi

# ─── Start recording (background mode) ──────────────────────────────
log_info "Toggle start requested"
"${NOTIFY_CMD[@]}"
start_recording
log_ok "Recording in background (PID $(cat "$PID_FILE"))"
