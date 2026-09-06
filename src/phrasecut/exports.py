"""Accurate PCM-based MP3 export and independently decoded file verification."""

import csv
import io
import os
import zipfile
from dataclasses import asdict
from pathlib import Path

import numpy as np

from .alignment import validate_cuts
from .jobs import atomic_json, read_json, sha256
from .media import SAMPLE_RATE, load_audio, run_ffmpeg, wav_info
from .models import Cut, PhrasecutError


def atomic_text(path, text):
    path = Path(path)
    temporary = path.with_name(path.name + ".partial")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_tables(output, phrases, cuts):
    rows = [{**asdict(phrase), **asdict(cut)} for phrase, cut in zip(phrases, cuts)]
    atomic_json(Path(output) / "phrases.json", rows)
    stream = io.StringIO(newline="")
    fields = ["id", "start", "end", "text", "translation", "section", "recognized", "coverage", "issues"]
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows({**row, "issues": ";".join(row["issues"])} for row in rows)
    atomic_text(Path(output) / "phrases.csv", stream.getvalue())
    atomic_text(Path(output) / "cuts.csv", stream.getvalue())
    review = {
        "phrase_count": len(rows),
        "boundary_review_count": sum(bool(c.issues) for c in cuts),
        "text_difference_count": sum(bool(c.differences) for c in cuts),
        "note": "ASR differences require listening; a transcript match is not proof of exact speech.",
        "entries": [r for r in rows if r["issues"] or r["differences"]],
    }
    atomic_json(Path(output) / "review.json", review)
    lines = [
        "# Phrasecut review",
        "",
        (
            f"Phrases: {len(rows)}. Boundary reviews: {review['boundary_review_count']}. "
            f"Transcript differences: {review['text_difference_count']}."
        ),
        "",
        review["note"],
        "",
    ]
    for row in review["entries"]:
        lines.extend(
            [
                f"## {row['id']:03d}",
                "",
                f"Script: {row['text']}",
                "",
                f"Recognized: {row['recognized']}",
                "",
                f"Time: {row['start']}–{row['end']}. Issues: {', '.join(row['issues']) or 'none'}.",
                "",
            ]
        )
    atomic_text(Path(output) / "review.md", "\n".join(lines))
    return review


def read_cuts_csv(path, count, duration):
    try:
        with Path(path).open(encoding="utf-8-sig", newline="") as f:
            cuts = [Cut(int(row["id"]), float(row["start"]), float(row["end"])) for row in csv.DictReader(f)]
    except (OSError, KeyError, ValueError, TypeError) as exc:
        raise PhrasecutError(f"Cuts CSV needs id,start,end columns with numeric values: {exc}") from exc
    if len(cuts) != count:
        raise PhrasecutError(f"Expected {count} cut rows; found {len(cuts)}.")
    validate_cuts(cuts, duration)
    return cuts


def export_audio(source_wav, output, phrases, cuts, duration, progress=lambda message: None):
    validate_cuts(cuts, duration)
    if len(phrases) != len(cuts):
        raise PhrasecutError("The phrase and cut counts differ.")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    info = wav_info(source_wav)
    export_cache = output / ".phrasecut/export.json"
    previous = read_json(export_cache) if export_cache.exists() else {}
    clips, width = [], max(3, len(str(len(cuts))))
    source_hash = sha256(source_wav)
    (output / "speech-verification.json").unlink(missing_ok=True)
    for phrase, cut in zip(phrases, cuts):
        name = f"{cut.id:0{width}d}.mp3"
        target = output / name
        signature = [cut.start, cut.end, source_hash]
        saved = previous.get(name, {})
        progress(f"Exporting {name} ({cut.id}/{len(cuts)})")
        if not (
            saved.get("signature") == signature and target.is_file() and saved["sha256"] == sha256(target)
        ):
            temporary = target.with_suffix(".partial.mp3")
            try:
                run_ffmpeg(
                    [
                        "-y",
                        "-ss",
                        f"{cut.start:.6f}",
                        "-i",
                        source_wav,
                        "-t",
                        f"{cut.end - cut.start:.6f}",
                        "-map",
                        "0:a:0",
                        "-map_metadata",
                        "-1",
                        "-ac",
                        min(info["channels"], 2),
                        "-c:a",
                        "libmp3lame",
                        "-b:a",
                        "192k",
                        "-metadata",
                        f"title={phrase.text}",
                        "-metadata",
                        f"track={cut.id}/{len(cuts)}",
                        temporary,
                    ]
                )
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
            saved = {"signature": signature, "sha256": sha256(target)}
            previous[name] = saved
            atomic_json(export_cache, previous)
        clips.append({**asdict(phrase), **asdict(cut), "file": name, "sha256": saved["sha256"]})
    manifest = {
        "schema": 1,
        "count": len(clips),
        "source_duration": duration,
        "source_channels": info["channels"],
        "export_channels": min(info["channels"], 2),
        "clips": clips,
    }
    write_tables(output, phrases, cuts)
    atomic_json(output / "manifest.json", manifest)
    atomic_text(output / "playlist.m3u8", "#EXTM3U\n" + "\n".join(c["file"] for c in clips) + "\n")
    make_archive(output, manifest)
    return manifest


def make_archive(output, manifest):
    output = Path(output)
    temporary = output / "phrases.partial.zip"
    names = [c["file"] for c in manifest["clips"]] + [
        "phrases.csv",
        "phrases.json",
        "cuts.csv",
        "manifest.json",
        "review.json",
        "review.md",
        "playlist.m3u8",
    ]
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in names:
                archive.write(output / name, name)
            for name in ["verification.json", "speech-verification.json"]:
                if (output / name).exists():
                    archive.write(output / name, name)
        os.replace(temporary, output / "phrases.zip")
    finally:
        temporary.unlink(missing_ok=True)


def verify_files(output, source_audio=None, progress=lambda message: None):
    output = Path(output)
    manifest = read_json(output / "manifest.json")
    expected = {c["file"] for c in manifest["clips"]}
    actual = {p.name for p in output.glob("*.mp3")}
    errors = [f"Missing files: {sorted(expected - actual)}"] if expected - actual else []
    if actual - expected:
        errors.append(f"Unexpected MP3 files: {sorted(actual - expected)}")
    results = []
    for clip in manifest["clips"]:
        path = output / clip["file"]
        row = {"id": clip["id"], "file": clip["file"], "errors": []}
        progress(f"Checking {clip['file']}")
        try:
            if path.name != clip["file"] or not path.is_file():
                raise PhrasecutError("Missing or invalid clip path.")
            if sha256(path) != clip["sha256"]:
                raise PhrasecutError("File checksum changed since export.")
            decoded = load_audio(path)
            row["decoded_duration"] = len(decoded) / SAMPLE_RATE
            expected_length = clip["end"] - clip["start"]
            if abs(row["decoded_duration"] - expected_length) > 0.065:
                raise PhrasecutError("Decoded duration does not match the requested cut.")
            if source_audio is not None:
                offset = round(clip["start"] * SAMPLE_RATE)
                reference = source_audio[offset : offset + len(decoded)]
                size = min(len(reference), len(decoded))
                a, b = reference[:size].astype(np.float64), decoded[:size].astype(np.float64)
                denominator = np.linalg.norm(a) * np.linalg.norm(b)
                correlation = float(np.dot(a, b) / denominator) if denominator > 1e-9 else None
                row["source_correlation"] = correlation
                if correlation is not None and correlation < 0.96:
                    raise PhrasecutError("Decoded waveform does not match the source interval.")
        except (PhrasecutError, OSError) as exc:
            row["errors"].append(str(exc))
            errors.append(f"{clip['file']}: {exc}")
        results.append(row)
    result = {"count": len(results), "errors": errors, "clips": results}
    atomic_json(output / "verification.json", result)
    return result
