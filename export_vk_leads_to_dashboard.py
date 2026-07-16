"""
Конвертирует вывод vk_lead_parser.py (leads.csv — похожая аудитория ВК)
в формат public/leads.json дашборда Keen Lead Scoop, дописывая записи
рядом с теми, что кладёт leads_demo.py --export (Разведчик), а не заменяя их.

Использование:
    python export_vk_leads_to_dashboard.py leads.csv \
        "C:\\Users\\HP\\Documents\\Project\\keen-lead-scoop\\public\\leads.json"
"""
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def vk_row_to_lead(row: dict) -> dict:
    name = f"{row['first_name']} {row['last_name']}".strip()
    return {
        "id": f"vk-{row['user_id']}",
        "name": name or row["profile_url"],
        "message": f"Похожая аудитория группы {row['source_group']}"
        + (f", город {row['city']}" if row.get("city") else ""),
        "source": f"VK: {row['source_group']} — {row['profile_url']}",
        "keyword": row["source_group"],
        "date": datetime.now(timezone.utc).isoformat(),
        "status": "Новый",
        "hot": False,
    }


def main():
    if len(sys.argv) != 3:
        print("Использование: python export_vk_leads_to_dashboard.py <leads.csv> <leads.json>")
        sys.exit(1)

    csv_path, json_path = Path(sys.argv[1]), Path(sys.argv[2])

    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        new_leads = [vk_row_to_lead(row) for row in csv.DictReader(f)]

    existing = json.loads(json_path.read_text(encoding="utf-8")) if json_path.exists() else []
    existing_ids = {lead["id"] for lead in existing}

    added = [lead for lead in new_leads if lead["id"] not in existing_ids]
    merged = existing + added

    json_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Добавлено {len(added)} новых лидов из {len(new_leads)} в CSV "
          f"(пропущено дублей: {len(new_leads) - len(added)}). Всего в {json_path.name}: {len(merged)}.")


if __name__ == "__main__":
    main()
