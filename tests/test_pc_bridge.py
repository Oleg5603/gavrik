import asyncio
import tempfile
import unittest
from pathlib import Path

from pc_bridge.client import PCAgent
from pc_bridge.protocol import message, parse


class PCBridgeTests(unittest.TestCase):
    def test_protocol_roundtrip(self):
        body = parse(message("ping", value=3))
        self.assertEqual(body["kind"], "ping")
        self.assertEqual(body["value"], 3)

    def test_agent_path_is_sandboxed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent = PCAgent("ws://127.0.0.1/pc/ws", "token", [root])
            self.assertEqual(agent._safe_path(str(root / "ok.txt")), root / "ok.txt")
            with self.assertRaises(PermissionError):
                agent._safe_path(str(root.parent / "outside.txt"))

    def test_status_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = PCAgent("ws://127.0.0.1/pc/ws", "token", [Path(tmp)])
            result = asyncio.run(agent._execute({"command": "status"}))
            self.assertIn("platform", result)

    def test_write_is_size_limited(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = PCAgent("ws://127.0.0.1/pc/ws", "token", [Path(tmp)], max_file_bytes=3)
            command = {"command": "write", "path": str(Path(tmp) / "large.bin"),
                       "data_b64": "QUJDRA=="}
            with self.assertRaisesRegex(ValueError, "exceeds"):
                asyncio.run(agent._execute(command))

    def test_exec_is_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = PCAgent("ws://127.0.0.1/pc/ws", "token", [Path(tmp)])
            with self.assertRaisesRegex(PermissionError, "disabled"):
                asyncio.run(agent._execute({"command": "exec", "argv": ["echo", "x"]}))
