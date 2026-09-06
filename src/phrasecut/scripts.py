"""Explicit script structure; source text is data, never instructions."""

import csv
import io
import json
import re
from pathlib import Path

from .models import Phrase, PhrasecutError

FORMATS = ("auto", "lines", "paragraphs", "duo", "csv", "json")
HANGUL = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")
HEADING = re.compile(r"^#{1,6}\s+(.+)$")


def blocks(text):
    section, pending = "", []
    for raw in [*text.splitlines(), ""]:
        line = raw.strip()
        heading = HEADING.match(line)
        if not line or heading:
            if pending:
                yield section, pending
                pending = []
            if heading:
                section = heading[1].strip()
        else:
            pending.append(line)


def duo_pair(lines):
    target, translation = [], []
    for line in lines:
        if HANGUL.search(line):
            translation.append(line)
        elif translation:
            raise PhrasecutError("Target text follows Korean translation; add a blank line or use CSV/JSON.")
        else:
            target.append(line)
    if not target or not translation:
        raise PhrasecutError("Each DUO paragraph needs target text followed by Korean translation.")
    return " ".join(target), " ".join(translation)


def parse_script(path, format="auto", expected_count=None):
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PhrasecutError("Save the script as UTF-8 text, CSV, or JSON.") from exc
    if format not in FORMATS:
        raise PhrasecutError(f"Unknown script format: {format}")
    if format == "auto" and path.suffix.lower() in (".csv", ".json"):
        format = path.suffix.lower()[1:]
    parsed = []
    if format in ("csv", "json"):
        try:
            records = list(csv.DictReader(io.StringIO(text))) if format == "csv" else json.loads(text)
        except (ValueError, csv.Error) as exc:
            raise PhrasecutError(f"Invalid {format.upper()}: {exc}") from exc
        if not isinstance(records, list):
            raise PhrasecutError("JSON must be an array of strings or objects with a text field.")
        for row in records:
            if isinstance(row, str):
                parsed.append((row, "", ""))
            elif isinstance(row, dict):
                target = row.get("text", row.get("english", row.get("target")))
                translation = row.get("translation", row.get("korean", ""))
                section = row.get("section", "")
                if not isinstance(target, str) or not isinstance(translation, str):
                    raise PhrasecutError(
                        "Every entry needs a text column/field; translations must be strings."
                    )
                parsed.append((target, translation, str(section)))
            else:
                raise PhrasecutError("Script entries must be strings or objects with a text field.")
    else:
        groups = list(blocks(text))
        if format == "auto":
            if any(len(lines) > 1 for _, lines in groups):
                try:
                    for _, lines in groups:
                        duo_pair(lines)
                    format = "duo"
                except PhrasecutError:
                    # Plain consecutive lines with no paragraph separators have an unambiguous line mode.
                    if len(groups) == 1 or not re.search(r"\n\s*\n", text.strip()):
                        format = "lines"
                    else:
                        raise PhrasecutError(
                            "Ambiguous multiline script: choose --format lines or --format paragraphs."
                        ) from None
            else:
                format = "lines"
        for section, lines in groups:
            if format == "lines":
                parsed.extend((line, "", section) for line in lines)
            elif format == "paragraphs":
                parsed.append((" ".join(lines), "", section))
            else:
                target, translation = duo_pair(lines)
                parsed.append((target, translation, section))
    phrases = []
    for target, translation, section in parsed:
        if not target.strip() or not any(c.isalnum() for c in target):
            raise PhrasecutError(f"Entry {len(phrases) + 1} has empty or non-spoken text.")
        phrases.append(Phrase(len(phrases) + 1, target.strip(), translation.strip(), section))
    if not phrases:
        raise PhrasecutError("The script contains no phrases.")
    if expected_count is not None and len(phrases) != expected_count:
        raise PhrasecutError(f"Expected {expected_count} phrases; parsed {len(phrases)}. Check --format.")
    return phrases
