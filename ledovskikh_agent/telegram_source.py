from __future__ import annotations
from .core import Message

async def collect_messages(api_id, api_hash, session, folder, allowlist):
    try:
        from telethon import TelegramClient, functions
    except ImportError as exc:
        raise RuntimeError("Telethon is required") from exc
    client = TelegramClient(session, api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError("Telegram session is not authorized; create it manually outside scheduler")
    selected = set(allowlist)
    if not selected:
        filters = await client(functions.messages.GetDialogFiltersRequest())
        for item in filters.filters:
            if str(getattr(item, "title", "")) == folder:
                for peer in item.include_peers:
                    selected.add(int(await client.get_peer_id(peer)))
    result = []
    for chat_id in selected:
        entity = await client.get_entity(chat_id)
        async for msg in client.iter_messages(entity, limit=100, reverse=True):
            result.append(Message(chat_id, msg.id, msg.date.isoformat(), msg.raw_text or "", getattr(entity, "title", str(chat_id))))
    await client.disconnect()
    return result
