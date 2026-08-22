"""Wire protocol shared by the VPS gateway and the Windows PC agent."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

PROTOCOL_VERSION = 1


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def message(kind: str, **payload) -> str:
    body = {"v": PROTOCOL_VERSION, "kind": kind, "id": uuid.uuid4().hex,
            "ts": now_iso(), **payload}
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


def parse(raw: str) -> dict:
    body = json.loads(raw)
    if body.get("v") != PROTOCOL_VERSION:
        raise ValueError(f"unsupported protocol version: {body.get('v')}")
    if not isinstance(body.get("kind"), str):
        raise ValueError("message kind is required")
    return body
