import json

from phrasecut.cli import main


def test_cli_preview_split_resume_verify_and_csv_export(tone_source, tmp_path, capsys):
    script = tmp_path / "script.txt"
    script.write_text("First tone.\nSecond tone.\n")
    transcript = tmp_path / "words.json"
    transcript.write_text(
        json.dumps(
            {
                "language": "en",
                "words": [
                    {"word": "First", "start": 1.0, "end": 1.4},
                    {"word": "tone.", "start": 1.5, "end": 2.0},
                    {"word": "Second", "start": 3.0, "end": 3.5},
                    {"word": "tone.", "start": 3.6, "end": 4.5},
                ],
            }
        )
    )
    output = tmp_path / "out"
    assert main(["preview", str(script), "--expect", "2"]) == 0
    args = [
        "split",
        str(tone_source),
        str(script),
        "-o",
        str(output),
        "--language",
        "en",
        "--transcript",
        str(transcript),
        "--expect",
        "2",
    ]
    assert main(args) == 0
    assert main(args + ["--resume"]) == 0
    assert main(["verify", str(output)]) == 0
    assert main(["export", str(output), "--cuts", str(output / "cuts.csv")]) == 0
    script.write_text("Changed first.\nChanged second.\n")
    assert main(args + ["--resume"]) == 1
    assert "changed" in capsys.readouterr().err.lower()


def test_unmatched_phrase_stops_for_review_without_fabricated_mp3(tone_source, tmp_path):
    script = tmp_path / "script.txt"
    script.write_text("Quantum giraffes.\n")
    transcript = tmp_path / "words.json"
    transcript.write_text(json.dumps({"language": "en", "words": [{"word": "Hello", "start": 1, "end": 2}]}))
    output = tmp_path / "out"
    assert (
        main(
            [
                "split",
                str(tone_source),
                str(script),
                "-o",
                str(output),
                "--language",
                "en",
                "--transcript",
                str(transcript),
                "--accept-review",
            ]
        )
        == 2
    )
    assert (output / "cuts.csv").exists()
    assert not list(output.glob("*.mp3"))


def test_selected_notes_can_be_omitted_without_dropping_spoken_parentheses():
    from phrasecut.models import Phrase
    from phrasecut.pipeline import spoken_phrases

    phrases = [Phrase(1, "Hello. (ON THE PHONE)"), Phrase(2, "Fill in the form. (Please print clearly.)")]
    spoken = spoken_phrases(phrases, False, ["ON THE PHONE"])
    assert spoken[0].text == "Hello."
    assert spoken[1].text == phrases[1].text
    assert phrases[0].text.endswith("(ON THE PHONE)")


def test_module_entrypoint_help_and_version_run_in_a_subprocess():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "phrasecut", "--help"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    assert "split" in result.stdout and "verify" in result.stdout
    result = subprocess.run(
        [sys.executable, "-m", "phrasecut", "--version"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0 and result.stdout.startswith("phrasecut ")


def test_corrupted_recognition_cache_is_rejected_before_reuse(tone_source, tmp_path):
    import pytest

    from phrasecut.jobs import create_job
    from phrasecut.models import PhrasecutError
    from phrasecut.pipeline import source_cache

    script = tmp_path / "script.txt"
    script.write_text("Hello.")
    output = tmp_path / "out"
    job = create_job(output, tone_source, script, {})
    source_cache(output, job, lambda message: None)
    path = output / ".phrasecut/audio16k.f32"
    data = bytearray(path.read_bytes())
    data[0:4] = b"abcd"
    path.write_bytes(data)
    with pytest.raises(PhrasecutError, match="cache changed"):
        source_cache(output, job, lambda message: None)
