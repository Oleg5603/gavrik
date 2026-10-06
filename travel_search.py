"""Build saved travel-search constraints injected into Gavrik's agent prompt."""

from __future__ import annotations

import json
import re
from pathlib import Path

TRAVEL_TERMS = re.compile(r"авиа|билет|тур(?:ы|а|е|ов)?|перел[её]т|поездк|отпуск", re.IGNORECASE)


def build_travel_search_context(message: str, config_path: Path) -> str:
    """Return travel rules only for travel-related requests."""
    if not TRAVEL_TERMS.search(message):
        return ""

    config = json.loads(config_path.read_text(encoding="utf-8"))
    origin = config["origin"]
    destination = config["destination"]
    month = config["departure_month"]
    passengers = config["passengers"]
    stay_days = config["stay_days"]
    group_cap = config["group_total_cap_rub"]

    return (
        "\n\n=== СОХРАНЁННЫЕ УСЛОВИЯ ПОИСКА ПОЕЗДОК ===\n"
        f"Маршрут: {origin} — {destination}. Месяц вылета: {month}. "
        f"Пассажиров: {passengers}. Туда и обратно. Длительность: {stay_days} дней "
        f"(дата обратного вылета на {stay_days} дней позже; возврат может попасть "
        "на следующий месяц, если вылет был в мае).\n"
        f"Для авиабилетов и пакетных туров показывай только полную подтверждённую "
        f"общую цену для всех {passengers} пассажиров не выше {group_cap} ₽; бюджет "
        "включает поездку туда и обратно, а для тура — весь пакет на двоих. "
        "Разделяй авиабилеты и пакетные туры в результатах.\n"
        "Применяй эти условия только к поиску поездок; явные более новые условия "
        "пользователя имеют приоритет. Не расширяй месяц вылета или маршрут самовольно.\n"
        "Не умножай тариф одного пассажира на число пассажиров и не выдавай расчёт "
        "или кэшированную/устаревшую цену за подтверждённую. Если цена дана только "
        "на одного пассажира либо итог для двоих не подтверждён источником, пометь "
        "её как неподтверждённый ориентир и не включай в список подходящих вариантов.\n"
        "Проверь даты, направление туда и обратно и итог для двоих. Если источник "
        "закрыт, не показывает общую стоимость или вариантов в бюджете нет, так и сообщи; "
        "не подставляй соседние месяцы. Для каждого подходящего результата укажи даты, "
        "длительность, общую цену на двоих, подтверждённые сведения о багаже/местах, "
        "время проверки и ссылку на источник.\n"
    )
