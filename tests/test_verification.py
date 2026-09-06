from phrasecut.exports import export_audio
from phrasecut.models import Cut, Phrase
from phrasecut.verification import verify_speech


def test_speech_verification_flags_one_word_difference_without_prompting_script(tone_source, tmp_path):
    output = tmp_path / "out"
    export_audio(tone_source, output, [Phrase(1, "First tone.")], [Cut(1, 0.8, 2.2)], 6)
    calls = []

    def recognizer(audio, language):
        calls.append((len(audio), language))
        return {
            "language": "en",
            "words": [
                {"word": "First", "start": 0.2, "end": 0.6},
                {"word": "stone.", "start": 0.7, "end": 1.2},
            ],
        }

    result = verify_speech(output, "en", "test-model", False, transcriber=recognizer)
    assert result["matched"] == 0
    assert result["review"] == 1
    assert result["entries"][0]["differences"]
    verify_speech(output, "en", "test-model", False, transcriber=recognizer)
    assert len(calls) == 1


def test_word_timestamp_in_inserted_batch_silence_is_assigned_to_nearest_clip(tone_source, tmp_path):
    output = tmp_path / "out"
    export_audio(
        tone_source, output, [Phrase(1, "Hello."), Phrase(2, "Yes indeed.")], [Cut(1, 1, 2), Cut(2, 3, 4)], 6
    )

    def recognizer(audio, language):
        return {
            "words": [
                {"word": "Hello.", "start": 0.1, "end": 0.8},
                {"word": "Yes", "start": 1.2, "end": 1.9},
                {"word": "indeed.", "start": 1.9, "end": 2.5},
            ]
        }

    # Clip 2 starts at 1.6 s, but "Yes" has an imprecise midpoint at 1.55 s.
    report = verify_speech(output, "en", "test", transcriber=recognizer)
    assert report["matched"] == 2
