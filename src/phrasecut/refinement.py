"""Recheck uncertain boundaries in a short local window, without a script prompt."""

import hashlib
import json
from dataclasses import replace
from itertools import pairwise
from pathlib import Path

from .alignment import align, best_local_words
from .jobs import atomic_json, read_json
from .models import Word
from .recognition import read_words


def refine(
    phrases,
    cuts,
    audio,
    silences,
    language,
    duration,
    cache_dir,
    transcriber,
    padding_before=0.15,
    padding_after=0.22,
    progress=lambda message: None,
):
    result = [replace(c, issues=list(c.issues)) for c in cuts]
    for i, (phrase, cut) in enumerate(zip(phrases, cuts)):
        if not cut.issues:
            continue
        left = cuts[i - 1].end if i and cuts[i - 1].end is not None else 0.0
        right = cuts[i + 1].start if i + 1 < len(cuts) and cuts[i + 1].start is not None else duration
        start = max(0.0, min(cut.start, left) - 1 if cut.start is not None else left - 1)
        end = min(duration, max(cut.end, right) + 1 if cut.end is not None else right + 1)
        # Do not turn a missing long passage into an arbitrary guessed interval.
        if end <= start or end - start > 29:
            continue
        progress(f"Rechecking phrase {phrase.id} ({start:.1f}–{end:.1f}s)")
        key = hashlib.sha256(json.dumps([phrase.id, start, end, language]).encode()).hexdigest()
        path = Path(cache_dir) / f"{key}.json"
        if path.exists():
            raw = read_json(path)
        else:
            raw = transcriber(audio[round(start * 16000) : round(end * 16000)], language)
            read_words(raw, end - start)
            atomic_json(path, raw)
        words = [
            Word(w.text, w.start + start, w.end + start, w.probability) for w in read_words(raw, end - start)
        ]
        selected = best_local_words(phrase, words, language)
        if not selected:
            continue
        proposed = align([phrase], selected, silences, language, duration, padding_before, padding_after)[0]
        if proposed.start is None or proposed.end is None:
            continue
        if proposed.start < left - 0.00001 or proposed.end > right + 0.00001:
            continue
        prior_issues = set(cut.issues) - {"overlap"}
        if proposed.coverage >= cut.coverage - 0.03 and len(proposed.issues) <= len(prior_issues):
            result[i] = proposed
    for cut in result:
        cut.issues = [issue for issue in cut.issues if issue != "overlap"]
    for previous, current in pairwise(result):
        if previous.end is not None and current.start is not None and previous.end > current.start:
            previous.issues.append("overlap")
            current.issues.append("overlap")
    return result
