"""Композитор ContentZavod: музыкальное ТЗ к утверждаемому видеочерновику.

Не создаёт и не публикует треки. Его результат — оригинальный план
аранжировки, который человек прослушивает и утверждает отдельно.

Использование: python content_zavod/composer.py oleg [номер_черновика]
"""
import json
import sys

from common import ask_for_json_with_retry, checkpoint, latest_step_output


COMPOSER_PROMPT = """Ты — Композитор в ContentZavod. Создай оригинальное
музыкальное ТЗ для короткого вертикального ролика. Музыка поддерживает смысл,
а не спорит с текстом. Никаких имитаций конкретных артистов, заимствованных
мелодий, цитат треков, ссылок на музыку или обещаний использовать чужие записи.

Для ТКМ и безопасного образовательного контента: спокойный, человеческий,
современный тон; без тревожных эффектов и медицинских обещаний.
Длительность должна совпасть с видео. В первых 2 секундах — ясный хук,
к финалу — мягкая положительная развязка. Не публикуй и не выбирай лицензии:
это обязательно проверяет человек.

Ответь строго JSON-объектом:
{
  "title": "...",
  "duration_seconds": 15,
  "tempo_bpm": 108,
  "key": "C major",
  "mood": "...",
  "main_motif_notes": ["E5", "G5", "A5", "G5"],
  "arrangement": [
    {"timecode": "0-2с", "visual_sync": "...", "harmony": "...",
     "instruments": ["..."], "melody_action": "..."}
  ],
  "mix_notes": "...",
  "human_review_checklist": ["..."],
  "copyright_note": "Только оригинальная музыка или трек с подтверждённой лицензией.",
  "needs_human_approval": true
}
"""


def load_draft(client: str, index: int) -> dict:
    path = latest_step_output(client, "drafts_final")
    if path is None:
        raise FileNotFoundError("Нет drafts_final_*.json: сначала запустите format_pipeline.py")
    drafts = json.loads(path.read_text(encoding="utf-8"))
    if not 1 <= index <= len(drafts):
        raise IndexError(f"Номер черновика — от 1 до {len(drafts)}")
    return drafts[index - 1]


def main() -> None:
    if len(sys.argv) not in (2, 3):
        print("Использование: python content_zavod/composer.py <client> [номер_черновика]")
        sys.exit(1)
    client = sys.argv[1]
    index = int(sys.argv[2]) if len(sys.argv) == 3 else 1
    try:
        draft = load_draft(client, index)
    except (FileNotFoundError, IndexError, ValueError, json.JSONDecodeError) as error:
        print(f"Ошибка входного черновика: {error}")
        sys.exit(1)

    video_script = draft.get("video_script", [])
    prompt = (
        COMPOSER_PROMPT
        + "\n=== Тема ===\n" + str(draft.get("topic", "Без темы"))
        + "\n=== Выбранный хук ===\n" + str(draft.get("chosen_hook", ""))
        + "\n=== Покадровый сценарий ===\n"
        + json.dumps(video_script, ensure_ascii=False, indent=2)
    )
    result, brief = ask_for_json_with_retry(prompt)
    checkpoint(client, f"composer_{index}_raw", result)
    if brief is None:
        print("Не получен валидный музыкальный план; сырой ответ сохранён для проверки.")
        sys.exit(2)
    brief["source_topic"] = draft.get("topic", "")
    brief["draft_index"] = index
    brief["needs_human_approval"] = True
    out = checkpoint(client, f"music_brief_{index}", json.dumps(brief, ensure_ascii=False, indent=2), ext="json")
    print(f"Музыкальное ТЗ готово: {out}")
    print("Статус: ждёт ручного прослушивания и одобрения; публикация не выполнялась.")


if __name__ == "__main__":
    main()
