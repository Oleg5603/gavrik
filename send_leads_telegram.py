#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для отправки leads.csv в Telegram.
Использует токен бота из .env и отправляет CSV в чат получателя.
"""
import os
import sys
from pathlib import Path
import requests
from config import TELEGRAM_TOKEN, ALLOWED_USER_IDS

# Fix Windows encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_DIR = Path(__file__).parent
LEADS_CSV = BASE_DIR / "leads.csv"
TELEGRAM_API = "https://api.telegram.org/bot" + TELEGRAM_TOKEN

def send_csv_to_telegram(user_id: int, csv_path: Path) -> bool:
    """Отправляет CSV-файл в Telegram чат."""
    if not csv_path.exists():
        print(f"❌ Файл не найден: {csv_path}")
        return False

    url = f"{TELEGRAM_API}/sendDocument"
    with open(csv_path, "rb") as f:
        files = {"document": f}
        data = {
            "chat_id": user_id,
            "caption": f"📊 {csv_path.name} — лиды из психологических групп ВК\n\nИтого: {_count_lines(csv_path)-1} контактов"
        }
        resp = requests.post(url, files=files, data=data, timeout=10)

    if resp.status_code == 200:
        print(f"✅ CSV отправлен в Telegram (чат {user_id})")
        return True
    else:
        print(f"❌ Ошибка отправки: {resp.status_code} — {resp.text}")
        return False

def _count_lines(path: Path) -> int:
    """Считает строки в файле."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return len(f.readlines())
    except:
        return 0

if __name__ == "__main__":
    # Получаем первый ID из ALLOWED_USER_IDS (может быть строка или число)
    allowed = ALLOWED_USER_IDS
    if isinstance(allowed, str):
        user_id = int(allowed.split(",")[0].strip())
    else:
        user_id = allowed

    if send_csv_to_telegram(user_id, LEADS_CSV):
        sys.exit(0)
    else:
        sys.exit(1)
