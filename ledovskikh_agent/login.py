"""One-time local Telegram authorization for the Ledovskikh scanner."""

from __future__ import annotations

import asyncio
import getpass
import os
from pathlib import Path

from dotenv import load_dotenv


async def authorize() -> None:
    try:
        from telethon import TelegramClient, errors
    except ImportError as exc:
        raise RuntimeError("Telethon is required") from exc

    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    api_id = int(os.getenv("LEDOVSKIKH_TG_API_ID", "0"))
    api_hash = os.getenv("LEDOVSKIKH_TG_API_HASH", "")
    if not api_id or not api_hash:
        raise SystemExit("Telegram API parameters are not configured.")

    session = os.getenv("LEDOVSKIKH_TG_SESSION", str(root / ".private" / "ledovskikh"))
    Path(session).parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(session, api_id, api_hash)
    await client.connect()
    try:
        if await client.is_user_authorized():
            print("Telegram session is already authorized.")
            return
        phone = input("Telegram phone number (+7...): ").strip()
        await client.send_code_request(phone)
        try:
            await client.sign_in(phone, input("Code from Telegram: ").strip())
        except errors.SessionPasswordNeededError:
            await client.sign_in(password=getpass.getpass("Two-step password: "))
        print("Telegram session authorized. You can now run the scanner.")
    finally:
        await client.disconnect()


def main() -> int:
    asyncio.run(authorize())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
