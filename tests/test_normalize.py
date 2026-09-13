import numpy as np
import pytest

from voice_to_clipboard import normalize, recorder


def test_punctuate_empty():
    assert normalize.punctuate("") == ""
    assert normalize.punctuate("   ") == "   "


def test_llm_fix_empty():
    assert normalize.llm_fix("") == ""


def test_llm_model_path_exports():
    assert normalize.LLM_REPO == "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
    assert normalize.LLM_FILENAME == "qwen2.5-0.5b-instruct-q4_k_m.gguf"


def test_record_empty(monkeypatch):
    """_record stops immediately and returns an empty int16 array."""
    class FakeInputStream:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(recorder.sd, "InputStream", FakeInputStream)

    stop = type("Evt", (), {"is_set": lambda self: True})()
    data = recorder._record(0, stop)
    assert isinstance(data, np.ndarray)
    assert data.dtype == np.int16
    assert data.shape == (0, 1)


def test_write_wav(tmp_path):
    out = tmp_path / "out.wav"
    data = np.array([[1], [2], [3]], dtype="int16")
    recorder._write_wav(out, data)
    assert out.exists()
    assert out.stat().st_size > 44


def test_select_input_device_prefers_default(monkeypatch):
    devices = {0: {"max_input_channels": 0}, 3: {"max_input_channels": 2}}
    monkeypatch.setattr(recorder.sd, "default", type("D", (), {"device": (3, 4)})())

    def fake_query(device_id=None):
        if device_id is None:
            return list(devices.values())
        return devices[device_id]

    monkeypatch.setattr(recorder.sd, "query_devices", fake_query)
    assert recorder.select_input_device() == 3