"""
Генератор идей (Фаза 2, ContentZavod) — CLI-скрипт.

Читает strategy.md клиента, выдаёт 5-7 тем на неделю (без повторов с уже
использованными — учитывает историю из drafts/ideas_history.json).
Каждая тема помечена рубрикой и рекомендуемым форматом (клип/карусель/
текст) с учётом требований ВК по продвижению.

Использование:
    python content_zavod/idea_generator.py oleg
"""
import json
import sys

from common import (
    CONTENT_ZAVOD_DIR, VK_PROMOTION_REQUIREMENTS,
    ask_for_json_with_retry, checkpoint, read_client_file,
)

SYSTEM_PROMPT = """Ты — Генератор идей в конвейере контента. Твоя задача:
по контент-стратегии клиента выдать 5-7 конкретных тем постов на неделю.

На вход — strategy.md (рубрики, тон, упаковка эксперта) и список уже
использованных тем (если есть — не повторяться).

{vk_requirements}

Для каждой темы укажи:
1. Формулировка темы (конкретная, не абстрактная — не "про пользу ИИ",
   а например "как я делегировал ИИ-агенту задачу, которую раньше делал
   сам разработчик за 3 дня")
2. Рубрика из strategy.md, к которой относится тема
3. Рекомендуемый формат с учётом требований ВК (клип/карусель/текстовый
   пост) — и почему именно этот формат подходит теме
4. Одно предложение, почему эта тема цепляет именно боль аудитории

Ответ — строго в JSON (без markdown-обрамления, без вступительных фраз):
{{
  "week_topics": [
    {{"topic": "...", "rubric": "...", "format": "клип|карусель|текст", "why_hooks_pain": "..."}}
  ]
}}

Не придумывай фактов о клиенте сверх того, что есть в strategy.md.
Ответь СРАЗУ JSON-объектом, без markdown-обрамления (без ```), без
вступительных фраз и без комментариев после JSON."""


def main():
    if len(sys.argv) != 2:
        print("Использование: python content_zavod/idea_generator.py <client>")
        sys.exit(1)
    client = sys.argv[1]

    strategy = read_client_file(client, "strategy.md")

    # Не в drafts/ — иначе имя совпадает с маской ideas_*.json, которую
    # latest_step_output использует для поиска последнего чекпойнта тем.
    history_path = CONTENT_ZAVOD_DIR / "clients" / client / "topics_history.json"
    used_topics = []
    if history_path.exists():
        used_topics = json.loads(history_path.read_text(encoding="utf-8"))

    prompt = (
        SYSTEM_PROMPT.format(vk_requirements=VK_PROMOTION_REQUIREMENTS)
        + f"\n\n=== strategy.md клиента «{client}» ===\n{strategy}"
        + f"\n\n=== Уже использованные темы (не повторять) ===\n{json.dumps(used_topics, ensure_ascii=False)}"
    )

    print(f"Генератор идей: вызываю модель для клиента «{client}»...")
    result, parsed = ask_for_json_with_retry(prompt)

    checkpoint_path = checkpoint(client, "ideas_raw", result)
    print(f"Промежуточный результат сохранён: {checkpoint_path}")

    if parsed is None:
        print("⚠ Модель не вернула валидный JSON после повторных попыток — сырой ответ "
              "сохранён в чекпойнте, исправьте вручную или перезапустите.")
        sys.exit(1)

    ideas_path = checkpoint(client, "ideas", json.dumps(parsed, ensure_ascii=False, indent=2), ext="json")
    print(f"Готово: {ideas_path}")

    # Обновляем историю тем, чтобы следующий запуск не повторялся
    used_topics.extend(t["topic"] for t in parsed.get("week_topics", []))
    history_path.write_text(json.dumps(used_topics, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n--- Темы недели ---\n")
    for i, t in enumerate(parsed.get("week_topics", []), 1):
        print(f"{i}. [{t.get('rubric')}] {t.get('topic')} — формат: {t.get('format')}")
        print(f"   Почему цепляет: {t.get('why_hooks_pain')}\n")


if __name__ == "__main__":
    main()
