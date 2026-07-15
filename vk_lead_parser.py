"""
vk_lead_parser.py — парсинг "похожей аудитории" ВК: участники групп-доноров
(похожие по теме сообщества — семейная психология, разводы, отношения),
отфильтрованные по региону и активности, для органического продвижения
(комментарий эксперта, точечные приглашения), не для рекламных баз/спама.

Отдельный CLI-скрипт, не подключён к bot.py — тестируется и запускается
руками, пока не доказал полезность (см. правило проекта не усложнять
раньше времени, CLAUDE.md).

Запуск:
    python vk_lead_parser.py --groups misemia,psy_chaikovsky --cities "Чайковский,Пермь" --out leads.csv
"""
import argparse
import csv
import sys
import time
from dataclasses import dataclass, asdict

import requests

from config import VK_TOKEN

API = "https://api.vk.com/method"
API_VERSION = "5.199"
RATE_LIMIT_SLEEP = 0.35  # VK ограничивает ~3 запроса/сек
MEMBERS_PAGE_SIZE = 1000  # максимум за один вызов groups.getMembers


@dataclass
class Lead:
    user_id: int
    first_name: str
    last_name: str
    city: str
    profile_url: str
    source_group: str
    last_seen_days_ago: int | None


def _vk_call(method: str, **params) -> dict:
    params["access_token"] = VK_TOKEN
    params["v"] = API_VERSION
    resp = requests.get(f"{API}/{method}", params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"VK API error [{method}]: {data['error']}")
    time.sleep(RATE_LIMIT_SLEEP)
    return data["response"]


def resolve_group_id(screen_name: str) -> int:
    """Принимает screen_name (misemia) или числовой id, возвращает numeric group id."""
    screen_name = screen_name.strip().lstrip("-")
    if screen_name.isdigit():
        return int(screen_name)
    resolved = _vk_call("utils.resolveScreenName", screen_name=screen_name)
    if not resolved or resolved.get("type") != "group":
        raise ValueError(f"'{screen_name}' — не похоже на группу ВК")
    return resolved["object_id"]


def fetch_group_members(group_id: int, source_label: str) -> list[Lead]:
    """Постранично тянет участников группы с полями city/last_seen."""
    leads: list[Lead] = []
    offset = 0
    fields = "city,last_seen,sex"
    while True:
        resp = _vk_call(
            "groups.getMembers",
            group_id=group_id,
            offset=offset,
            count=MEMBERS_PAGE_SIZE,
            fields=fields,
        )
        items = resp.get("items", [])
        if not items:
            break
        now = int(time.time())
        for u in items:
            if u.get("deactivated"):
                continue
            city = (u.get("city") or {}).get("title", "")
            last_seen_ts = (u.get("last_seen") or {}).get("time")
            last_seen_days = (now - last_seen_ts) // 86400 if last_seen_ts else None
            leads.append(Lead(
                user_id=u["id"],
                first_name=u.get("first_name", ""),
                last_name=u.get("last_name", ""),
                city=city,
                profile_url=f"https://vk.com/id{u['id']}",
                source_group=source_label,
                last_seen_days_ago=last_seen_days,
            ))
        offset += MEMBERS_PAGE_SIZE
        if offset >= resp.get("count", 0):
            break
    return leads


def filter_leads(leads: list[Lead], cities: list[str] | None, max_days_inactive: int) -> list[Lead]:
    cities_lower = {c.strip().lower() for c in cities} if cities else None
    result = []
    for lead in leads:
        if cities_lower and lead.city.lower() not in cities_lower:
            continue
        if lead.last_seen_days_ago is None or lead.last_seen_days_ago > max_days_inactive:
            continue
        result.append(lead)
    return result


def dedup_leads(leads: list[Lead]) -> list[Lead]:
    seen: dict[int, Lead] = {}
    for lead in leads:
        if lead.user_id not in seen:
            seen[lead.user_id] = lead
    return list(seen.values())


def write_csv(leads: list[Lead], out_path: str) -> None:
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(leads[0]).keys()) if leads else
                                 ["user_id", "first_name", "last_name", "city",
                                  "profile_url", "source_group", "last_seen_days_ago"])
        writer.writeheader()
        for lead in leads:
            writer.writerow(asdict(lead))


def main():
    parser = argparse.ArgumentParser(description="Парсинг похожей аудитории ВК для органического продвижения")
    parser.add_argument("--groups", required=True,
                         help="Список групп-доноров через запятую (screen_name или id), напр. misemia,psy_chaikovsky")
    parser.add_argument("--cities", default="",
                         help="Фильтр по городам через запятую, напр. 'Чайковский,Пермь'. Пусто — без фильтра")
    parser.add_argument("--max-days-inactive", type=int, default=30,
                         help="Отсеять тех, кто не заходил дольше N дней (по умолчанию 30)")
    parser.add_argument("--out", default="leads.csv", help="Путь для сохранения CSV")
    args = parser.parse_args()

    if not VK_TOKEN:
        print("VK_TOKEN не задан в .env — без токена API недоступен.", file=sys.stderr)
        sys.exit(1)

    cities = [c for c in args.cities.split(",") if c.strip()] or None
    all_leads: list[Lead] = []

    for raw_group in args.groups.split(","):
        raw_group = raw_group.strip()
        if not raw_group:
            continue
        print(f"Группа '{raw_group}': резолвлю id...")
        try:
            group_id = resolve_group_id(raw_group)
            print(f"  id={group_id}, собираю участников...")
            members = fetch_group_members(group_id, source_label=raw_group)
            print(f"  собрано {len(members)} участников")
            all_leads.extend(members)
        except Exception as e:
            print(f"  ошибка: {e}", file=sys.stderr)

    filtered = filter_leads(all_leads, cities, args.max_days_inactive)
    deduped = dedup_leads(filtered)

    print(f"Всего собрано: {len(all_leads)}, после фильтра города/активности: {len(filtered)}, "
          f"после дедупликации: {len(deduped)}")

    write_csv(deduped, args.out)
    print(f"Сохранено в {args.out}")


if __name__ == "__main__":
    main()
