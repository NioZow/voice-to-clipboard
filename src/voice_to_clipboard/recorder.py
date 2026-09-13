"""Audio recording with sounddevice.

Two entry points:

* ``record_until_signal`` — block until ``SIGINT``/``SIGTERM`` then write a WAV
  (used by ``--transcribe`` foreground mode and the hidden background recorder).
* toggle helpers — ``start_background_recorder`` / ``stop_background_recorder``
  manage a detached recording process via a PID file.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
_CACHE_DIR_NAME = "voice-to-clipboard"


def cache_dir() -> Path:
    path = Path.home() / ".cache" / _CACHE_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def audio_path() -> Path:
    return cache_dir() / "voice_record.wav"


def pid_file_path() -> Path:
    return cache_dir() / "voice_record.pid"


def select_input_device() -> int:
    """Return an input device index, preferring the system default input."""
    try:
        default = sd.default.device
        if isinstance(default, (list, tuple)):
            default = default[0]
        if default is not None and _has_input_channels(default):
            return int(default)
    except Exception:
        pass

    for idx, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            return idx

    raise RuntimeError("No audio input device found")


def _has_input_channels(device_id: int) -> bool:
    try:
        return sd.query_devices(device_id)["max_input_channels"] > 0
    except Exception:
        return False


def _write_wav(path: Path, data: np.ndarray) -> None:
    data = np.asarray(data, dtype="int16")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(data.tobytes())


def _record(device: int, stop: threading.Event) -> np.ndarray:
    chunks: list[np.ndarray] = []

    def callback(indata, frames, time_info, status):
        chunks.append(indata.copy())

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        device=device,
        callback=callback,
    ):
        while not stop.is_set():
            time.sleep(0.1)

    if chunks:
        return np.concatenate(chunks, axis=0)
    return np.zeros((0, 1), dtype="int16")


def record_until_signal(
    out_path: Path,
    signals: tuple = (signal.SIGINT, signal.SIGTERM),
) -> Path:
    """Record audio until one of ``signals`` fires, then write ``out_path``."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.unlink(missing_ok=True)

    stop = threading.Event()

    def handler(signum, frame):
        stop.set()

    previous = {}
    for sig in signals:
        previous[sig] = signal.signal(sig, handler)

    try:
        device = select_input_device()
        data = _record(device, stop)
    finally:
        for sig, old in previous.items():
            signal.signal(sig, old)

    _write_wav(out_path, data)
    return out_path


def start_background_recorder() -> int:
    """Launch a detached recorder and record its PID."""
    audio_path().unlink(missing_ok=True)
    proc = subprocess.Popen(
        [os.path.abspath(sys.argv[0]), "--record-bg"],
        start_new_session=True,
    )
    pid_file_path().write_text(str(proc.pid))
    return proc.pid


def stop_background_recorder(timeout: float = 5.0) -> int | None:
    """Signal the background recorder to finish and return its PID.

    Waits (up to ``timeout`` seconds) for the recorder to flush the WAV file
    before returning, so the pipeline never races the writer.
    """
    pid_file = pid_file_path()
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text().strip())
    except ValueError:
        pid_file.unlink(missing_ok=True)
        return None
    pid_file.unlink(missing_ok=True)
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return pid
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            break
        time.sleep(0.05)
    return pid


def is_recording() -> bool:
    pid_file = pid_file_path()
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text().strip())
    except ValueError:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True