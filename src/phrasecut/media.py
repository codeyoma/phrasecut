import os
import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np

from .models import PhrasecutError

SAMPLE_RATE = 16000


def ffmpeg():
    return imageio_ffmpeg.get_ffmpeg_exe()


def run_ffmpeg(arguments, stdout=subprocess.PIPE):
    try:
        return subprocess.run(
            [ffmpeg(), "-hide_banner", "-nostdin", "-v", "error", *map(str, arguments)],
            stdout=stdout,
            stderr=subprocess.PIPE,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise PhrasecutError("FFmpeg: " + exc.stderr.decode(errors="replace")[-1500:]) from exc


def wav_info(path):
    try:
        with wave.open(str(path), "rb") as f:
            return {
                "duration": f.getnframes() / f.getframerate(),
                "sample_rate": f.getframerate(),
                "channels": f.getnchannels(),
            }
    except (wave.Error, EOFError) as exc:
        raise PhrasecutError(f"Invalid decoded WAV: {path}") from exc


def decode_to_wav(source, target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.stem + ".partial.wav")
    try:
        run_ffmpeg(
            ["-y", "-i", source, "-map", "0:a:0", "-map_metadata", "-1", "-c:a", "pcm_s16le", temporary]
        )
        info = wav_info(temporary)
        if info["duration"] <= 0:
            raise PhrasecutError("The source contains no audio.")
        os.replace(temporary, target)
        return info
    finally:
        temporary.unlink(missing_ok=True)


def load_audio(source, cache=None):
    args = ["-i", source, "-map", "0:a:0", "-ar", SAMPLE_RATE, "-ac", 1, "-f", "f32le", "-"]
    if cache is None:
        return np.frombuffer(run_ffmpeg(args).stdout, dtype=np.float32).copy()
    cache = Path(cache)
    if not cache.exists():
        temporary = cache.with_suffix(".partial")
        try:
            with temporary.open("wb") as f:
                run_ffmpeg(args, stdout=f)
            if not temporary.stat().st_size or temporary.stat().st_size % 4:
                raise PhrasecutError("Audio decoding produced an incomplete cache.")
            os.replace(temporary, cache)
        finally:
            temporary.unlink(missing_ok=True)
    return np.memmap(cache, dtype=np.float32, mode="r")


def detect_silences(audio, threshold_db=-45.0, minimum=0.3):
    # Scan in blocks so long recordings do not allocate an audio-sized energy array.
    frame = 160
    energies = []
    for offset in range(0, len(audio) // frame * frame, frame * 6000):
        block = np.asarray(audio[offset : min(offset + frame * 6000, len(audio) // frame * frame)])
        energies.append(np.sqrt(np.mean(block.reshape(-1, frame) ** 2, axis=1)))
    if not energies:
        return []
    quiet = np.concatenate(energies) < 10 ** (threshold_db / 20)
    edges = np.diff(np.r_[False, quiet, False].astype(np.int8))
    return [
        (float(s / 100), float(e / 100))
        for s, e in zip(np.where(edges == 1)[0], np.where(edges == -1)[0])
        if (e - s) / 100 >= minimum
    ]


def chunk_ranges(duration, silences):
    chunks, start = [], 0.0
    while start < duration:
        if duration - start <= 27:
            chunks.append((start, duration))
            break
        candidates = [(s + e) / 2 for s, e in silences if start + 15 <= (s + e) / 2 <= start + 27]
        if candidates:
            end = min(candidates, key=lambda x: abs(x - (start + 25)))
            chunks.append((start, end))
            start = end
        else:
            end = min(start + 27, duration)
            chunks.append((start, end))
            start = end - 1  # Overlap only when no natural pause exists.
    return chunks
