import numpy as np

from phrasecut.models import Cut, Phrase, Word
from phrasecut.refinement import best_local_words, refine


def test_local_matching_excludes_neighbor_tail_even_with_repeated_opening_article():
    phrase = Phrase(1, "A good idea.")
    words = [
        Word("A", 0, 0.1),
        Word("different", 0.2, 0.7),
        Word("sentence.", 0.8, 1.2),
        Word("A", 2, 2.1),
        Word("good", 2.2, 2.5),
        Word("idea.", 2.6, 3.0),
    ]
    chosen = best_local_words(phrase, words, "en")
    assert chosen[0].start == 2
    assert chosen[-1].end == 3


def test_local_refinement_recovers_an_unmatched_middle_phrase(tmp_path):
    phrases = [Phrase(1, "First."), Phrase(2, "A good idea."), Phrase(3, "Last.")]
    cuts = [
        Cut(1, 0.85, 2.22, coverage=1),
        Cut(2, None, None, issues=["unmatched"]),
        Cut(3, 5.85, 7.22, coverage=1),
    ]

    def recognizer(audio, language):
        # The refinement window starts at 1.22 seconds.
        return {
            "words": [
                {"word": "A", "start": 1.78, "end": 1.98},
                {"word": "good", "start": 2.08, "end": 2.38},
                {"word": "idea.", "start": 2.48, "end": 2.78},
            ]
        }

    result = refine(
        phrases, cuts, np.zeros(8 * 16000, dtype=np.float32), [(2, 3), (4, 6)], "en", 8, tmp_path, recognizer
    )
    assert result[1].start == 2.85
    assert result[1].end == 4.22
    assert not result[1].issues


def test_refinement_does_not_replace_valid_cut_with_an_overlapping_neighbor(tmp_path):
    phrases = [Phrase(1, "Earlier."), Phrase(2, "Hello."), Phrase(3, "Later.")]
    cuts = [
        Cut(1, 0.85, 2.22, coverage=1),
        Cut(2, 2.85, 4.22, coverage=1, issues=["start_shift"]),
        Cut(3, 5.85, 7.22, coverage=1),
    ]

    def recognizer(audio, language):
        return {"words": [{"word": "Hello.", "start": 0, "end": 0.78}]}

    result = refine(
        phrases,
        cuts,
        np.zeros(8 * 16000, dtype=np.float32),
        [(0.5, 1.4), (2, 3), (4, 6)],
        "en",
        8,
        tmp_path,
        recognizer,
    )
    assert result[1].start == cuts[1].start
    assert result[1].end == cuts[1].end
