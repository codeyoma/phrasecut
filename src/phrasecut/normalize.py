"""Keep comparison separate from the more forgiving alignment representation."""

import unicodedata
from functools import lru_cache

from rapidfuzz.distance import Levenshtein


def comparison_text(text):
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold() if c.isalnum())


@lru_cache(maxsize=1)
def japanese_converter():
    from fugashi import Tagger

    return Tagger()


@lru_cache(maxsize=32768)
def alignment_text(text, language):
    text = unicodedata.normalize("NFKC", text)
    if language == "ja":
        text = "".join((word.feature.kana or word.surface) for word in japanese_converter()(text))
        text = "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text)
    return comparison_text(text)


def differences(expected, recognized):
    a, b = comparison_text(expected), comparison_text(recognized)
    return [
        {
            "operation": op.tag,
            "script": a[op.src_start : op.src_end],
            "recognized": b[op.dest_start : op.dest_end],
        }
        for op in Levenshtein.opcodes(a, b)
        if op.tag != "equal"
    ]


def joined_words(words, language):
    separator = "" if language in ("ja", "zh", "th", "lo", "my") else " "
    return separator.join(w.text.strip() for w in words).strip()
