"""Build the saved travel-search constraints injected into Gavrik's agent prompt."""

from __future__ import annotations

import json
import re
from pathlib import Path

TRAVEL_TERMS = re.compile(r"авиа|билет|тур(?:ы|а|е|ов)?|перел[её]т|поездк|отпуск", re.IGNORECASE)


def build_travel_search_context(message: str, config_path: Path) -> str:
    """Return authoritative travel rules only for travel-related requests."""
    if not TRAVEL_TERMS.search(message):
        return ""

    config = json.loads(config_path.read_text(encoding="utf-8"))
    origin = config["origin"]
    destination = config["destination"]
    month = config["departure_month"]
    passengers = config["passengers"]
    stay_days = config["stay_days"]
    flight_cap = config["flight_total_cap_rub"]
    tour_cap = config.get("tour_total_cap_rub")
    tour_cap_text = f"{tour_cap} ₽ для всей группы" if tour_cap is not None else "не задан; не придумывай его"

    return (
        "\n\n=== СОХРАНЁННЫЕ УСЛОВИЯ ПОИСКА ПОЕЗДОК ===\n"
        f"Маршрут: {origin} — {destination}. Месяц вылета: {month}. "
        f"Пассажиров: {passengers}. Туда и обратно. Длительность: {stay_days} дней "
        f"(дата обратного вылета на {stay_days} дней позже даты вылета; возврат может "
        "попасть на следующий месяц, если вылет был в мае).\n"
        f"Авиабилеты показывай только при полной подтверждённой цене туда-обратно "
        f"для всех {passengers} пассажиров строго ниже {flight_cap} ₽.\n"
        f"Лимит для пакетных туров: {tour_cap_text}. Отделяй пакетные туры от авиабилетов.\n"
        "Применяй эти условия только к поиску поездок; явные более новые условия "
        "пользователя имеют приоритет. Не расширяй месяц вылета или маршрут самовольно.\n"
        "Не прибавляй цены отдельных участков и не умножай тариф на одного пассажира "
        "и не выдавай расчёт за найденную цену или подтверждённые места. Если есть только "
        "цена на одного пассажира, либо цена кэшированная/устаревшая, пометь её как "
        "неподтверждённый ориентир и не включай в список подходящих билетов.\n"
        "Проверь направление туда и обратно, обе даты и общую сумму на нужное число "
        "пассажиров. Если источник закрыт, не показывает итог на группу или не даёт "
        "вариантов в рамках бюджета, так и сообщи; не подставляй соседние месяцы. "
        "Для каждого подходящего результата укажи дату вылета и возврата, длительность, "
        "реальную общую цену на группу, что подтверждено по багажу/местам, время проверки "
        "и ссылку на источник.\n"
    )
