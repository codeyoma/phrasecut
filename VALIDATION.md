# Validation — 2026-09-06

Phrasecut 0.1.0 was built and exercised on this Mac (Apple Silicon M4, 16 GB RAM), using Python 3.12.14, mlx-whisper 0.4.3, and `mlx-community/whisper-large-v3-turbo`.

## Checks completed

- **44 tests passed**, covering script formats, Japanese reading normalization, missing/repeated phrases, section announcements, targeted refinement, invalid/overlapping timestamps, interrupted recognition, changed inputs/options, corrupted caches/files, real MP3 encoding, ZIP contents, CLI entry points, editable cuts, and speech comparison.
- Ruff checks passed. Wheel and source distribution built successfully.
- Installed executable: `/opt/homebrew/bin/phrasecut` → `~/.local/share/phrasecut/venv/bin/phrasecut`.
- Verified `phrasecut --version`, `doctor`, a fresh installed-command recognition/export job, and `--resume` on that job. The fresh job automatically detected Spanish.

## DUO recording: 560 entries

The supplied recording is **3,413.2898 seconds** long. Its script was parsed as **560 entries**, keeping dialogues together and retaining Korean translations as metadata.

A fresh full-recording recognition pass processed **138 chunks**. During development, this exposed announcement-prefix matching and silence-spanning timestamp problems; the corresponding alignment logic was corrected. The final alignment/export acceptance job reused that fresh recognition JSON through `--transcript`, with explicit note omissions for `ON THE PHONE`, `IN A LETTER`, and `it`. Spoken parenthetical sentences remained included.

Results:

| Check | Result |
| --- | --- |
| Numbered MP3 exports | 560 / 560 |
| Missing/corrupt files or duration errors | 0 |
| Minimum decoded waveform correlation with source interval | 0.9999977429 |
| Largest start/end difference from the previously verified cut list | 0.000 seconds |
| First-pass transcript differences | 25 entries |
| Independent recognition of the exported MP3s | 527 transcript matches, 33 review entries |

The final MP3 acceptance export explicitly accepted 31 conservative boundary flags after comparing every interval with the earlier verified cut list. A separate run of the final targeted-refinement implementation reduced these to **6 flagged entries**, preserving every start/end timestamp and introducing no overlaps. Those six boundary flags are unrelated to any earlier count of grammatical corrections.

The speech verification pass recognized the actual exported MP3s in 132 cached batches, with no expected-script prompt. Its **33 review entries are possible ASR/script differences**, not 33 confirmed speech or grammar errors. Numbers written as digits versus words, orthography, and recognizer errors can all cause a review. Neither transcript matches nor high waveform correlation prove word-for-word agreement with the script; waveform correlation checks that the exported file contains the chosen source interval.

Acceptance artifacts were retained outside the source repository in a local `phrasecut-validation` directory:

- `phrasecut-validation/duo-final/phrases.zip`
- `phrasecut-validation/duo-final/verification.json`
- `phrasecut-validation/duo-final/speech-verification.json`
- `phrasecut-validation/duo-general-refinement.json`

The original source files and the earlier 560-phrase output were preserved. No source paths, phrase count, or previous cut times are embedded in the application code.

## Japanese and Spanish

Fresh, self-authored three-entry recordings were generated with the macOS `say` voices **Kyoko** and **Paulina**, with one-second pauses. These are synthetic acceptance fixtures, not an evaluation of arbitrary natural recordings.

| Recording | Export/integrity | Speech comparison | Minimum source correlation |
| --- | --- | --- | --- |
| Japanese, 10.5995 s | 3 / 3 passed; no boundary flags | 2 matches; 1 kana/kanji review with identical reading | 0.9999415606 |
| Spanish, 10.00075 s | 3 / 3 passed; no boundary flags | 3 / 3 matches | 0.9999018494 |
| Spanish through installed CLI, automatic language detection | Detected `es`; 3 / 3 passed; resume passed | First-pass text matched all three | — |

Japanese review example: script `駅まで歩いて行きましょう。`, recognizer `駅まで歩いていきましょう`. The original spelling was preserved and the report marked the readings as equivalent.

The Spanish fixture exposed a batch-verification bug where a word's approximate midpoint landed just before the clip boundary, inside inserted silence. A regression test now covers ownership across the gap; the corrected verification matches all three entries.

Artifacts are under `phrasecut-validation/ja`, `/es`, and `/es-installed-auto`. Other Whisper language codes are available, but have not been acceptance-tested here. Local recognition currently targets Apple Silicon macOS. Background music, continuously spoken material, mixed spoken languages, substantial script omissions, and reordered scripts remain situations where manual review can be necessary.
