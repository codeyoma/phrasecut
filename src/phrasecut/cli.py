"""The CLI imports the heavy recognizer only when a command needs it."""

import argparse
import json
import math
import platform
import sys
from pathlib import Path

from filelock import FileLock, Timeout

from . import __version__
from .models import PhrasecutError
from .recognition import DEFAULT_MODEL, model_cache, supported_languages
from .scripts import FORMATS, parse_script


def parser():
    p = argparse.ArgumentParser(
        prog="phrasecut", description="Split audio into one MP3 per script entry, locally."
    )
    p.add_argument("--version", action="version", version=f"phrasecut {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    preview = sub.add_parser("preview", help="Check how a script will be divided before recognizing audio.")
    preview.add_argument("script", type=Path)
    preview.add_argument("--format", choices=FORMATS, default="auto")
    preview.add_argument("--expect", type=int, help="Require this exact phrase count.")
    preview.add_argument("--json", action="store_true", help="Print all parsed entries as JSON.")
    split = sub.add_parser("split", help="Recognize, align, export MP3s and check the resulting files.")
    split.add_argument("audio", type=Path)
    split.add_argument("script", type=Path)
    split.add_argument("-o", "--output", type=Path, required=True, help="New directory for this job.")
    split.add_argument("--format", choices=FORMATS, default="auto")
    split.add_argument("--expect", type=int)
    split.add_argument("--language", default="auto", help="Whisper code: en, ja, es, ko, etc., or auto.")
    split.add_argument("--model", default=DEFAULT_MODEL)
    split.add_argument(
        "--resume", action="store_true", help="Continue an interrupted job with identical inputs/options."
    )
    split.add_argument(
        "--transcript", type=Path, help="Import a Whisper-compatible JSON with word timestamps."
    )
    split.add_argument(
        "--ignore-parentheticals", action="store_true", help="Exclude parenthesized notes from alignment."
    )
    split.add_argument(
        "--omit-note",
        action="append",
        default=[],
        metavar="TEXT",
        help="Omit only this exact parenthesized note; repeat for multiple notes.",
    )
    split.add_argument("--padding-before", type=float, default=0.15, metavar="SECONDS")
    split.add_argument("--padding-after", type=float, default=0.22, metavar="SECONDS")
    split.add_argument(
        "--accept-review", action="store_true", help="Export valid but flagged estimated intervals."
    )
    export = sub.add_parser("export", help="Export using reviewed start/end times from cuts.csv.")
    export.add_argument("output", type=Path)
    export.add_argument("--cuts", type=Path, required=True)
    export.add_argument(
        "--accept-review", action="store_true", help="Accept unchanged flagged estimated intervals."
    )
    verify = sub.add_parser("verify", help="Check every exported MP3; optionally recognize its speech again.")
    verify.add_argument("output", type=Path)
    verify.add_argument("--speech", action="store_true")
    verify.add_argument("--model", help="Independent verification model; default is the job model.")
    sub.add_parser("doctor", help="Check the runtime and display the local model cache.")
    sub.add_parser("languages", help="List supported Whisper language codes.")
    return p


def progress(message):
    print(message, file=sys.stderr, flush=True)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "preview":
            from dataclasses import asdict

            phrases = parse_script(args.script, args.format, args.expect)
            if args.json:
                print(json.dumps([asdict(p) for p in phrases], ensure_ascii=False, indent=2))
            else:
                print(f"{len(phrases)} script entries")
                for phrase in phrases[:12]:
                    print(f"{phrase.id:03d}  {phrase.text}")
                if len(phrases) > 12:
                    print(f"… {len(phrases) - 12} more. Use --json for every entry.")
            return 0
        if args.command == "languages":
            for code, name in supported_languages().items():
                print(f"{code:4} {name}")
            return 0
        if args.command == "doctor":
            from importlib.metadata import PackageNotFoundError, version

            from .media import ffmpeg

            print(
                f"phrasecut {__version__}\nPython: {sys.version.split()[0]}\nSystem: {platform.system()} {platform.machine()}"
            )
            print(f"FFmpeg: {ffmpeg()}\nModel cache: {model_cache()}")
            try:
                print(f"Local recognizer: mlx-whisper {version('mlx-whisper')}")
            except PackageNotFoundError:
                print("Local recognizer is not installed. Install this project with the [asr] extra.")
                return 1
            return 0
        if args.command == "split" and any(
            not math.isfinite(x) or not 0 <= x <= 2 for x in [args.padding_before, args.padding_after]
        ):
            raise PhrasecutError("Padding must be between 0 and 2 seconds.")
        from . import pipeline

        args.output = args.output.expanduser().resolve()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(args.output) + ".phrasecut.lock", timeout=0)
        with lock:
            return getattr(pipeline, args.command)(args, progress)
    except Timeout:
        progress("Another process is using this output directory. Wait for it to finish.")
        return 1
    except (PhrasecutError, OSError, ValueError) as exc:
        progress(f"Error: {exc}")
        return 1
    except KeyboardInterrupt:
        progress("Interrupted. Completed work is saved; rerun split with the same options and --resume.")
        return 130
