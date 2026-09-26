from pathlib import Path
import string
import tempfile

from i18n import STRINGS, tr
from engine import find_binary


def test_translation_keys():
    assert set(STRINGS["en"]) == set(STRINGS["ru"])
    for lang in ("en", "ru"):
        for key, value in STRINGS[lang].items():
            assert isinstance(value, str) and value.strip(), (lang, key)



def test_translation_placeholders_match():
    formatter = string.Formatter()
    for key in STRINGS["en"]:
        en_fields = {field for _, field, _, _ in formatter.parse(STRINGS["en"][key]) if field}
        ru_fields = {field for _, field, _, _ in formatter.parse(STRINGS["ru"][key]) if field}
        assert en_fields == ru_fields, (key, en_fields, ru_fields)


def test_default_english_examples():
    assert tr("en", "mode_single") == "Single"
    assert tr("en", "output_folder") == "Output folder"
    assert "12" in tr("en", "create_n_videos", count=12)


def test_russian_strings_preserved():
    assert tr("ru", "mode_single") == "Одиночное"
    assert tr("ru", "mode_multi") == "Мульти"
    assert tr("ru", "create_video") == "✦  СОЗДАТЬ ВИДЕО"
    assert tr("ru", "status_ready") == "Готово к работе"


def test_bundled_binary_priority():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        target = root / "ffmpeg" / "bin" / ("ffmpeg.exe" if __import__("os").name == "nt" else "ffmpeg")
        target.parent.mkdir(parents=True)
        target.write_bytes(b"stub")
        assert find_binary("ffmpeg", root) == str(target)


if __name__ == "__main__":
    test_translation_keys()
    test_translation_placeholders_match()
    test_default_english_examples()
    test_russian_strings_preserved()
    test_bundled_binary_priority()
    print("i18n/bundle tests: OK")
