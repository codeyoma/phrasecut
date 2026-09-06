"""Persistent jobs are owned, content-addressed, and written atomically."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from .models import PhrasecutError

SCHEMA = 1


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".writing-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise PhrasecutError(f"Cannot read {path}: {exc}") from exc


def load_job(output):
    job = read_json(Path(output) / ".phrasecut/job.json")
    if job.get("schema") != SCHEMA:
        raise PhrasecutError("Unsupported job version. Use a new output directory.")
    return job


def create_job(output, audio, script, options, resume=False):
    output, audio, script = Path(output), Path(audio).resolve(), Path(script).resolve()
    if not audio.is_file() or not script.is_file():
        raise PhrasecutError("Both the audio and script must be existing files.")
    fingerprints = {"audio_sha256": sha256(audio), "script_sha256": sha256(script)}
    if resume:
        job = load_job(output)
        if any(job[k] != v for k, v in fingerprints.items()):
            raise PhrasecutError("Input audio or script changed; use a new output directory.")
        if job["options"] != options:
            raise PhrasecutError(
                "Processing options changed; resume needs the same language, model and parser options."
            )
        return job
    if output.exists() and any(output.iterdir()):
        raise PhrasecutError(
            "Output directory is not empty. Use --resume for an existing job or choose a new directory."
        )
    output.mkdir(parents=True, exist_ok=True)
    job = {
        "schema": SCHEMA,
        "audio": str(audio),
        "script": str(script),
        **fingerprints,
        "options": options,
        "phase": "created",
    }
    atomic_json(output / ".phrasecut/job.json", job)
    return job


def assert_source_unchanged(job):
    if not Path(job["audio"]).is_file() or sha256(job["audio"]) != job["audio_sha256"]:
        raise PhrasecutError(
            "The source audio changed or is missing. Restore it before exporting or verifying."
        )
