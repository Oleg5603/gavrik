"""
media.py — вложения (голос/фото/документы/видео) и обратные файлы от агента.

Реализует часть "16 фишек" из презентации jarvis-architect (см. память
reference_jarvis_install_server / курс aibasis.ru), которых у Гаврика не
было: расшифровка голосовых через Deepgram, чтение фото/PDF агентом,
отправка агентом файлов обратно через теги [ФАЙЛ: путь] и т.п.

Чистая логика (парсинг тегов, HTTP-запрос к Deepgram) вынесена сюда
отдельно от aiogram-хендлеров в handlers.py, чтобы её можно было
протестировать без поднятия бота.
"""
import re
from pathlib import Path

import aiohttp

from config import DEEPGRAM_API_KEY

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen?model=nova-2&language=ru"

# Теги, которые агент кладёт в текст ответа, чтобы бот прикрепил реальный
# файл вместо пути. Формат: [ТИП: /путь/к/файлу.ext]
FILE_TAG_PATTERN = re.compile(r"\[(ФАЙЛ|ФОТО|ВИДЕО|АУДИО|ГОЛОС|GIF):\s*([^\]]+?)\s*\]")

TAG_TO_METHOD = {
    "ФАЙЛ": "document",
    "ФОТО": "photo",
    "ВИДЕО": "video",
    "АУДИО": "audio",
    "ГОЛОС": "voice",
    "GIF": "animation",
}


class TranscriptionNotConfigured(Exception):
    """DEEPGRAM_API_KEY не задан — расшифровка недоступна."""


class TranscriptionError(Exception):
    pass


async def transcribe_voice(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """Отправляет аудио в Deepgram, возвращает распознанный текст.

    Поднимает TranscriptionNotConfigured, если ключ не задан — вызывающий
    код должен показать пользователю понятную инструкцию, а не голый
    стектрейс (ровно то, чего не хватало Гаврику раньше — раньше голосовые
    просто отклонялись фразой "не умею обрабатывать")."""
    if not DEEPGRAM_API_KEY:
        raise TranscriptionNotConfigured(
            "DEEPGRAM_API_KEY не задан в .env. Получить бесплатно (~770 часов): "
            "https://console.deepgram.com/api-keys → Create API Key → впишите "
            "в .env как DEEPGRAM_API_KEY=..."
        )

    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": mime_type,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(DEEPGRAM_URL, headers=headers, data=audio_bytes,
                                 timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise TranscriptionError(f"Deepgram вернул {resp.status}: {text[:300]}")
            data = await resp.json()

    try:
        transcript = (
            data["results"]["channels"][0]["alternatives"][0]["transcript"]
        )
    except (KeyError, IndexError) as e:
        raise TranscriptionError(f"Не удалось разобрать ответ Deepgram: {e}") from e

    if not transcript.strip():
        raise TranscriptionError("Deepgram не распознал речь (пустая расшифровка).")
    return transcript.strip()


def extract_file_tags(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Вырезает теги [ТИП: путь] из текста ответа агента.

    Возвращает (текст_без_тегов, список (aiogram_метод, путь)).
    Путь не проверяется на существование здесь — это забота вызывающего
    кода (файл мог не сохраниться, путь может быть неверным — тогда
    просто не получится отправить, и это надо явно сообщить пользователю,
    а не молча проглотить)."""
    files: list[tuple[str, str]] = []

    def _collect(m: re.Match) -> str:
        tag, path = m.group(1), m.group(2).strip()
        method = TAG_TO_METHOD.get(tag)
        if method:
            files.append((method, path))
        return ""

    cleaned = FILE_TAG_PATTERN.sub(_collect, text).strip()
    return cleaned, files


def resolve_existing_files(files: list[tuple[str, str]]) -> tuple[list[tuple[str, Path]], list[str]]:
    """Разделяет найденные теги на (существующие_файлы, отсутствующие_пути) —
    чтобы бот мог явно предупредить, если агент сослался на файл, которого
    на самом деле нет, вместо тихого игнорирования."""
    found: list[tuple[str, Path]] = []
    missing: list[str] = []
    for method, raw_path in files:
        path = Path(raw_path).expanduser()
        if path.exists() and path.is_file():
            found.append((method, path))
        else:
            missing.append(raw_path)
    return found, missing
