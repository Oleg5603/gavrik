"""Outbound PC agent. Run this as a Windows service or scheduled task."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import shlex
import time
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

from .protocol import message, parse

log = logging.getLogger("gavrik.pc_agent")


class PCAgent:
    def __init__(self, url: str, token: str, roots: list[Path] | None = None,
                 max_file_bytes: int = 50 * 1024 * 1024, allow_exec: bool = False):
        self.url = url
        self.token = token
        self.roots = [p.resolve() for p in (roots or [Path.cwd()])]
        self.max_file_bytes = max_file_bytes
        self.allow_exec = allow_exec
        self.stop_event = asyncio.Event()
        self.last_connected = 0.0

    def _safe_path(self, raw: str) -> Path:
        path = Path(raw).expanduser().resolve()
        if not any(path == root or root in path.parents for root in self.roots):
            raise PermissionError("path is outside configured PC_AGENT_ROOTS")
        return path

    async def _execute(self, cmd: dict) -> dict:
        kind = cmd.get("command")
        if kind == "status":
            return {"platform": os.name, "cwd": str(Path.cwd()),
                    "connected_since": self.last_connected}
        if kind == "read":
            path = self._safe_path(cmd["path"])
            if path.stat().st_size > self.max_file_bytes:
                raise ValueError("file exceeds PC_AGENT_MAX_FILE_BYTES")
            data = await asyncio.to_thread(path.read_bytes)
            return {"path": str(path), "data_b64": base64.b64encode(data).decode()}
        if kind == "write":
            path = self._safe_path(cmd["path"])
            data = base64.b64decode(cmd["data_b64"], validate=True)
            if len(data) > self.max_file_bytes:
                raise ValueError("file exceeds PC_AGENT_MAX_FILE_BYTES")
            path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(path.write_bytes, data)
            return {"path": str(path), "bytes": len(data)}
        if kind == "exec":
            if not self.allow_exec:
                raise PermissionError("exec is disabled")
            # Commands are explicit jobs sent by the authenticated VPS gateway.
            argv = cmd.get("argv")
            if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
                raise ValueError("exec requires argv: list[str]")
            proc = await asyncio.create_subprocess_exec(
                *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            try:
                out, err = await asyncio.wait_for(proc.communicate(), timeout=float(cmd.get("timeout", 900)))
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise TimeoutError("command timed out")
            return {"returncode": proc.returncode, "stdout": out.decode(errors="replace"),
                    "stderr": err.decode(errors="replace")}
        raise ValueError(f"unknown command: {kind}")

    async def run(self) -> None:
        delay = 1.0
        timeout = aiohttp.ClientTimeout(total=None, connect=20, sock_read=None)
        headers = {"Authorization": f"Bearer {self.token}"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            while not self.stop_event.is_set():
                try:
                    async with session.ws_connect(
                        self.url, heartbeat=20, autoping=True,
                        max_msg_size=max(self.max_file_bytes * 2, 4 * 1024 * 1024),
                    ) as ws:
                        self.last_connected = time.time()
                        delay = 1.0
                        capabilities = ["status", "read", "write"]
                        if self.allow_exec:
                            capabilities.append("exec")
                        await ws.send_str(message("hello", agent="pc", capabilities=capabilities))
                        async for raw in ws:
                            body = parse(raw.data)
                            if body["kind"] == "ping":
                                await ws.send_str(message("pong", reply_to=body.get("id")))
                            elif body["kind"] == "command":
                                try:
                                    result = await self._execute(body)
                                    await ws.send_str(message("result", reply_to=body.get("id"), ok=True, result=result))
                                except Exception as exc:  # report, keep the channel alive
                                    await ws.send_str(message("result", reply_to=body.get("id"), ok=False, error=str(exc)))
                except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
                    log.warning("PC bridge disconnected: %s; retry in %.1fs", exc, delay)
                if self.stop_event.is_set():
                    break
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60.0)


def main() -> None:
    env_file = os.getenv("PC_AGENT_ENV_FILE")
    if env_file:
        load_dotenv(env_file, override=False)
    logging.basicConfig(level=os.getenv("PC_AGENT_LOG_LEVEL", "INFO"))
    roots = [Path(x) for x in os.getenv("PC_AGENT_ROOTS", str(Path.cwd())).split(os.pathsep) if x]
    max_bytes = int(os.getenv("PC_AGENT_MAX_FILE_BYTES", str(50 * 1024 * 1024)))
    allow_exec = os.getenv("PC_AGENT_ALLOW_EXEC", "0").strip().lower() in {"1", "true", "yes"}
    agent = PCAgent(os.environ["PC_AGENT_URL"], os.environ["PC_AGENT_TOKEN"], roots,
                    max_file_bytes=max_bytes, allow_exec=allow_exec)
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
