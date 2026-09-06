import itertools
import json

import numpy as np
import pytest

from phrasecut.jobs import create_job
from phrasecut.media import chunk_ranges, decode_to_wav, detect_silences, load_audio
from phrasecut.models import PhrasecutError


def test_resume_keeps_work_and_rejects_changed_inputs(tmp_path, tone_source):
    script = tmp_path / "script.txt"
    script.write_text("First.\nSecond.")
    out = tmp_path / "output"
    first = create_job(out, tone_source, script, {"language": "en"})
    (out / ".phrasecut" / "completed-chunk.json").write_text('{"finished":true}')
    resumed = create_job(out, tone_source, script, {"language": "en"}, resume=True)
    assert first["audio_sha256"] == resumed["audio_sha256"]
    assert json.loads((out / ".phrasecut/completed-chunk.json").read_text())["finished"]
    script.write_text("Changed.")
    with pytest.raises(PhrasecutError, match="changed"):
        create_job(out, tone_source, script, {"language": "en"}, resume=True)


def test_resume_rejects_changed_model_options(tmp_path, tone_source):
    script = tmp_path / "script.txt"
    script.write_text("Hello.")
    create_job(tmp_path / "out", tone_source, script, {"model": "small"})
    with pytest.raises(PhrasecutError, match="options"):
        create_job(tmp_path / "out", tone_source, script, {"model": "large"}, resume=True)


def test_unrelated_output_is_never_overwritten(tmp_path, tone_source):
    script = tmp_path / "script.txt"
    script.write_text("Hello.")
    out = tmp_path / "out"
    out.mkdir()
    (out / "important.txt").write_text("Keep me")
    with pytest.raises(PhrasecutError):
        create_job(out, tone_source, script, {})
    assert (out / "important.txt").read_text() == "Keep me"


def test_real_decode_and_silence_boundaries(tmp_path, tone_source):
    target = tmp_path / "decode.wav"
    info = decode_to_wav(tone_source, target)
    audio = load_audio(target)
    assert info["duration"] == pytest.approx(6)
    assert len(audio) == 96000
    gaps = detect_silences(audio)
    assert any(abs(s - 2) < 0.03 and abs(e - 3) < 0.03 for s, e in gaps)
    assert np.max(audio) > 0.3


def test_chunks_cover_audio_and_use_pauses():
    chunks = chunk_ranges(65, [(24, 26), (49, 51)])
    assert chunks[0][0] == 0 and chunks[-1][1] == 65
    assert chunks[0][1] == 25
    assert all(b - a <= 29 for a, b in chunks)
    assert all(next_start <= end for (_, end), (next_start, _) in itertools.pairwise(chunks))
