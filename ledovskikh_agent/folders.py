"""List Telegram folder titles and chat counts without reading messages."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv


async def main() -> int:
    from telethon import TelegramClient, functions

    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    api_id = int(os.getenv("LEDOVSKIKH_TG_API_ID", "0"))
    api_hash = os.getenv("LEDOVSKIKH_TG_API_HASH", "")
    session = os.getenv("LEDOVSKIKH_TG_SESSION", str(root / ".private" / "ledovskikh"))
    client = TelegramClient(session, api_id, api_hash)
    await client.connect()
    try:
        filters = await client(functions.messages.GetDialogFiltersRequest())
        for item in filters.filters:
            raw_title = getattr(item, "title", "")
            title = str(getattr(raw_title, "text", raw_title)).strip()
            count = len(getattr(item, "include_peers", []))
            print(f"{title} | chats: {count}")
    finally:
        await client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
