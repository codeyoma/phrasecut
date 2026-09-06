import json

import pytest

from phrasecut.models import PhrasecutError
from phrasecut.scripts import parse_script


def write(tmp_path, text, name="script.txt"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_headings_do_not_consume_numbers(tmp_path):
    rows = parse_script(
        write(tmp_path, "## 朝\nおはようございます。\n今日は晴れです。\n\n## 夜\nおやすみ。"), "lines"
    )
    assert [(r.id, r.text, r.section) for r in rows] == [
        (1, "おはようございます。", "朝"),
        (2, "今日は晴れです。", "朝"),
        (3, "おやすみ。", "夜"),
    ]


def test_duo_keeps_dialogue_together_and_separates_translation(tmp_path):
    text = '## Section 1\n\n"Are you ready?"\n"Yes, let us go."\n"준비됐어?"\n"응, 가자."\n\n今日は晴れです。\n오늘은 맑습니다。'
    rows = parse_script(write(tmp_path, text))
    assert len(rows) == 2
    assert rows[0].text == '"Are you ready?" "Yes, let us go."'
    assert rows[0].translation == '"준비됐어?" "응, 가자."'
    assert rows[1].text == "今日は晴れです。"


def test_auto_rejects_ambiguous_multiline_paragraphs(tmp_path):
    p = write(tmp_path, "Hello.\nGoodbye.\n\nWelcome.\nSee you.")
    with pytest.raises(PhrasecutError, match="format"):
        parse_script(p)
    assert len(parse_script(p, "lines")) == 4
    assert len(parse_script(p, "paragraphs")) == 2


def test_csv_pairs_two_latin_languages_without_guessing(tmp_path):
    rows = parse_script(
        write(
            tmp_path,
            'text,translation,section\n"Hola, Ana.","Hello, Ana.",Uno\nAdiós.,Goodbye.,Uno',
            "script.csv",
        )
    )
    assert rows[0].text == "Hola, Ana."
    assert rows[0].translation == "Hello, Ana."


def test_json_accepts_text_and_rejects_empty_entries(tmp_path):
    p = write(
        tmp_path, json.dumps(["Hello.", {"text": "こんにちは。", "translation": "Hello."}]), "script.json"
    )
    assert len(parse_script(p)) == 2
    p.write_text('["Hello.", ""]')
    with pytest.raises(PhrasecutError, match="empty"):
        parse_script(p)


def test_count_mismatch_fails_before_audio_work(tmp_path):
    with pytest.raises(PhrasecutError, match="Expected 3"):
        parse_script(write(tmp_path, "One.\nTwo."), "lines", 3)


def test_duo_rejects_interleaved_target_translation(tmp_path):
    with pytest.raises(PhrasecutError, match="translation"):
        parse_script(write(tmp_path, "Hello.\n안녕.\nGoodbye.\n잘가."), "duo")


def test_duo_rejects_missing_translation(tmp_path):
    with pytest.raises(PhrasecutError, match="translation"):
        parse_script(write(tmp_path, "Hello."), "duo")
