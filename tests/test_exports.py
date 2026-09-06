import zipfile

import pytest

from phrasecut.exports import export_audio, read_cuts_csv, verify_files
from phrasecut.jobs import sha256
from phrasecut.models import Cut, Phrase, PhrasecutError


def test_exports_actual_mp3_files_archive_and_detects_corruption(tone_source, tmp_path):
    output = tmp_path / "result"
    output.mkdir()
    phrases = [Phrase(1, "First tone."), Phrase(2, "Second tone.")]
    cuts = [Cut(1, 0.8, 2.2), Cut(2, 2.8, 4.7)]
    manifest = export_audio(tone_source, output, phrases, cuts, 6)
    assert len(manifest["clips"]) == 2
    assert verify_files(output)["errors"] == []
    with zipfile.ZipFile(output / "phrases.zip") as archive:
        assert "001.mp3" in archive.namelist()
        assert "phrases.csv" in archive.namelist()
        assert not any(".phrasecut" in n for n in archive.namelist())
    original = sha256(tone_source)
    (output / "001.mp3").write_bytes(b"corrupted")
    assert verify_files(output)["errors"]
    assert sha256(tone_source) == original


def test_invalid_intervals_never_export(tone_source, tmp_path):
    with pytest.raises(PhrasecutError):
        export_audio(tone_source, tmp_path, [Phrase(1, "Missing")], [Cut(1, None, None)], 6)
    assert not list(tmp_path.glob("*.mp3"))


def test_cuts_csv_requires_exact_ids_and_finite_ordered_times(tmp_path):
    path = tmp_path / "cuts.csv"
    path.write_text("id,start,end\n1,0.5,1\n2,2,3\n")
    assert read_cuts_csv(path, 2, 4)[1].start == 2
    for text in ["id,start,end\n1,0,1\n", "id,start,end\n1,0,3\n2,2,3\n", "id,start,end\n1,nan,1\n2,2,3\n"]:
        path.write_text(text)
        with pytest.raises(PhrasecutError):
            read_cuts_csv(path, 2, 4)
