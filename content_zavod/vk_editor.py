"""Редакторский gate для постов ВК.

Не публикует автоматически: создаёт отдельный пакет для человеческого
одобрения. Исходные черновики не меняются.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
DRAFTS = ROOT / "clients" / "oleg" / "drafts"

REPLACEMENTS = {
    "Показать полностью": "",
    "декомпозирую": "разбиваю задачу на шаги",
    "декомпозиция": "разбиение задачи на шаги",
    "промпт-паттерн": "приём постановки задачи",
    "паттерн": "приём",
    "почти всегда": "в большинстве случаев",
}


def latest_source() -> Path:
    files = sorted(DRAFTS.glob("drafts_final_*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError("Не найден drafts_final_*.json")
    return files[-1]


def edit_text(text: str) -> str:
    for old, new in REPLACEMENTS.items():
        text = text.replace(old, new)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def validate(text: str) -> list[str]:
    first = text[:150]
    findings = []
    if "http://" in text or "https://" in text:
        findings.append("external_link_in_body")
    if len(text) > 15000:
        findings.append("over_vk_limit")
    if len(first.strip()) < 40:
        findings.append("weak_first_screen")
    tail = text[-500:].lower()
    if "?" not in tail and not any(word in tail for word in ("комментар", "расскажите", "напишите")):
        findings.append("no_question_or_comment_cta")
    if any(word in text.lower() for word in ("всегда", "никогда", "гарантированно")):
        findings.append("absolute_claim")
    return findings


def main() -> None:
    source = latest_source()
    posts = json.loads(source.read_text(encoding="utf-8"))
    ready = []
    for index, item in enumerate(posts, 1):
        post = dict(item)
        post["vk_post"] = edit_text(post.get("vk_post", ""))
        post["editorial"] = {
            "index": index,
            "source": source.name,
            "first_150_chars": post["vk_post"][:150],
            "length": len(post["vk_post"]),
            "findings": validate(post["vk_post"]),
            "approval": "pending",
        }
        ready.append(post)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = DRAFTS / f"vk_ready_{stamp}.json"
    out.write_text(json.dumps(ready, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Источник: {source.name}")
    print(f"Готовый пакет: {out.name}")
    for item in ready:
        meta = item["editorial"]
        result = "OK" if not meta["findings"] else ", ".join(meta["findings"])
        print(f"{meta['index']}: {meta['length']} знаков — {result}")


if __name__ == "__main__":
    main()
