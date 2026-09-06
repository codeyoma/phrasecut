import pytest

from phrasecut.alignment import align, validate_cuts
from phrasecut.models import Cut, Phrase, PhrasecutError, Word


def test_intro_is_excluded_and_dialogue_is_one_clip():
    phrases = [Phrase(1, "Hello there. Are you ready?"), Phrase(2, "Yes, let us go.")]
    words = [
        Word("Section", 0.3, 0.7),
        Word("one", 0.7, 1),
        Word("Hello", 2, 2.4),
        Word("there.", 2.4, 2.8),
        Word("Are", 3.4, 3.6),
        Word("you", 3.6, 3.8),
        Word("ready?", 3.8, 4.2),
        Word("Yes,", 5.5, 5.8),
        Word("let", 5.8, 6),
        Word("us", 6, 6.2),
        Word("go.", 6.2, 6.5),
    ]
    cuts = align(phrases, words, [(0, 0.3), (1, 2), (2.8, 3.4), (4.2, 5.5), (6.5, 7)], "en", 7)
    assert cuts[0].start == pytest.approx(1.85)
    assert cuts[0].end == pytest.approx(4.42)
    assert cuts[1].start == pytest.approx(5.35)
    assert not cuts[0].issues


def test_missing_phrase_never_gets_fabricated_timestamps():
    rows = [Phrase(1, "Hello there"), Phrase(2, "Quantum giraffes juggle"), Phrase(3, "Good night")]
    words = [Word("Hello", 1, 1.4), Word("there", 1.4, 2), Word("Good", 4, 4.4), Word("night", 4.4, 5)]
    cuts = align(rows, words, [(0, 1), (2, 4), (5, 6)], "en", 6)
    assert cuts[1].start is None and cuts[1].end is None
    assert "unmatched" in cuts[1].issues


def test_japanese_without_spaces_and_kana_script_align():
    rows = [Phrase(1, "きょうは晴れです。"), Phrase(2, "ありがとうございます。")]
    words = [Word("今日は", 1, 1.6), Word("晴れです。", 1.6, 2.4), Word("ありがとうございます。", 4, 5.2)]
    cuts = align(rows, words, [(0, 1), (2.4, 4), (5.2, 6)], "ja", 6)
    assert cuts[0].coverage == pytest.approx(1)
    assert cuts[0].start == pytest.approx(0.85)
    assert cuts[1].start == pytest.approx(3.85)


def test_repeated_identical_entries_remain_in_order():
    cuts = align(
        [Phrase(1, "Hello"), Phrase(2, "Hello")],
        [Word("Hello", 1, 2), Word("Hello", 4, 5)],
        [(0, 1), (2, 4), (5, 6)],
        "en",
        6,
    )
    assert cuts[0].end < cuts[1].start


def test_wording_difference_is_not_silently_accepted_as_exact():
    cuts = align(
        [Phrase(1, "He bites his nail.")],
        [Word("He", 1, 1.2), Word("bites", 1.2, 1.6), Word("his", 1.6, 1.8), Word("nails.", 1.8, 2.2)],
        [(0, 1), (2.2, 3)],
        "en",
        3,
    )
    assert cuts[0].differences
    assert cuts[0].start is not None


@pytest.mark.parametrize(
    "cuts",
    [
        [Cut(1, 1, 3), Cut(2, 2, 4)],
        [Cut(1, float("nan"), 2)],
        [Cut(1, None, None)],
        [Cut(1, -1, 2)],
        [Cut(1, 1, 8)],
    ],
)
def test_export_rejects_invalid_or_overlapping_intervals(cuts):
    with pytest.raises(PhrasecutError):
        validate_cuts(cuts, 6)


def test_section_announcement_cannot_steal_matching_characters_from_phrase():
    # The global character alignment can map "I" to the i in "Section".
    phrases = [Phrase(1, "I begged Richie to lend me money.")]
    words = [
        Word("Section", 0, 1),
        Word("three.", 1, 1.4),
        Word("I", 3, 3.2),
        Word("begged", 3.2, 3.6),
        Word("Richie", 3.6, 4),
        Word("to", 4, 4.1),
        Word("lend", 4.1, 4.5),
        Word("me", 4.5, 4.7),
        Word("money.", 4.7, 5),
    ]
    cuts = align(phrases, words, [(1.4, 3), (5, 6)], "en", 6)
    assert cuts[0].start == pytest.approx(2.85)
    assert cuts[0].recognized == "I begged Richie to lend me money."
