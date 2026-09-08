from __future__ import annotations
import argparse, asyncio, os
from pathlib import Path
from dotenv import load_dotenv
from .core import StateStore, write_report
from .telegram_source import collect_messages

def main() -> int:
    parser = argparse.ArgumentParser(description="Gavrik subordinate agent Ledovskikh")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--content-research", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    api_id = int(os.getenv("LEDOVSKIKH_TG_API_ID", "0"))
    api_hash = os.getenv("LEDOVSKIKH_TG_API_HASH", "")
    if not api_id or not api_hash:
        raise SystemExit("Set LEDOVSKIKH_TG_API_ID and LEDOVSKIKH_TG_API_HASH")
    if args.dry_run:
        print("Configuration OK; authorization was not attempted.")
        return 0
    session = os.getenv("LEDOVSKIKH_TG_SESSION", str(root / ".private" / "ledovskikh"))
    folder = os.getenv("LEDOVSKIKH_TG_FOLDER", "Нейрозавод")
    allowlist = {int(x) for x in os.getenv("LEDOVSKIKH_TG_CHAT_IDS", "").split(",") if x.strip().lstrip("-").isdigit()}
    messages = asyncio.run(collect_messages(api_id, api_hash, session, folder, allowlist))
    state_name = "content_research_state.json" if args.content_research else "state.json"
    report_dir = "content-research-reports" if args.content_research else "reports"
    candidates = StateStore(root / ".ledovskikh" / state_name).process(messages)
    print(write_report(candidates, root / ".ledovskikh" / report_dir))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
