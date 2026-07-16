"""
Сценарист (Фаза 2, ContentZavod) — CLI-скрипт.

Читает последний чекпойнт ideas_*.json (или конкретный файл через
--ideas-file), строит структуру сценария (проблема → инсайт → вывод/
призыв) под каждую тему недели, с учётом формата и требований ВК.

Использование:
    python content_zavod/scenarist.py oleg
    python content_zavod/scenarist.py oleg --ideas-file drafts/ideas_20260717_120000.json
"""
import json
import sys

from common import VK_PROMOTION_REQUIREMENTS, ask_for_json_with_retry, checkpoint, latest_step_output, read_client_file

SYSTEM_PROMPT = """Ты — Сценарист в конвейере контента. На вход — одна тема
поста (с рубрикой, форматом, тем, какую боль аудитории она закрывает) и
контент-стратегия клиента (тон, упаковка эксперта).

{vk_requirements}

Построй структуру сценария по схеме: проблема → инсайт → вывод/призыв.
Это СТРУКТУРА, не финальный текст поста — конкретные формулировки будут
на следующем шаге (Конвейер форматов).

Учитывай рекомендованный формат темы:
- Если формат "клип" — структура должна работать под короткое вертикальное
  видео: первые 2-3 секунды = проблема максимально ёмко, инсайт — визуально
  показываемый факт/демонстрация, призыв — короткий и прямой.
- Если формат "карусель" — структура должна делиться на слайды (проблема
  на первом слайде-обложке, инсайт разворачивается по слайдам, призыв на
  последнем).
- Если формат "текст" — структура держит крючок в первых 2-3 строках
  (до обрыва "показать полностью").

Ответ строго в JSON (без markdown-обрамления, без вступительных фраз):
{{
  "problem": "...",
  "insight": "...",
  "conclusion_or_cta": "...",
  "format_notes": "как конкретно эта структура ляжет на рекомендованный формат"
}}
Ответь СРАЗУ JSON-объектом, без markdown-обрамления (без ```), без
вступительных фраз и без комментариев после JSON."""


def main():
    args = sys.argv[1:]
    if not args:
        print("Использование: python content_zavod/scenarist.py <client> [--ideas-file <path>]")
        sys.exit(1)
    client = args[0]

    if "--ideas-file" in args:
        ideas_path = args[args.index("--ideas-file") + 1]
        from pathlib import Path
        ideas_path = Path(ideas_path)
    else:
        ideas_path = latest_step_output(client, "ideas")
        if ideas_path is None:
            print(f"Не найден ideas_*.json для клиента «{client}» — сначала запустите idea_generator.py")
            sys.exit(1)

    ideas = json.loads(ideas_path.read_text(encoding="utf-8"))
    strategy = read_client_file(client, "strategy.md")

    scenarios = []
    topics = ideas.get("week_topics", [])
    for i, topic in enumerate(topics, 1):
        print(f"Сценарист: тема {i}/{len(topics)} — «{topic.get('topic')}»...")
        prompt = (
            SYSTEM_PROMPT.format(vk_requirements=VK_PROMOTION_REQUIREMENTS)
            + f"\n\n=== Тема ===\n{json.dumps(topic, ensure_ascii=False)}"
            + f"\n\n=== strategy.md клиента «{client}» (тон, упаковка эксперта) ===\n{strategy}"
        )
        result, scenario = ask_for_json_with_retry(prompt)
        # Чекпойнт каждой темы сразу — обрыв на теме 4 из 7 не теряет 1-3
        checkpoint(client, f"scenario_{i}_raw", result)
        if scenario is None:
            print(f"⚠ Тема {i}: не удалось получить валидный JSON после повторных попыток — "
                  "сырой ответ сохранён в чекпойнте, пропускаю.")
            continue
        scenario["topic"] = topic
        scenarios.append(scenario)

    scenarios_path = checkpoint(client, "scenarios", json.dumps(scenarios, ensure_ascii=False, indent=2), ext="json")
    print(f"\nГотово: {scenarios_path} ({len(scenarios)}/{len(topics)} тем успешно)")


if __name__ == "__main__":
    main()
