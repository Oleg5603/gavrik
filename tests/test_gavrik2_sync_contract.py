from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "deploy" / "GAVRIK2_SYNC.md"
PC = ROOT / "deploy" / "windows" / "sync_gavrik2.ps1"
SERVER = ROOT / "deploy" / "linux" / "sync_gavrik_server.sh"


def read(path):
    return path.read_text(encoding="utf-8")


def test_no_embedded_credentials():
    text = "\n".join(map(read, (DOC, PC, SERVER)))
    assignment = re.compile(r"(?im)^\s*(?:export\s+|\$env:)?(?:bot_token|api_key|password)\s*=\s*[^\s$]")
    assert not assignment.search(text)
    assert not re.search(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b", text)


def test_pull_only_and_nondestructive():
    scripts = (read(PC) + read(SERVER)).lower()
    assert "reset --hard" not in scripts
    assert not re.search(r"\bgit\s+push\b", scripts)
    assert "git fetch" in scripts and "git switch --detach" in scripts


def test_fail_closed_and_record_only_after_tests():
    pc, server = read(PC), read(SERVER)
    assert "status --porcelain" in pc and "status --porcelain" in server
    assert pc.index("-m pytest") < pc.index("Set-Content")
    assert server.index("-m pytest") < server.index("printf '%s\\n'")
    assert "$ErrorActionPreference = 'Stop'" in pc
    assert "set -Eeuo pipefail" in server
    assert "requirements-dev.txt" in pc and "requirements-dev.txt" in server


def test_pc_does_not_start_application():
    pc = read(PC).lower()
    forbidden = ("start-process", "python bot.py", "run_gavrik", "systemctl start")
    assert all(item not in pc for item in forbidden)
    assert "application was not started" in pc


def test_documented_topology_manifest_and_fencing():
    doc = read(DOC).lower()
    assert "github" in doc and "vps" in doc and "гаврик 2" in doc
    assert "манифест" in doc and "fencing" in doc
    assert "одновременно активен только один" in doc
    assert "не является разрешением автоматически запускать" in doc
