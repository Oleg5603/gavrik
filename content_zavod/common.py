"""
Общие утилиты конвейера ContentZavod — переиспользуются всеми CLI-скриптами
Фаз 1-3 (strategist.py, idea_generator.py, scenarist.py, hook_master.py).

Вынесено из strategist.py при добавлении Фазы 2, чтобы retry+checkpoint
логика не дублировалась в каждом новом скрипте (CRITIQUE.md п.4).
"""
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Windows-консоль по умолчанию cp1251, а ответы модели/Markdown содержат
# символы вроде → — без этого print() падает с UnicodeEncodeError (та же
# болячка, что чинили в bot.py).
sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

CONTENT_ZAVOD_DIR = Path(__file__).parent
RETRY_DELAYS = [5, 15, 45]  # секунды между попытками (CRITIQUE.md п.4)

# Требования ВК по продвижению постов (проверено 2026-07-17, см. PLAN.md
# "Фаза 3 — Конвейер форматов" и источники в истории чата) — внедряется в
# промпты Генератора идей / Сценариста / Мастера хуков, чтобы контент
# изначально проектировался под алгоритм, а не подгонялся постфактум.
VK_PROMOTION_REQUIREMENTS = """=== Требования ВК по продвижению (актуально на 2026) ===
- Клипы/короткие вертикальные видео получают приоритетное продвижение —
  сильнее каруселей и текстовых постов. Если тема допускает видео-формат,
  явно предлагать его как основной вариант.
- Внешние ссылки в самом посте дают минус 50% охвата — если нужна ссылка,
  выносить её в комментарий, не в тело поста.
- Вовлечение важнее охвата: осмысленные комментарии и репосты весят
  больше лайков. Пост должен провоцировать не лайк, а комментарий —
  заканчивать открытым вопросом или явным приглашением высказать мнение,
  без дешёвого кликбейта ("а как думаете вы?" работает хуже конкретного
  вопроса по теме поста).
- Алгоритм считает время просмотра/дочитывания — текст должен быть
  построен так, чтобы хотелось нажать "показать полностью" (сильный крючок
  в первых 2-3 строках, до обрыва), а не искусственно растянут.
- Уникальность важнее: не дублировать чужой контент один в один, даже
  формат-референс адаптировать под голос клиента.
- Время публикации вторично по сравнению с качеством вовлечения — не
  нужно жёстко привязываться к "идеальному часу", важнее удержание
  внимания с первых секунд. Тем не менее для аудитории предпринимателей
  разумные окна — будни, 9:00-11:00 и 18:00-21:00 (рабочие паузы), не
  выходные дни."""


def call_claude(prompt: str) -> str:
    """Синхронный вызов claude --print — тот же паттерн, что и
    _run_claude_subprocess в handlers.py, но без asyncio (скрипты CLI).
    Без --permission-mode: задача чисто текстовая (генерация ответа по
    промпту), никаких файловых/bash-инструментов не требуется и не
    авторизовано для этих скриптов."""
    proc = subprocess.run(
        ["cmd", "/c", "claude", "--print"],
        input=prompt.encode("utf-8", errors="replace"),
        capture_output=True,
        timeout=600,
    )
    result = proc.stdout.decode("utf-8", errors="replace").strip()
    if not result:
        result = proc.stderr.decode("utf-8", errors="replace").strip()
    return result or "Модель не вернула ответ."


def ask_with_retry(prompt: str) -> str:
    """Retry с backoff (CRITIQUE.md п.4) — не полагаемся, что один вызов
    модели = один успех, особенно с учётом известных обрывов сети к
    api.anthropic.com (см. память project_net_monitor_dropouts)."""
    last_error = None
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            print(f"Попытка {attempt + 1}/{len(RETRY_DELAYS) + 1} — жду {delay}с после ошибки: {last_error}")
            time.sleep(delay)
        try:
            result = call_claude(prompt)
            if result and result != "Модель не вернула ответ.":
                return result
            last_error = "пустой ответ модели"
        except subprocess.TimeoutExpired:
            last_error = "таймаут 10 минут"
        except Exception as e:
            last_error = str(e)
    raise RuntimeError(f"Все {len(RETRY_DELAYS) + 1} попытки провалились: {last_error}")


def checkpoint(client: str, step: str, content: str, ext: str = "md") -> Path:
    """Промежуточное сохранение результата шага на диск (CRITIQUE.md п.4) —
    чтобы обрыв на следующем шаге конвейера не терял уже готовый результат."""
    drafts_dir = CONTENT_ZAVOD_DIR / "clients" / client / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    checkpoint_path = drafts_dir / f"{step}_{timestamp}.{ext}"
    checkpoint_path.write_text(content, encoding="utf-8")
    return checkpoint_path


def read_client_file(client: str, filename: str) -> str:
    path = CONTENT_ZAVOD_DIR / "clients" / client / filename
    if not path.exists():
        print(f"Не найден {path}")
        sys.exit(1)
    return path.read_text(encoding="utf-8")


def latest_step_output(client: str, step: str) -> Path | None:
    """Находит последний чекпойнт данного шага для резюмирования конвейера
    без пересчёта (см. PLAN.md 'Фаза 2-4 — надёжность конвейера')."""
    drafts_dir = CONTENT_ZAVOD_DIR / "clients" / client / "drafts"
    if not drafts_dir.exists():
        return None
    candidates = sorted(drafts_dir.glob(f"{step}_*.json"))
    return candidates[-1] if candidates else None


def save_json_checkpoint(client: str, step: str, data) -> Path:
    return checkpoint(client, step, json.dumps(data, ensure_ascii=False, indent=2), ext="json")


def ask_for_json_with_retry(prompt: str, max_json_retries: int = 2):
    """Как ask_with_retry, но дополнительно перезапускает вызов целиком,
    если ответ пришёл непустым, но не распарсился как JSON — потому что
    claude --print это полноценный агент, а не голая text-completion API:
    иногда он путает промпт с системным напоминанием/шаблоном или
    спотыкается о свой permission-классификатор и возвращает не-JSON текст
    вместо результата. Такой ответ технически 'успешен' (непустой), поэтому
    обычный ask_with_retry его не переспрашивает — это и есть тот самый
    случай 'один вызов ≠ один успех' из CRITIQUE.md."""
    last_result = None
    for attempt in range(max_json_retries + 1):
        result = ask_with_retry(prompt)
        try:
            return result, extract_json(result)
        except json.JSONDecodeError:
            last_result = result
            if attempt < max_json_retries:
                print(f"Ответ не распарсился как JSON (попытка {attempt + 1}/{max_json_retries + 1}), "
                      "перезапрашиваю...")
    return last_result, None


def extract_json(text: str):
    """Модель иногда оборачивает JSON в ```json ... ``` и добавляет
    преамбулу/постскриптум вопреки инструкции 'без markdown-обрамления' —
    вместо того чтобы полагаться на дисциплину промпта, вырезаем первый
    {...}-блок явно перед json.loads."""
    text = text.strip()
    if "```" in text:
        start = text.find("```")
        end = text.find("```", start + 3)
        if end != -1:
            block = text[start + 3:end]
            if block.startswith("json"):
                block = block[4:]
            text = block.strip()
    first = text.find("{")
    last = text.rfind("}")
    if first == -1 or last == -1:
        raise json.JSONDecodeError("Не найден JSON-блок в ответе", text, 0)
    return json.loads(text[first:last + 1])
