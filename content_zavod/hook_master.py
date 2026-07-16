"""
Мастер хуков (Фаза 2, ContentZavod) — CLI-скрипт.

Читает последний чекпойнт scenarios_*.json, для каждого сценария выдаёт
3-5 вариантов первой фразы/хука — с учётом того, что первые секунды/строки
решают удержание внимания (ключевой сигнал алгоритма ВК).

Использование:
    python content_zavod/hook_master.py oleg
"""
import json
import sys

from common import VK_PROMOTION_REQUIREMENTS, ask_for_json_with_retry, checkpoint, latest_step_output

SYSTEM_PROMPT = """Ты — Мастер хуков в конвейере контента. На вход — один
сценарий (проблема/инсайт/призыв + рекомендованный формат). Твоя задача:
выдать 3-5 вариантов первой фразы/хука, максимально удерживающих внимание
в первые 2-3 секунды (клип) или первые 2-3 строки до "показать полностью"
(текст/карусель).

{vk_requirements}

Хук должен:
- Бить прямо в проблему из сценария, не быть абстрактным
- НЕ быть дешёвым кликбейтом без раскрытия темы (алгоритм и аудитория это
  считывают — короткое время просмотра после кликбейта хуже, чем честный,
  но точный хук)
- Провоцировать желание узнать продолжение/дочитать, не обещая того, чего
  в посте нет

Дай 3-5 РАЗНЫХ по подходу вариантов (не вариации одной фразы): например,
вопрос-провокация, конкретная цифра/факт, личное признание, контраст
ожидание/реальность.

Ответ строго в JSON (без markdown-обрамления, без вступительных фраз):
{{
  "hooks": [
    {{"hook": "...", "approach": "вопрос-провокация|цифра-факт|личное-признание|контраст|другое"}}
  ]
}}
Ответь СРАЗУ JSON-объектом, без markdown-обрамления (без ```), без
вступительных фраз и без комментариев после JSON."""


def main():
    if len(sys.argv) != 2:
        print("Использование: python content_zavod/hook_master.py <client>")
        sys.exit(1)
    client = sys.argv[1]

    scenarios_path = latest_step_output(client, "scenarios")
    if scenarios_path is None:
        print(f"Не найден scenarios_*.json для клиента «{client}» — сначала запустите scenarist.py")
        sys.exit(1)

    scenarios = json.loads(scenarios_path.read_text(encoding="utf-8"))

    results = []
    for i, scenario in enumerate(scenarios, 1):
        topic = scenario.get("topic", {}).get("topic", f"тема {i}")
        print(f"Мастер хуков: сценарий {i}/{len(scenarios)} — «{topic}»...")
        prompt = (
            SYSTEM_PROMPT.format(vk_requirements=VK_PROMOTION_REQUIREMENTS)
            + f"\n\n=== Сценарий ===\n{json.dumps(scenario, ensure_ascii=False)}"
        )
        result, hooks = ask_for_json_with_retry(prompt)
        checkpoint(client, f"hooks_{i}_raw", result)
        if hooks is None:
            print(f"⚠ Сценарий {i}: не удалось получить валидный JSON после повторных попыток — "
                  "сырой ответ сохранён в чекпойнте, пропускаю.")
            continue
        results.append({"scenario": scenario, "hooks": hooks.get("hooks", [])})

    out_path = checkpoint(client, "hooks_final", json.dumps(results, ensure_ascii=False, indent=2), ext="json")
    print(f"\nГотово: {out_path} ({len(results)}/{len(scenarios)} сценариев успешно)")

    print("\n--- Итоги для ручной проверки ---\n")
    for i, r in enumerate(results, 1):
        print(f"{i}. {r['scenario'].get('topic', {}).get('topic')}")
        for h in r["hooks"]:
            print(f"   [{h.get('approach')}] {h.get('hook')}")
        print()


if __name__ == "__main__":
    main()
