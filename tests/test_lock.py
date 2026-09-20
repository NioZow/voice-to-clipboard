import os
import signal

import pytest

from voice_to_clipboard import cli, recorder


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder, "cache_dir", lambda: tmp_path)
    return tmp_path


def test_lock_is_exclusive_across_opens():
    first = recorder.acquire_recording_lock()
    assert first is not None
    try:
        assert recorder.acquire_recording_lock() is None
    finally:
        recorder.release_recording_lock(first)

    second = recorder.acquire_recording_lock()
    assert second is not None
    recorder.release_recording_lock(second)


def test_is_recording_tracks_the_lease():
    assert recorder.is_recording() is False

    handle = recorder.acquire_recording_lock()
    assert handle is not None
    try:
        assert recorder.is_recording() is True
    finally:
        recorder.release_recording_lock(handle)

    assert recorder.is_recording() is False


class _FakeProc:
    """Stand-in for Popen that emulates fd inheritance via os.dup."""

    def __init__(self, *args, **kwargs):
        self.pid = 4242
        self._held = []
        for fd in kwargs.get("pass_fds", ()):
            self._held.append(os.dup(fd))

    def close(self):
        for fd in self._held:
            os.close(fd)
        self._held.clear()


def test_start_hands_off_lock_and_blocks_duplicate(monkeypatch):
    holder = {}

    def fake_popen(*args, **kwargs):
        proc = _FakeProc(*args, **kwargs)
        holder["proc"] = proc
        return proc

    monkeypatch.setattr(recorder.subprocess, "Popen", fake_popen)

    pid = recorder.start_background_recorder()
    assert pid == 4242

    # The child (fake proc) now owns the lease, so a duplicate start is refused.
    assert recorder.is_recording() is True
    with pytest.raises(recorder.AlreadyRecordingError):
        recorder.start_background_recorder()

    # Once the child exits the lease is released and a new start succeeds.
    holder["proc"].close()
    assert recorder.is_recording() is False
    assert recorder.start_background_recorder() == 4242
    holder["proc"].close()


def test_stop_reads_state_and_signals(monkeypatch):
    calls = []

    def fake_kill(pid, sig):
        calls.append((pid, sig))
        if sig == 0:
            raise ProcessLookupError

    monkeypatch.setattr(os, "kill", fake_kill)
    owner = recorder.acquire_recording_lock()
    assert owner is not None
    recorder.lock_file_path().write_text("1234 deadbeef\n")
    try:
        assert recorder.stop_background_recorder(timeout=0.2) == 1234
    finally:
        recorder.release_recording_lock(owner)
    assert (1234, signal.SIGTERM) in calls


def test_stop_is_noop_while_still_starting():
    # A live lease with no published pid yet (start-up window).
    owner = recorder.acquire_recording_lock()
    assert owner is not None
    try:
        assert recorder.stop_background_recorder(timeout=0.1) is None
    finally:
        recorder.release_recording_lock(owner)


def test_stop_is_noop_without_a_lease():
    recorder.lock_file_path().write_text("1234 deadbeef\n")
    assert recorder.stop_background_recorder(timeout=0.1) is None


def test_foreground_refuses_when_lease_is_held(monkeypatch):
    monkeypatch.setattr(
        recorder, "acquire_recording_lock", lambda timeout=0.0: None
    )
    assert cli.main(["--transcribe"]) == 2


def test_toggle_duplicate_start_is_noop(monkeypatch):
    def boom():
        raise recorder.AlreadyRecordingError("busy")

    monkeypatch.setattr(recorder, "start_background_recorder", boom)
    assert cli.main([]) == 0
