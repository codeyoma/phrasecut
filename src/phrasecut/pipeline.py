"""Repeatable local jobs; recognition evidence stays separate from the user's script."""

import re
from dataclasses import asdict, replace
from pathlib import Path

from .alignment import align, validate_cuts
from .exports import export_audio, make_archive, read_cuts_csv, verify_files, write_tables
from .jobs import assert_source_unchanged, atomic_json, create_job, load_job, read_json, sha256
from .media import decode_to_wav, detect_silences, load_audio, wav_info
from .models import Cut, Phrase, PhrasecutError
from .recognition import LocalRecognizer, read_words, transcribe_chunks
from .scripts import parse_script


def spoken_phrases(phrases, ignore_parentheticals, omit_notes=()):
    if not ignore_parentheticals and not omit_notes:
        return phrases
    result = []
    for phrase in phrases:
        text = phrase.text
        if ignore_parentheticals:
            while re.search(r"\([^()]*\)|（[^（）]*）", text):
                text = re.sub(r"\([^()]*\)|（[^（）]*）", "", text)
        for note in omit_notes:
            text = text.replace(f"({note})", "").replace(f"（{note}）", "")
        if not any(c.isalnum() for c in text):
            raise PhrasecutError(f"Phrase {phrase.id} has no spoken text after removing parentheses.")
        result.append(replace(phrase, text=text.strip()))
    return result


def save_job(output, job):
    atomic_json(Path(output) / ".phrasecut/job.json", job)


def source_cache(output, job, progress):
    assert_source_unchanged(job)
    cache = Path(output) / ".phrasecut"
    source = cache / "source.wav"
    if source.exists() and job.get("decoded_sha256"):
        if sha256(source) != job["decoded_sha256"]:
            raise PhrasecutError("Decoded audio cache changed. Use a new output directory.")
        info = wav_info(source)
    else:
        progress("Decoding the source audio…")
        info = decode_to_wav(job["audio"], source)
        job["decoded_sha256"] = sha256(source)
        job["audio_info"] = info
        save_job(output, job)
    audio = load_audio(source, cache / "audio16k.f32")
    audio_hash = sha256(cache / "audio16k.f32")
    if job.get("recognition_sha256") and job["recognition_sha256"] != audio_hash:
        raise PhrasecutError("Recognition audio cache changed. Use a new output directory.")
    if not job.get("recognition_sha256"):
        job["recognition_sha256"] = audio_hash
        save_job(output, job)
    if abs(len(audio) / 16000 - info["duration"]) > 0.03:
        raise PhrasecutError("Recognition audio cache is incomplete. Use a new output directory.")
    return source, audio, info


def split(args, progress):
    phrases = parse_script(args.script, args.format, args.expect)
    spoken = spoken_phrases(phrases, args.ignore_parentheticals, args.omit_note)
    options = {
        k: getattr(args, k)
        for k in [
            "format",
            "expect",
            "language",
            "model",
            "padding_before",
            "padding_after",
            "ignore_parentheticals",
        ]
    }
    options["omit_note"] = args.omit_note
    options["transcript_sha256"] = sha256(args.transcript) if args.transcript else None
    output = Path(args.output)
    job = create_job(output, args.audio, args.script, options, args.resume)
    cache = output / ".phrasecut"
    atomic_json(cache / "script.json", [asdict(p) for p in phrases])
    source, audio, info = source_cache(output, job, progress)
    if args.resume and job["phase"] == "exported":
        progress("Job already exported; checking its files.")
        result = verify_files(output, audio, progress)
        if result["errors"]:
            raise PhrasecutError("; ".join(result["errors"][:5]))
        print(f"Verified {result['count']} MP3 files: {output}")
        return 0
    progress(f"Parsed {len(phrases)} phrases; source duration {info['duration']:.1f}s.")
    silences = detect_silences(audio)
    atomic_json(cache / "silences.json", silences)
    if args.transcript:
        raw = read_json(args.transcript)
        if raw.get("audio_sha256", job["audio_sha256"]) != job["audio_sha256"]:
            raise PhrasecutError("The transcript belongs to different source audio.")
        words = read_words(raw, info["duration"])
        language = args.language if args.language != "auto" else raw.get("language", "auto")
        if language == "auto":
            raise PhrasecutError("Imported transcripts need a language field or --language.")
    else:
        recognizer = LocalRecognizer(args.model)
        end = (
            silences[-1][0] + 0.3
            if silences and silences[-1][1] >= info["duration"] - 0.03
            else info["duration"]
        )
        words, language = transcribe_chunks(
            audio[: round(end * 16000)], silences, cache / "chunks", args.language, recognizer, progress
        )
    atomic_json(cache / "transcript.json", {"language": language, "words": [asdict(w) for w in words]})
    progress("Aligning the script with recognized speech…")
    cuts = align(spoken, words, silences, language, info["duration"], args.padding_before, args.padding_after)
    if not args.transcript and any(c.issues for c in cuts):
        from .refinement import refine

        cuts = refine(
            spoken,
            cuts,
            audio,
            silences,
            language,
            info["duration"],
            cache / "refinement",
            recognizer,
            args.padding_before,
            args.padding_after,
            progress,
        )
    job["language"], job["phase"] = language, "aligned"
    atomic_json(cache / "alignment.json", [asdict(c) for c in cuts])
    review = write_tables(output, phrases, cuts)
    save_job(output, job)
    try:
        validate_cuts(cuts, info["duration"])
    except PhrasecutError as exc:
        progress(str(exc))
        job["phase"] = "review_required"
        save_job(output, job)
        print(f"Review required. Edit {output / 'cuts.csv'}, then run phrasecut export.")
        return 2
    if review["boundary_review_count"] and not args.accept_review:
        job["phase"] = "review_required"
        save_job(output, job)
        print(f"{review['boundary_review_count']} boundaries need review: {output / 'review.md'}")
        print(
            "Edit cuts.csv and run phrasecut export, or rerun with --resume --accept-review to accept estimates."
        )
        return 2
    job["phase"] = "exporting"
    save_job(output, job)
    manifest = export_audio(source, output, phrases, cuts, info["duration"], progress)
    result = verify_files(output, audio, progress)
    make_archive(output, manifest)
    if result["errors"]:
        raise PhrasecutError("; ".join(result["errors"][:5]))
    job["phase"] = "exported"
    save_job(output, job)
    print(f"Exported and checked {len(cuts)} MP3 files: {output}")
    print(f"Transcript differences to listen to: {review['text_difference_count']}. See review.md.")
    return 0


def export(args, progress):
    output = Path(args.output)
    job = load_job(output)
    source, audio, info = source_cache(output, job, progress)
    phrases = [Phrase(**p) for p in read_json(output / ".phrasecut/script.json")]
    proposed = [Cut(**c) for c in read_json(output / ".phrasecut/alignment.json")]
    cuts = read_cuts_csv(args.cuts, len(phrases), info["duration"])
    unchanged_issues = []
    for cut, prior in zip(cuts, proposed):
        if (cut.start, cut.end) == (prior.start, prior.end):
            cut.recognized, cut.coverage = prior.recognized, prior.coverage
            cut.issues, cut.differences = list(prior.issues), list(prior.differences)
            if cut.issues:
                unchanged_issues.append(cut.id)
        else:
            # Existing recognition evidence does not verify newly edited boundaries.
            cut.issues = ["manually_edited_unverified"]
    if unchanged_issues and not args.accept_review:
        raise PhrasecutError(
            f"Unchanged flagged cuts: {unchanged_issues}. Edit their times or use --accept-review."
        )
    atomic_json(output / ".phrasecut/exported-cuts.json", [asdict(c) for c in cuts])
    job["phase"] = "exporting"
    save_job(output, job)
    manifest = export_audio(source, output, phrases, cuts, info["duration"], progress)
    result = verify_files(output, audio, progress)
    make_archive(output, manifest)
    if result["errors"]:
        raise PhrasecutError("; ".join(result["errors"][:5]))
    job["phase"] = "exported"
    save_job(output, job)
    print(f"Exported and checked {len(cuts)} MP3 files: {output}")
    return 0


def verify(args, progress):
    output = Path(args.output)
    job = load_job(output)
    _, audio, _ = source_cache(output, job, progress)
    result = verify_files(output, audio, progress)
    if result["errors"]:
        raise PhrasecutError("; ".join(result["errors"][:10]))
    print(f"File checks passed: {result['count']} MP3 files.")
    if args.speech:
        from .verification import verify_speech

        model = args.model or job["options"]["model"]
        result = verify_speech(
            output,
            job["language"],
            model,
            job["options"]["ignore_parentheticals"],
            progress,
            omit_notes=job["options"].get("omit_note", []),
        )
        make_archive(output, read_json(output / "manifest.json"))
        print(
            f"Speech transcript matches: {result['matched']}/{result['count']}; review: {result['review']}."
        )
        return 2 if result["review"] else 0
    return 0
