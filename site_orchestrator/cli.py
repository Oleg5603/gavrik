from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .core import ContractError, SiteOrchestrator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gavrik subordinate website orchestrator")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--work-order", help="JSON object; reads stdin when omitted")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.work_order if args.work_order is not None else sys.stdin.read())
        result = SiteOrchestrator(args.project_root).dispatch(payload)
    except (json.JSONDecodeError, ContractError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
