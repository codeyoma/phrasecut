"""A second recognition pass reads the exported MP3s without seeing the expected script."""

import hashlib
import json
from pathlib import Path

import numpy as np

from .jobs import atomic_json, read_json
from .media import SAMPLE_RATE, detect_silences, load_audio
from .models import Phrase
from .normalize import alignment_text, comparison_text, differences, joined_words
from .recognition import LocalRecognizer, transcribe_chunks


def verify_speech(
    output,
    language,
    model,
    ignore_parentheticals=False,
    progress=lambda message: None,
    transcriber=None,
    omit_notes=(),
):
    from .pipeline import spoken_phrases

    output = Path(output)
    manifest = read_json(output / "manifest.json")
    transcriber = transcriber or LocalRecognizer(model)
    groups, group, seconds = [], [], 0.0
    for clip in manifest["clips"]:
        duration = clip["end"] - clip["start"]
        if group and seconds + duration + 0.6 > 25:
            groups.append(group)
            group, seconds = [], 0.0
        group.append(clip)
        seconds += duration + 0.6
    if group:
        groups.append(group)
    results = []
    for i, clips in enumerate(groups, 1):
        progress(f"Verifying speech batch {i}/{len(groups)} · phrases {clips[0]['id']}–{clips[-1]['id']}")
        signature = json.dumps([model, language, [(c["id"], c["sha256"]) for c in clips]])
        key = hashlib.sha256(signature.encode()).hexdigest()
        audio_parts, intervals, offset = [], [], 0.0
        for clip in clips:
            audio = load_audio(output / clip["file"])
            end = offset + len(audio) / SAMPLE_RATE
            intervals.append((offset, end))
            audio_parts.extend([audio, np.zeros(round(0.6 * SAMPLE_RATE), dtype=np.float32)])
            offset = end + 0.6
        joined = np.concatenate(audio_parts)
        words, _ = transcribe_chunks(
            joined, detect_silences(joined), output / ".phrasecut/verification" / key, language, transcriber
        )
        for index, (clip, (start, end)) in enumerate(zip(clips, intervals)):
            left = (intervals[index - 1][1] + start) / 2 if index else 0.0
            right = (
                (end + intervals[index + 1][0]) / 2
                if index + 1 < len(intervals)
                else len(joined) / SAMPLE_RATE
            )
            selected = [w for w in words if left <= (w.start + w.end) / 2 < right]
            recognized = joined_words(selected, language)
            expected = spoken_phrases([Phrase(clip["id"], clip["text"])], ignore_parentheticals, omit_notes)[
                0
            ].text
            exact = comparison_text(expected) == comparison_text(recognized)
            results.append(
                {
                    "id": clip["id"],
                    "file": clip["file"],
                    "script": clip["text"],
                    "spoken_script": expected,
                    "recognized": recognized,
                    "status": "transcript_match" if exact else "review",
                    "same_reading": alignment_text(expected, language)
                    == alignment_text(recognized, language),
                    "differences": differences(expected, recognized),
                }
            )
    report = {
        "model": model,
        "language": language,
        "count": len(results),
        "matched": sum(r["status"] == "transcript_match" for r in results),
        "review": sum(r["status"] == "review" for r in results),
        "note": "Case and punctuation are ignored. Wording and spelling differences require listening. "
        "A transcript match is automated evidence, not a guarantee of exact speech.",
        "entries": results,
    }
    atomic_json(output / "speech-verification.json", report)
    return report
