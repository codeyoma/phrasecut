import numpy as np
import pytest

from phrasecut.models import PhrasecutError
from phrasecut.recognition import read_words, transcribe_chunks


def test_import_rejects_missing_or_invalid_word_timestamps():
    with pytest.raises(PhrasecutError):
        read_words({"segments": [{"text": "Hello."}]}, 5)
    for bad in [float("nan"), -1, 6]:
        with pytest.raises(PhrasecutError):
            read_words({"words": [{"word": "Hello", "start": bad, "end": 7}]}, 5)


def test_import_accepts_whisper_word_timestamps():
    words = read_words({"segments": [{"words": [{"word": " 今日は", "start": 1, "end": 2}]}]}, 5)
    assert words[0].text == " 今日は"
    assert words[0].start == 1


def test_interrupted_transcription_resumes_completed_chunks(tmp_path):
    attempts = 0

    def interrupted(audio, language):
        nonlocal attempts
        attempts += 1
        if attempts > 1:
            raise RuntimeError("simulated recognizer interruption")
        return {"language": "en", "segments": [{"words": [{"word": "Alpha", "start": 1, "end": 2}]}]}

    audio = np.zeros(50 * 16000, dtype=np.float32)
    with pytest.raises(RuntimeError):
        transcribe_chunks(audio, [(24, 26)], tmp_path, "en", interrupted)

    def continuation(audio, language):
        return {"language": "en", "segments": [{"words": [{"word": "Beta", "start": 1, "end": 2}]}]}

    words, language = transcribe_chunks(audio, [(24, 26)], tmp_path, "en", continuation)
    assert [(w.text, w.start, w.end) for w in words] == [("Alpha", 1, 2), ("Beta", 26, 27)]
    assert language == "en"


@pytest.mark.parametrize(
    "raw",
    [
        {"segments": None},
        {"segments": [None]},
        {"words": [None]},
        {"words": [{"word": "Hi", "start": 0, "end": 1, "probability": float("nan")}]},
    ],
)
def test_malformed_transcript_structure_is_a_readable_input_error(raw):
    with pytest.raises(PhrasecutError):
        read_words(raw, 2)
