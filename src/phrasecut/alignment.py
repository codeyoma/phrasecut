"""Monotonic text/audio alignment with explicit uncertainty, never equal-duration guessing."""

import itertools
import math

from rapidfuzz.distance import Levenshtein

from .models import Cut, PhrasecutError
from .normalize import alignment_text, differences, joined_words


def best_local_words(phrase, words, language):
    reference = alignment_text(phrase.text, language)
    tokens = [alignment_text(w.text, language) for w in words]
    best, chosen = (float("inf"), float("inf")), []
    for start in range(len(words)):
        text = ""
        for end in range(start, len(words)):
            text += tokens[end]
            if len(text) > len(reference) * 1.6 + 8:
                break
            score = (Levenshtein.distance(reference, text) / max(1, len(reference)), end - start)
            if score < best:
                best, chosen = score, words[start : end + 1]
    return chosen if best[0] <= 0.4 else []


def align(phrases, words, silences, language, duration, padding_before=0.15, padding_after=0.22):
    reference, ranges = "", []
    for phrase in phrases:
        text = alignment_text(phrase.text, language)
        ranges.append((len(reference), len(reference) + len(text)))
        reference += text
    hypothesis, owners = "", []
    for i, word in enumerate(words):
        text = alignment_text(word.text, language)
        hypothesis += text
        owners.extend([i] * len(text))
    matched = {}
    for op in Levenshtein.opcodes(reference, hypothesis):
        if op.tag == "equal":
            for a, b in zip(range(op.src_start, op.src_end), range(op.dest_start, op.dest_end)):
                matched[a] = owners[b]
    gaps = [(s, e) for s, e in silences if e - s >= 0.299]
    cuts = []
    for phrase, (lo, hi) in zip(phrases, ranges):
        hits = [(i, matched[i]) for i in range(lo, hi) if i in matched]
        coverage = len(hits) / max(1, hi - lo)
        if not hits or coverage < 0.55:
            cuts.append(Cut(phrase.id, None, None, coverage=round(coverage, 4), issues=["unmatched"]))
            continue
        first_index, last_index = hits[0][1], hits[-1][1]
        selected = best_local_words(phrase, words[first_index : last_index + 1], language)
        if not selected:
            cuts.append(Cut(phrase.id, None, None, coverage=round(coverage, 4), issues=["unmatched"]))
            continue
        # Whole-phrase matching removes introductory words that share individual letters with the script.
        reference_text = alignment_text(phrase.text, language)
        hypothesis_text = "".join(alignment_text(w.text, language) for w in selected)
        equal = [op for op in Levenshtein.opcodes(reference_text, hypothesis_text) if op.tag == "equal"]
        coverage = sum(op.src_end - op.src_start for op in equal) / max(1, len(reference_text))
        first, last = selected[0], selected[-1]
        issues = []
        if coverage < 0.88:
            issues.append("low_coverage")
        if not equal or equal[0].src_start > 0:
            issues.append("opening_unmatched")
        if not equal or equal[-1].src_end < len(reference_text):
            issues.append("ending_unmatched")
        if first.end <= first.start or last.end <= last.start:
            issues.append("zero_word_duration")
        before = [(s, e) for s, e in gaps if first.start - 1.5 <= e <= first.end + 0.025]
        after = [(s, e) for s, e in gaps if last.start + 0.03 <= s <= last.end + 1.3]
        pre = max(before, key=lambda g: g[1]) if before else None
        post = min(after, key=lambda g: g[0]) if after else None
        start = max(0.0, (pre[1] if pre else first.start) - padding_before)
        end = min(duration, (post[0] if post else last.end) + padding_after)
        if not pre and first.start > 0.3:
            issues.append("no_start_pause")
        if not post and last.end < duration - 0.3:
            issues.append("no_end_pause")
        if pre and abs(pre[1] - first.start) > 0.6 and not pre[0] - 0.1 <= first.start <= pre[1]:
            issues.append("start_shift")
        if post and abs(post[0] - last.end) > 0.6:
            issues.append("end_shift")
        if end <= start:
            issues.append("invalid_interval")
        spoken = joined_words(selected, language)
        cuts.append(
            Cut(
                phrase.id,
                round(start, 5),
                round(end, 5),
                spoken,
                round(coverage, 4),
                issues,
                differences(phrase.text, spoken),
            )
        )
    for previous, current in itertools.pairwise(cuts):
        if previous.end is not None and current.start is not None and previous.end > current.start:
            previous.issues.append("overlap")
            current.issues.append("overlap")
    return cuts


def validate_cuts(cuts, duration):
    previous_end = 0.0
    for i, cut in enumerate(cuts, 1):
        if cut.id != i:
            raise PhrasecutError("Cut IDs must be consecutive and in script order.")
        if cut.start is None or cut.end is None:
            raise PhrasecutError(
                f"Phrase {cut.id}: no matched interval; supply actual start/end times in cuts.csv."
            )
        if not all(math.isfinite(t) for t in (cut.start, cut.end)):
            raise PhrasecutError(f"Phrase {cut.id}: timestamps must be finite numbers.")
        if not (0 <= cut.start < cut.end <= duration + 0.001):
            raise PhrasecutError(
                f"Phrase {cut.id}: invalid interval {cut.start}–{cut.end}; source is {duration:.3f}s."
            )
        if cut.start < previous_end - 0.00001:
            raise PhrasecutError(f"Phrase {cut.id}: interval overlaps the previous phrase.")
        previous_end = cut.end
