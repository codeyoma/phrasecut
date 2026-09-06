"""Local multilingual ASR; each completed chunk is an independent resume checkpoint."""

import math
import os
import platform
from pathlib import Path

from .jobs import atomic_json, read_json
from .media import SAMPLE_RATE, chunk_ranges
from .models import PhrasecutError, Word

DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"


def read_words(raw, duration):
    if not isinstance(raw, dict):
        raise PhrasecutError("Transcript must be a JSON object with word timestamps.")
    entries = raw.get("words")
    if entries is None:
        segments = raw.get("segments", [])
        if not isinstance(segments, list) or any(not isinstance(segment, dict) for segment in segments):
            raise PhrasecutError("Transcript segments must be an array of objects.")
        if any(not isinstance(segment.get("words", []), list) for segment in segments):
            raise PhrasecutError("Each transcript segment needs an array of words.")
        if any(str(s.get("text", "")).strip() and "words" not in s for s in segments):
            raise PhrasecutError("Transcript requires word timestamps, not just segment timestamps.")
        entries = [word for segment in segments for word in segment.get("words", [])]
    if not isinstance(entries, list):
        raise PhrasecutError("Transcript words must be an array.")
    words = []
    previous_start = 0.0
    try:
        for entry in entries:
            if not isinstance(entry, dict):
                raise TypeError("word entries must be objects")
            text = entry.get("word", entry.get("text", ""))
            start, end = float(entry["start"]), float(entry["end"])
            if (
                not isinstance(text, str)
                or not text.strip()
                or not all(math.isfinite(t) for t in (start, end))
                or not 0 <= start <= end <= duration + 0.03
                or start < previous_start
            ):
                raise ValueError("invalid text, order or timestamps")
            probability = float(entry.get("probability", 1))
            if not math.isfinite(probability) or not 0 <= probability <= 1:
                raise ValueError("word probability must be between 0 and 1")
            words.append(Word(text, start, min(end, duration), probability))
            previous_start = start
    except (KeyError, TypeError, ValueError) as exc:
        raise PhrasecutError(f"Invalid word timestamp: {exc}") from exc
    if not entries and "words" not in raw and "segments" not in raw:
        raise PhrasecutError("Transcript has no word timestamps.")
    return words


def transcribe_chunks(audio, silences, cache_dir, language, transcriber, progress=lambda message: None):
    cache_dir = Path(cache_dir)
    ranges = chunk_ranges(len(audio) / SAMPLE_RATE, silences)
    result, detected = [], language
    for i, (start, end) in enumerate(ranges):
        path = cache_dir / f"{i:05d}.json"
        progress(
            f"Recognizing chunk {i + 1}/{len(ranges)} ({start:.1f}–{end:.1f}s)"
            + (" · cached" if path.exists() else "")
        )
        if path.exists():
            saved = read_json(path)
            if saved["start"] != start or saved["end"] != end:
                raise PhrasecutError("Chunk cache does not match this audio. Use a new output directory.")
            raw = saved["result"]
        else:
            raw = transcriber(audio[round(start * SAMPLE_RATE) : round(end * SAMPLE_RATE)], language)
            read_words(raw, end - start)
            atomic_json(path, {"start": start, "end": end, "result": raw})
        detected = raw.get("language", detected) if detected in ("auto", None) else detected
        # Each overlapping word belongs to the chunk containing its midpoint.
        left = (ranges[i - 1][1] + start) / 2 if i else 0
        right = (end + ranges[i + 1][0]) / 2 if i + 1 < len(ranges) else end
        for word in read_words(raw, end - start):
            midpoint = start + (word.start + word.end) / 2
            if left <= midpoint < right or (i == len(ranges) - 1 and midpoint == right):
                result.append(Word(word.text, start + word.start, start + word.end, word.probability))
    return result, detected or "auto"


def model_cache():
    return Path(os.environ.get("HF_HOME", Path.home() / ".cache/phrasecut/models"))


def supported_languages():
    try:
        from mlx_whisper.tokenizer import LANGUAGES
    except ImportError as exc:
        raise PhrasecutError(
            "Local recognizer missing. Rerun this project's install.sh."
        ) from exc
    return LANGUAGES


class LocalRecognizer:
    def __init__(self, model=DEFAULT_MODEL):
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            raise PhrasecutError("Local speech recognition currently requires macOS on Apple Silicon.")
        os.environ.setdefault("HF_HOME", str(model_cache()))
        try:
            import mlx_whisper
        except ImportError as exc:
            raise PhrasecutError(
                "Local recognizer missing. Rerun this project's install.sh."
            ) from exc
        self.backend, self.model = mlx_whisper, model

    def __call__(self, audio, language):
        import numpy as np

        if language != "auto" and language not in supported_languages():
            raise PhrasecutError(f"Unknown language code: {language}. Run phrasecut languages.")
        return self.backend.transcribe(
            np.asarray(audio).copy(),
            path_or_hf_repo=self.model,
            language=None if language == "auto" else language,
            task="transcribe",
            word_timestamps=True,
            condition_on_previous_text=False,
            temperature=(0.0, 0.2),
            verbose=None,
        )
