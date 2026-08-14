from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Callable, Iterable
import ipaddress
import json
import re
import socket
from urllib.parse import urlparse

URL_RE = re.compile(r"https?://[^\s<>\]\[\"']+", re.I)
KEYWORDS = (
    "vibe coding", "vibecoding", "vibe-coding",
    "вайбкодинг", "вайб-кодинг", "вайб кодинг",
    "codex", "кодекс", "agent", "агент", "multi-agent", "мультиагент",
    "проект", "ledovsk", "ледовск",
)


@dataclass(frozen=True)
class Message:
    chat_id: int
    message_id: int
    date: str
    text: str
    chat_title: str = ""


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    source: dict
    url: str
    relevance: list[str]
    summary: str
    proposal: str
    status: str = "proposed"
    implementation: str = "not_applied"
    verification: str = "pending_quality_gates"


def extract_urls(text: str) -> list[str]:
    return list(dict.fromkeys(url.rstrip(".,);!?\u00bb") for url in URL_RE.findall(text or "")))


def relevance(text: str, url: str = "") -> list[str]:
    haystack = f"{text} {url}".lower()
    return [keyword for keyword in KEYWORDS if keyword in haystack]


def is_public_http_url(url: str, resolver: Callable[[str], Iterable[str]] | None = None) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return False
    if parsed.port not in (None, 80, 443):
        return False
    resolve = resolver or (lambda host: {item[4][0] for item in socket.getaddrinfo(host, None)})
    try:
        addresses = list(resolve(parsed.hostname))
        return bool(addresses) and all(ipaddress.ip_address(address).is_global for address in addresses)
    except (OSError, ValueError):
        return False


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"checkpoints": {}, "seen": [], "candidates": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def checkpoint(self, chat_id: int) -> int:
        return int(self.data["checkpoints"].get(str(chat_id), 0))

    def process(self, messages: Iterable[Message], link_reader: Callable[[str], str] | None = None) -> list[Candidate]:
        created: list[Candidate] = []
        seen = set(self.data["seen"])
        for msg in sorted(messages, key=lambda item: (item.chat_id, item.message_id)):
            if msg.message_id <= self.checkpoint(msg.chat_id):
                continue
            for url in extract_urls(msg.text):
                digest = sha256(f"{msg.chat_id}:{msg.message_id}:{url}".encode()).hexdigest()[:20]
                if digest in seen:
                    continue
                tags = relevance(msg.text, url)
                if not tags:
                    continue
                page_text = link_reader(url) if link_reader and is_public_http_url(url) else ""
                combined_tags = list(dict.fromkeys(tags + relevance(page_text, url)))
                candidate = Candidate(
                    candidate_id=digest,
                    source={"chat_id": msg.chat_id, "chat": msg.chat_title, "message_id": msg.message_id, "date": msg.date},
                    url=url,
                    relevance=combined_tags,
                    summary=(page_text or msg.text)[:1000],
                    proposal="Review the source, define a reversible change and tests; apply only after QA/Security and human approval when external or risky.",
                )
                created.append(candidate)
                self.data["candidates"].append(asdict(candidate))
                self.data["seen"].append(digest)
                seen.add(digest)
            self.data["checkpoints"][str(msg.chat_id)] = max(self.checkpoint(msg.chat_id), msg.message_id)
        self.save()
        return created


def write_report(candidates: Iterable[Candidate], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".md")
    rows = ["# Отчёт агента «Ледовских»", ""]
    items = list(candidates)
    if not items:
        rows.append("Новых релевантных материалов нет.")
    for item in items:
        rows += [f"## {item.candidate_id}", f"- Источник: {item.source['chat']} / сообщение {item.source['message_id']}", f"- Ссылка: {item.url}", f"- Вывод: {item.summary}", f"- Предложено: {item.proposal}", f"- Внедрено: {item.implementation}", f"- Проверено: {item.verification}", f"- Статус: {item.status}", ""]
    path.write_text("\n".join(rows), encoding="utf-8")
    return path
