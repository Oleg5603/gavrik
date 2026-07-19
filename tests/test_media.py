import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

import media


def test_extract_file_tags_no_tags():
    text, files = media.extract_file_tags("Просто обычный ответ без вложений.")
    assert text == "Просто обычный ответ без вложений."
    assert files == []


def test_extract_file_tags_single_file():
    text, files = media.extract_file_tags(
        "Готово! [ФАЙЛ: /home/agent/workspace/.media/report.html]"
    )
    assert text == "Готово!"
    assert files == [("document", "/home/agent/workspace/.media/report.html")]


def test_extract_file_tags_multiple_mixed():
    raw = (
        "Сделал карусель.\n"
        "[ФОТО: /tmp/slide1.png]\n"
        "[ФОТО: /tmp/slide2.png]\n"
        "Ещё голосовое: [ГОЛОС: /tmp/reply.ogg]\n"
        "И гифка [GIF: /tmp/anim.gif] тоже готова."
    )
    text, files = media.extract_file_tags(raw)
    assert "[ФОТО" not in text
    assert "[ГОЛОС" not in text
    assert "[GIF" not in text
    assert files == [
        ("photo", "/tmp/slide1.png"),
        ("photo", "/tmp/slide2.png"),
        ("voice", "/tmp/reply.ogg"),
        ("animation", "/tmp/anim.gif"),
    ]


def test_extract_file_tags_unknown_tag_ignored():
    text, files = media.extract_file_tags("Текст [НЕИЗВЕСТНО: /tmp/x] дальше")
    # Тег не из словаря TAG_TO_METHOD — не распознаётся регуляркой вовсе,
    # остаётся как обычный текст (осознанное решение: лучше показать
    # пользователю странный текст, чем тихо потерять кусок ответа).
    assert "[НЕИЗВЕСТНО" in text
    assert files == []


def test_resolve_existing_files_splits_found_and_missing(tmp_path):
    real_file = tmp_path / "exists.txt"
    real_file.write_text("hi", encoding="utf-8")

    files = [("document", str(real_file)), ("photo", str(tmp_path / "missing.png"))]
    found, missing = media.resolve_existing_files(files)

    assert len(found) == 1
    assert found[0][0] == "document"
    assert found[0][1] == real_file
    assert missing == [str(tmp_path / "missing.png")]


def test_resolve_existing_files_rejects_directories(tmp_path):
    subdir = tmp_path / "adir"
    subdir.mkdir()
    found, missing = media.resolve_existing_files([("document", str(subdir))])
    assert found == []
    assert missing == [str(subdir)]


def test_transcribe_voice_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(media, "DEEPGRAM_API_KEY", "")
    with pytest.raises(media.TranscriptionNotConfigured):
        asyncio.run(media.transcribe_voice(b"fake audio bytes"))
