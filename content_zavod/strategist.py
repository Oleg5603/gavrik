"""
Стратег (Фаза 1, ContentZavod) — CLI-скрипт, не часть бота (см. PLAN.md/
CRITIQUE.md п.2: ContentZavod не трогает handlers.py, пока конвейер не
докажет себя вручную).

Читает clients/<client>/brand.md, вызывает модель через claude --print
(с retry+backoff и промежуточным сохранением — CRITIQUE.md п.4),
сохраняет clients/<client>/strategy.md для ручной проверки Олегом.

Использование:
    python content_zavod/strategist.py oleg
"""
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

SYSTEM_PROMPT = """Ты — Стратег в конвейере контента ("распаковщик" из
методологии, см. SOURCE.md). Твоя единственная задача: превратить бренд/
продукт/боли аудитории клиента в контент-стратегию.

На вход — файл brand.md с описанием: кто клиент, тема контента, аудитория,
её боли, тон, запрещённые темы, частота публикации.

Выдай контент-стратегию строго в следующей структуре (Markdown):

# Стратегия контента — <имя клиента>

## Рубрики (5-7 штук)
Для каждой рубрики: название + одно предложение о том, какие посты в неё
попадают и зачем она нужна для этой аудитории/боли.

## Тональность
Конкретное описание голоса (не общие слова вроде "дружелюбный" — с
примером фразы/оборота, характерного для этого тона).

## Упаковка эксперта
Как подавать личность клиента через контент, чтобы боль аудитории
резонировала с его позицией (в 3-5 предложениях).

## Запрещённые темы и ограничения
Явный список (возьми из brand.md, ничего не выдумывай сверх него).

## Первые 2 недели — примерный микс рубрик
Как распределить 3+ поста/неделю по рубрикам в первые 2 недели, чтобы
можно было измерить критерий успеха MVP (рост охвата).

Не придумывай факты о клиенте, которых нет в brand.md — если чего-то не
хватает, явно напиши "уточнить у клиента" вместо выдумки. Это чистая
задача на преобразование текста — не читай и не изменяй никакие файлы.
Ответь СРАЗУ готовым Markdown-текстом стратегии, начиная с заголовка
"# Стратегия контента" — без вступительных фраз о том, что ты собираешься
делать."""


def _read_brand(client: str) -> str:
    brand_path = CONTENT_ZAVOD_DIR / "clients" / client / "brand.md"
    if not brand_path.exists():
        print(f"Не найден {brand_path}")
        sys.exit(1)
    return brand_path.read_text(encoding="utf-8")


def _call_claude(prompt: str) -> str:
    """Синхронный вызов claude --print — тот же паттерн, что и
    _run_claude_subprocess в handlers.py, но без asyncio (скрипт CLI).
    Без --permission-mode: задача чисто текстовая (генерация ответа по
    промпту), никаких файловых/bash-инструментов не требуется и не
    авторизовано для этого скрипта."""
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


def _ask_with_retry(prompt: str) -> str:
    """Retry с backoff (CRITIQUE.md п.4) — не полагаемся, что один вызов
    модели = один успех, особенно с учётом известных обрывов сети к
    api.anthropic.com (см. память project_net_monitor_dropouts)."""
    last_error = None
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            print(f"Попытка {attempt + 1}/{len(RETRY_DELAYS) + 1} — жду {delay}с после ошибки: {last_error}")
            time.sleep(delay)
        try:
            result = _call_claude(prompt)
            if result and result != "Модель не вернула ответ.":
                return result
            last_error = "пустой ответ модели"
        except subprocess.TimeoutExpired:
            last_error = "таймаут 10 минут"
        except Exception as e:
            last_error = str(e)
    raise RuntimeError(f"Все {len(RETRY_DELAYS) + 1} попытки провалились: {last_error}")


def _checkpoint_raw(client: str, raw_result: str) -> Path:
    """Промежуточное сохранение сырого ответа модели на диск (CRITIQUE.md
    п.4) — чтобы результат не терялся, даже если что-то упадёт до записи
    финального strategy.md."""
    drafts_dir = CONTENT_ZAVOD_DIR / "clients" / client / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    checkpoint_path = drafts_dir / f"strategy_raw_{timestamp}.md"
    checkpoint_path.write_text(raw_result, encoding="utf-8")
    return checkpoint_path


def main():
    if len(sys.argv) != 2:
        print("Использование: python content_zavod/strategist.py <client>")
        sys.exit(1)
    client = sys.argv[1]

    brand = _read_brand(client)
    prompt = f"{SYSTEM_PROMPT}\n\n=== brand.md клиента «{client}» ===\n{brand}"

    print(f"Стратег: вызываю модель для клиента «{client}»...")
    result = _ask_with_retry(prompt)

    checkpoint_path = _checkpoint_raw(client, result)
    print(f"Промежуточный результат сохранён: {checkpoint_path}")

    strategy_path = CONTENT_ZAVOD_DIR / "clients" / client / "strategy.md"
    strategy_path.write_text(result, encoding="utf-8")
    print(f"Готово: {strategy_path}")
    print("\n--- Проверьте перед тем, как переходить к Фазе 2 (Генератор идей) ---\n")
    print(result)


if __name__ == "__main__":
    main()
