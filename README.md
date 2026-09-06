# Phrasecut

Turn one recording and its script into one numbered MP3 per script entry. Runs locally on an Apple Silicon Mac. A script entry can contain a sentence, several sentences, or a complete dialogue.

```bash
phrasecut preview script.txt --expect 560
phrasecut split recording.mp3 script.txt --language en --expect 560 --output ./my-phrases
phrasecut verify ./my-phrases --speech
```

The output contains `001.mp3`, `002.mp3`, …, plus a ZIP, playlist, editable timestamps, and review reports. Original audio and script files are preserved. There is no fixed sentence count.

## Install

Requires Python 3.11+ and macOS on Apple Silicon for local recognition. Python 3.12 was used for validation. Clone the repository and install:

```bash
git clone https://github.com/codeyoma/phrasecut.git
cd phrasecut
./install.sh
export PATH="$HOME/.local/bin:$PATH"
phrasecut doctor
```

The installer creates a dedicated environment under `~/.local/share/phrasecut`. To choose Python, set `PHRASECUT_PYTHON=/path/to/python3`. To choose the command directory, set `PHRASECUT_BIN_DIR`. Rerunning the installer updates the installed copy. Development source changes take effect after reinstalling.

FFmpeg is supplied by the Python dependency; no separate FFmpeg installation is needed. The first recognition run downloads the selected model to `~/.cache/phrasecut/models` (or `HF_HOME`, if set). Audio and scripts are processed locally. An internet connection is needed for the initial package/model downloads, not for cached recognition. Model storage and recognition speed depend on the model and recording length.

## Choose the script structure

Always run `preview` first. `--expect` catches accidental translations, headings, or merged entries.

| Format | Each exported MP3 corresponds to |
| --- | --- |
| `--format lines` | One nonempty line; Markdown headings are skipped |
| `--format paragraphs` | One blank-line-separated paragraph; wrapped lines are joined |
| `--format duo` | One paragraph of target-language lines followed by Korean translation lines |
| `--format csv` | One row with `text`; optional `translation` and `section` |
| `--format json` | One string/object in an array; objects use `text`, optional `translation` and `section` |
| `--format auto` | File extension, clear DUO blocks, or individual lines; ambiguous multiline blocks are rejected |

Save files as UTF-8. Use CSV/JSON for arbitrary bilingual pairs or mixed-language scripts. The DUO parser requires a non-Korean target followed by Korean translations; it does not infer arbitrary translation languages. The `english`/`korean` JSON fields are also accepted for existing lesson data. Numbering written inside a text entry is treated as spoken text; use Markdown headings for section labels.

```bash
# The supplied DUO style: English/dialogue followed by Korean translation.
phrasecut preview duo-script.txt --format duo --expect 560
phrasecut split duo.mp3 duo-script.txt --format duo --language en \
  --expect 560 --omit-note "ON THE PHONE" --omit-note "IN A LETTER" \
  --omit-note "it" --output ./duo-phrases

# Japanese, one entry per line.
phrasecut split japanese.mp3 japanese.txt --format lines --language ja --output ./japanese-phrases

# Spanish with translation columns.
phrasecut split spanish.m4a bilingual.csv --language es --output ./spanish-phrases

# All parsed entries, useful for checking a large script.
phrasecut preview script.txt --json
phrasecut languages
```

`--omit-note "ON THE PHONE"` excludes only that exact parenthesized note. Repeat the option for other notes. This is preferable when some parenthetical sentences are spoken.

`--ignore-parentheticals` explicitly excludes `(notes)` and `（notes）` from alignment and speech comparison while preserving the original text in the output. Do not enable it if parentheses contain words actually spoken. Japanese alignment uses readings to tolerate kana/kanji spelling differences. The review report still shows the original spelling.

Choose the language spoken in the recording with `--language en`, `ja`, `es`, `ko`, etc. The default is `auto`; specify a language for more predictable results. Recognition uses transcription rather than translation. A single language setting works best for one spoken language; mixed-language recordings may need manual review.

## Review and adjust boundaries

Recognition runs in short chunks, then aligns the script in order and looks for nearby pauses. Uncertain boundaries are rechecked in a shorter audio window. If any remain, the command saves its work and exits with status **2**:

```bash
# Read review.md and listen to the source at the indicated times.
# Edit only start/end in cuts.csv (seconds from the source's beginning).
phrasecut export ./my-phrases --cuts ./my-phrases/cuts.csv
phrasecut verify ./my-phrases --speech
```

Keep every row and its ID in order. Cuts must be finite, within the recording, and nonoverlapping. A missing phrase has empty timestamps; Phrasecut never invents evenly spaced cuts. Supply actual times for missing entries before export.

To explicitly export valid but uncertain estimates, use `--accept-review` with `split` or `export`. This never overrides missing, overlapping, or invalid intervals. Edited boundaries are recorded as manually edited and unverified until you check them. Wording differences alone do not prevent export when the boundaries are sound.

Default padding is 0.15 seconds before speech and 0.22 seconds after speech. Change it with `--padding-before` and `--padding-after` (0–2 seconds). Continuous speech without pauses, background music, repeated or omitted phrases, and inaccurate scripts can require boundary edits. Strongly different or reordered scripts are not guaranteed to align.

## Resume a job

Rerun the exact `split` command with `--resume`. Completed recognition chunks and MP3 exports are reused. The audio, script, model, language, parsing settings, and padding must match the original run. Changed inputs require a new output directory. Ctrl-C saves completed chunks.

```bash
phrasecut split recording.mp3 script.txt --language en \
  --output ./my-phrases --resume
```

Use `export` to apply boundary edits to an existing job. The `.phrasecut` folder contains the source PCM cache and recognition checkpoints; keep it if you want to resume, edit, or verify. It can use more disk space than the compressed recording. The ZIP excludes this working cache.

## Verify the outputs

`split` and `export` automatically decode every MP3 and check its duration, checksum, and waveform against the corresponding source interval. Run these again with:

```bash
phrasecut verify ./my-phrases
phrasecut verify ./my-phrases --speech

# Optional second model for another recognition opinion.
phrasecut verify ./my-phrases --speech --model mlx-community/whisper-large-v3-mlx
```

Speech verification reads the actual exported MP3s without using the expected script as a prompt. It caches completed batches by audio hashes and model. Case and punctuation are ignored; wording and spelling differences are reported without a loose “similar enough” threshold. A transcript match is automated evidence, **not a guarantee of verbatim audio**. Alternate Japanese spellings may be marked for review even when the readings match. Listen to flagged clips before changing the script.

| File | Contents |
| --- | --- |
| `001.mp3`, … | 192 kbps MP3, original sample rate; mono/stereo retained, larger channel layouts downmixed to stereo |
| `phrases.zip` | MP3s and portable reports |
| `playlist.m3u8` | Clips in script order |
| `cuts.csv` | Editable `id,start,end` plus script context |
| `phrases.csv`, `phrases.json` | Original text, translations, section, times, recognition and review flags |
| `manifest.json` | Exported file names and checksums |
| `review.md`, `review.json` | Alignment/boundary issues and first-pass transcript differences |
| `verification.json` | File integrity, decoded duration and source waveform checks |
| `speech-verification.json` | Optional second-pass recognition and text differences |

Exit status: `0` completed; `1` processing/integrity error; `2` review needed (also argparse usage errors); `130` interrupted. A successful export can still have wording differences in `review.md`.

## Bring existing word timestamps

Recognition can be skipped with `--transcript words.json`. This also permits export-only use on machines without MLX. The JSON must contain `language` and either a `words` array or Whisper `segments[].words`, with real `word`, `start`, `end` values. An optional `audio_sha256` is checked against the recording. Plain text or segment-only timestamps are insufficient. The transcript must use the same recording and time origin.

```json
{"language":"en","words":[{"word":"Hello.","start":1.0,"end":1.8}]}
```

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[asr,dev]'
.venv/bin/python -m pytest tests
.venv/bin/ruff check .
.venv/bin/python -m build .
```

See [VALIDATION.md](VALIDATION.md) for the actual acceptance results and limitations. Recognition uses [MLX Whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) and [Whisper multilingual models](https://github.com/openai/whisper).
