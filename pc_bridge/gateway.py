"""VPS-side aiohttp WebSocket gateway for one authenticated PC agent."""

from __future__ import annotations

import asyncio
import hmac
import logging
import time
from dataclasses import dataclass

from aiohttp import web

from .protocol import message, parse

log = logging.getLogger("gavrik.pc_gateway")


@dataclass
class Pending:
    future: asyncio.Future
    created: float


class PCGateway:
    def __init__(self, token: str, max_message_bytes: int = 100 * 1024 * 1024):
        self.token = token
        self.max_message_bytes = max_message_bytes
        self.ws: web.WebSocketResponse | None = None
        self.last_seen = 0.0
        self.pending: dict[str, Pending] = {}
        self._lock = asyncio.Lock()

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/pc/ws", self.handle_ws)
        app.router.add_get("/pc/health", self.health)
        return app

    async def health(self, _request: web.Request) -> web.Response:
        age = time.time() - self.last_seen if self.last_seen else None
        return web.json_response({"online": bool(age is not None and age < 60), "last_seen": self.last_seen, "age": age})

    async def handle_ws(self, request: web.Request) -> web.StreamResponse:
        auth = request.headers.get("Authorization", "")
        if not hmac.compare_digest(auth, f"Bearer {self.token}"):
            raise web.HTTPUnauthorized()
        ws = web.WebSocketResponse(heartbeat=20, max_msg_size=self.max_message_bytes)
        await ws.prepare(request)
        async with self._lock:
            if self.ws and not self.ws.closed:
                await self.ws.close(code=4001, message=b"replaced by newer PC agent")
            self.ws = ws
        self.last_seen = time.time()
        try:
            async for raw in ws:
                if raw.type != web.WSMsgType.TEXT:
                    continue
                body = parse(raw.data)
                self.last_seen = time.time()
                if body["kind"] == "hello":
                    await ws.send_str(message("hello_ack"))
                elif body["kind"] == "pong":
                    continue
                elif body["kind"] == "result":
                    pending = self.pending.pop(body.get("reply_to", ""), None)
                    if pending and not pending.future.done():
                        pending.future.set_result(body)
        finally:
            async with self._lock:
                if self.ws is ws:
                    self.ws = None
        return ws

    async def command(self, command: dict, timeout: float = 900) -> dict:
        if not self.ws or self.ws.closed or time.time() - self.last_seen > 60:
            raise ConnectionError("PC agent is offline")
        raw = message("command", command=command)
        request_id = __import__("json").loads(raw)["id"]
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.pending[request_id] = Pending(future, time.time())
        await self.ws.send_str(raw)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self.pending.pop(request_id, None)
