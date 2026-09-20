"""Audio recording with sounddevice.

Two entry points:

* ``record_until_signal`` — block until ``SIGINT``/``SIGTERM`` then write a WAV
  (used by ``--transcribe`` foreground mode and the hidden background recorder).
* toggle helpers — ``start_background_recorder`` / ``stop_background_recorder``
  manage a detached recording process via a PID file.

Single-instance guarantee
-------------------------

A POSIX ``flock`` (``LOCK_EX``) on ``voice_record.lock`` is the source of truth
for "is a recorder running".  The lock is held by whichever process is recording:

* Toggle start acquires the lock, spawns the detached ``--record-bg`` child with
  the lock fd passed through ``pass_fds``, writes ``pid <token>`` and closes its
  own fd.  The child keeps the inherited open file description, so it owns the
  lease until it exits (including on ``SIGKILL``, where the fd is closed by the
  kernel).  There is no stale-lock problem and no PID-reuse false positive.
* Foreground ``--transcribe`` acquires the same lock for the duration of the
  recording.
* A second start while the lock is held is a no-op (``AlreadyRecordingError``),
  which removes the start-up race between concurrent hotkey invocations.
"""

from __future__ import annotations

import fcntl
import os
import secrets
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


def lock_file_path() -> Path:
    """Path of the combined lock + state file.

    It is both the ``flock`` target (single-instance guarantee) and the place
    where the recorder's ``pid <token>`` is stored so the toggling caller can
    signal the detached recorder to stop.
    """
    return cache_dir() / "voice_record.lock"


def pid_file_path() -> Path:
    """Backward-compatible alias for :func:`lock_file_path`."""
    return lock_file_path()


class AlreadyRecordingError(RuntimeError):
    """Raised when a start is attempted while a recorder already holds the lock."""


def acquire_recording_lock(timeout: float = 0.0):
    """Try to take the exclusive recorder lease.

    Returns an open file object on success (the caller owns the lease until it
    closes the fd) or ``None`` if another process already holds it.  If
    ``timeout`` is positive, retry for up to that many seconds before giving up.
    """
    path = lock_file_path()
    deadline = time.monotonic() + timeout
    while True:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        handle = os.fdopen(fd, "r+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except OSError:
            handle.close()
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.05)


def release_recording_lock(handle) -> None:
    """Release a lease we acquired ourselves (never use on a handed-off fd)."""
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    handle.close()


def clear_recording_state(handle) -> None:
    """Remove any published ``pid <token>`` from the lock file.

    Used by the foreground recorder, which owns the lease but is stopped with
    ``Ctrl+C`` rather than by a pid signal.  Clearing prevents a concurrent
    toggle from reading a stale pid left by an earlier background recording.
    """
    handle.seek(0)
    handle.truncate(0)
    handle.flush()
    os.fsync(handle.fileno())


def _read_state() -> tuple[int, str] | None:
    """Read ``(pid, token)`` from the lock file, or ``None`` if absent/invalid."""
    try:
        text = lock_file_path().read_text().strip()
    except OSError:
        return None
    parts = text.split()
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), parts[1]
    except ValueError:
        return None


def _wait_for_state(timeout: float) -> tuple[int, str] | None:
    """Wait briefly for a starting recorder to publish its pid/token."""
    deadline = time.monotonic() + timeout
    while True:
        state = _read_state()
        if state is not None:
            return state
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.02)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


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
    """Launch a detached recorder, holding the single-instance lease.

    The lock fd is handed to the child via ``pass_fds``; the child keeps the
    inherited open file description open for its whole lifetime, so the lease
    (and therefore "recording") stays held after this process closes its own
    copy.

    Raises :class:`AlreadyRecordingError` if another recorder already holds the
    lease, making a duplicate start a no-op.
    """
    lock = acquire_recording_lock()
    if lock is None:
        raise AlreadyRecordingError("a recorder is already running")

    audio_path().unlink(missing_ok=True)
    proc = None
    try:
        proc = subprocess.Popen(
            [os.path.abspath(sys.argv[0]), "--record-bg"],
            start_new_session=True,
            pass_fds=(lock.fileno(),),
        )
        token = secrets.token_hex(16)
        lock.seek(0)
        lock.truncate(0)
        lock.write(f"{proc.pid} {token}\n")
        lock.flush()
        os.fsync(lock.fileno())
    except Exception:
        # The child shares this open file description, so an explicit LOCK_UN
        # here would release the child's lease too.  Reap the child first, then
        # the LOCK_UN only affects our now-sole descriptor.
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                pass
        release_recording_lock(lock)
        raise

    # The child now owns the shared lease; closing our fd must NOT unlock it
    # (an explicit LOCK_UN would, hence plain close()).
    lock.close()
    return proc.pid


def stop_background_recorder(timeout: float = 5.0) -> int | None:
    """Signal the background recorder to finish and return its PID.

    Waits (up to ``timeout`` seconds) for the recorder to flush the WAV file
    before returning, so the pipeline never races the writer.  Waits briefly for
    a just-started recorder to publish its pid before giving up (returns ``None``
    only if the start has not reached the pid-publish step, i.e. it is still in
    its start-up window).
    """
    if not is_recording():
        return None
    state = _wait_for_state(timeout=min(timeout, 1.0))
    if state is None:
        return None
    pid, _token = state
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return pid
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            break
        time.sleep(0.05)
    return pid


def is_recording() -> bool:
    """Return whether a recorder currently holds the single-instance lease."""
    lock = acquire_recording_lock()
    if lock is None:
        return True
    release_recording_lock(lock)
    return False
