"""
Конвейер форматов (Фаза 3, ContentZavod) — CLI-скрипт.

Читает последний чекпойнт hooks_final_*.json (сценарий + варианты хуков),
для каждого сценария выдаёт готовые черновики под все форматы: пост ВК,
пост ТГ, карусель (слайды), видео-сценарий. Лимиты по формату — из
PLAN.md "Фаза 3 — Конвейер форматов".

Хук пока выбирается моделью из 5 вариантов Мастера хуков (с явным
указанием, какой выбран и почему) — финальное слово всё равно за
человеком на Фазе 4 (Редактор), ничего не публикуется без одобрения.

Использование:
    python content_zavod/format_pipeline.py oleg
"""
import json
import sys

from common import VK_PROMOTION_REQUIREMENTS, ask_for_json_with_retry, checkpoint, latest_step_output

FORMAT_LIMITS = """=== Лимиты форматов (см. PLAN.md, Фаза 3) ===
- Пост ВК: целимся в 800-1500 символов; первые ~150 символов — до обрыва
  "Показать полностью" — там обязательно должен быть выбранный хук.
- Пост ТГ: целимся в 400-900 символов (лимит канала — 4096, но органика
  короче), поддерживается Markdown-разметка (**жирный**, *курсив*).
- Карусель: 6-10 слайдов, на слайд — заголовок (до ~60 символов) +
  короткий тезис (до ~120 символов), связный нарратив слайд-к-слайду,
  первый слайд = хук.
- Видео-сценарий: хронометраж 30-90 сек, структура хук(0-3с)/развитие/
  призыв к действию, покадровый текст с таймкодами (например [0-3с], [3-15с]...)."""

SYSTEM_PROMPT = """Ты — Конвейер форматов в цепочке контента. На вход —
сценарий (проблема/инсайт/призыв) и 3-5 вариантов хука от Мастера хуков.

{vk_requirements}

{format_limits}

Твоя задача:
1. Выбери из предложенных хуков ОДИН, наиболее подходящий именно этому
   сценарию и рекомендованному формату — укажи, какой выбрал (текст хука)
   и одним предложением почему.
2. На основе сценария и выбранного хука напиши готовые черновики для ВСЕХ
   четырёх форматов (даже если в теме указан только один рекомендованный
   формат — конвейер форматов всегда делает все четыре, это и есть его
   смысл: экономия «один сценарий → все форматы»).

Ответ строго в JSON (без markdown-обрамления, без вступительных фраз):
{{
  "chosen_hook": "...",
  "chosen_hook_reason": "...",
  "vk_post": "...",
  "tg_post": "...",
  "carousel_slides": [
    {{"title": "...", "text": "..."}}
  ],
  "video_script": [
    {{"timecode": "0-3с", "text": "..."}}
  ]
}}
Ответь СРАЗУ JSON-объектом, без markdown-обрамления (без ```), без
вступительных фраз и без комментариев после JSON."""


def main():
    if len(sys.argv) != 2:
        print("Использование: python content_zavod/format_pipeline.py <client>")
        sys.exit(1)
    client = sys.argv[1]

    hooks_path = latest_step_output(client, "hooks_final")
    if hooks_path is None:
        print(f"Не найден hooks_final_*.json для клиента «{client}» — сначала запустите hook_master.py")
        sys.exit(1)

    items = json.loads(hooks_path.read_text(encoding="utf-8"))

    drafts = []
    for i, item in enumerate(items, 1):
        topic = item["scenario"].get("topic", {}).get("topic", f"тема {i}")
        print(f"Конвейер форматов: сценарий {i}/{len(items)} — «{topic}»...")
        prompt = (
            SYSTEM_PROMPT.format(vk_requirements=VK_PROMOTION_REQUIREMENTS, format_limits=FORMAT_LIMITS)
            + f"\n\n=== Сценарий ===\n{json.dumps(item['scenario'], ensure_ascii=False)}"
            + f"\n\n=== Варианты хуков ===\n{json.dumps(item['hooks'], ensure_ascii=False)}"
        )
        result, draft = ask_for_json_with_retry(prompt)
        checkpoint(client, f"formats_{i}_raw", result)
        if draft is None:
            print(f"⚠ Сценарий {i}: не удалось получить валидный JSON после повторных попыток — "
                  "сырой ответ сохранён в чекпойнте, пропускаю.")
            continue
        draft["topic"] = topic
        drafts.append(draft)

    out_path = checkpoint(client, "drafts_final", json.dumps(drafts, ensure_ascii=False, indent=2), ext="json")
    print(f"\nГотово: {out_path} ({len(drafts)}/{len(items)} сценариев успешно)")

    print("\n--- Черновики для ручной проверки (Фаза 4 — Редактор) ---\n")
    for i, d in enumerate(drafts, 1):
        print(f"\n===== {i}. {d['topic']} =====")
        print(f"Выбранный хук: {d.get('chosen_hook')}  ({d.get('chosen_hook_reason')})")
        print(f"\n--- Пост ВК ({len(d.get('vk_post', ''))} симв.) ---\n{d.get('vk_post')}")
        print(f"\n--- Пост ТГ ({len(d.get('tg_post', ''))} симв.) ---\n{d.get('tg_post')}")
        slides = d.get("carousel_slides", [])
        print(f"\n--- Карусель ({len(slides)} слайдов) ---")
        for s in slides:
            print(f"  • {s.get('title')}: {s.get('text')}")
        script = d.get("video_script", [])
        print(f"\n--- Видео-сценарий ({len(script)} кадров) ---")
        for frame in script:
            print(f"  [{frame.get('timecode')}] {frame.get('text')}")


if __name__ == "__main__":
    main()
