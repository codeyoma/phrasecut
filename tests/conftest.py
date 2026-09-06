import wave

import numpy as np
import pytest


@pytest.fixture
def tone_source(tmp_path):
    # Two independently identifiable signals, separated by a real one-second pause.
    sr = 16000
    a = np.zeros(6 * sr, dtype=np.int16)
    for start, end, freq in [(1, 2, 440), (3, 4.5, 880)]:
        t = np.arange(round((end - start) * sr)) / sr
        a[round(start * sr) : round(end * sr)] = (np.sin(2 * np.pi * freq * t) * 12000).astype(np.int16)
    path = tmp_path / "source with spaces.wav"
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes(a.tobytes())
    return path
