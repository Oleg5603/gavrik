from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any


class SiteStatus(str, Enum):
    QUEUED = "queued"
    PLANNING = "planning"
    BUILDING = "building"
    REVIEW = "review"
    BLOCKED = "blocked"
    READY_FOR_APPROVAL = "ready_for_approval"
    RELEASED = "released"
    FAILED = "failed"


@dataclass(frozen=True)
class SiteAgent:
    key: str
    title: str
    mission: str
    outputs: tuple[str, ...]
    gate: str | None = None


AGENTS = {
    agent.key: agent
    for agent in (
        SiteAgent("site_orchestrator", "Оркестратор сайтов", "Принимает задание только от Гаврика, маршрутизирует работу, объединяет артефакты и эскалирует решения.", ("plan", "assignments", "status", "handoff")),
        SiteAgent("strategy", "Исследователь-стратег", "Проверяет цель, аудиторию, конкурентов, аналитику, SEO-намерение, ограничения и критерии успеха; в discovery не строит продукт.", ("brief", "research", "success_metrics"), "discovery"),
        SiteAgent("experience", "UX/UI и контент-архитектор", "Проектирует IA, сценарии, состояния, адаптивную визуальную систему, доступность и содержание без шаблонной подмены материалов.", ("sitemap", "flows", "content_model", "design_spec"), "architecture"),
        SiteAgent("engineer", "Web-инженер", "Реализует минимальный поддерживаемый frontend и подключает backend только при доказанной необходимости.", ("source", "tests", "build_notes"), "implementation"),
        SiteAgent("quality", "Независимый контролёр качества", "Проверяет реальные пользовательские пути, кросс-браузерность, WCAG 2.2, производительность и регрессии; не принимает собственную реализацию.", ("qa_report", "a11y_report", "performance_report", "verdict"), "implementation"),
        SiteAgent("security_release", "Инженер безопасности и выпуска", "Проверяет OWASP, privacy, секреты, зависимости, SEO-технику, preview, rollback и мониторинг; выполняет выпуск только после разрешения.", ("security_report", "release_plan", "rollback_plan", "release_evidence"), "release"),
    )
}

COMMANDS = {
    "site.create", "site.audit", "site.resume", "site.status", "site.preview", "site.release"
}

COMMAND_ROUTES = {
    "site.create": ("strategy", "experience", "engineer", "quality", "security_release"),
    "site.audit": ("strategy", "experience", "quality", "security_release"),
    "site.resume": ("site_orchestrator",),
    "site.status": ("site_orchestrator",),
    "site.preview": ("engineer", "quality", "security_release"),
    "site.release": ("quality", "security_release"),
}

EXTERNAL_APPROVALS = {"publish", "preview_external", "domain", "paid_service", "external_message"}


class ContractError(ValueError):
    pass


class SiteOrchestrator:
    """Deterministic state and routing layer; execution remains with Gavrik/Codex."""

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.state_dir = self.project_root / ".site-orchestrator"
        self.state_path = self.state_dir / "state.json"
        self.events_path = self.state_dir / "events.jsonl"

    def dispatch(self, work_order: dict[str, Any]) -> dict[str, Any]:
        command = str(work_order.get("command", ""))
        if command not in COMMANDS:
            raise ContractError(f"Unsupported command: {command!r}")
        if not work_order.get("project_key"):
            raise ContractError("project_key is required")
        if not work_order.get("correlation_id"):
            raise ContractError("correlation_id is required")

        if command == "site.status":
            return self.load_state()

        approvals = set(work_order.get("approval_scope") or [])
        human_approval = bool(work_order.get("human_approval", False))
        requested_external = approvals & EXTERNAL_APPROVALS
        release_allowed = command != "site.release" or ("publish" in requested_external and human_approval)
        external_preview = command == "site.preview" and bool(work_order.get("external_preview"))
        preview_allowed = not external_preview or ("preview_external" in requested_external and human_approval)
        release_prepared = bool(work_order.get("release_prepared"))
        status = SiteStatus.PLANNING
        approvals_needed: list[dict[str, Any]] = []
        if command == "site.release" and not release_allowed:
            status = SiteStatus.READY_FOR_APPROVAL
            approvals_needed = [self._approval("publish")]
        elif command == "site.release":
            status = SiteStatus.RELEASED
        elif external_preview and not preview_allowed:
            status = SiteStatus.READY_FOR_APPROVAL
            approvals_needed = [self._approval("preview_external")]
        elif release_prepared:
            status = SiteStatus.READY_FOR_APPROVAL
            approvals_needed = [self._approval("publish")]
        elif command in {"site.preview", "site.audit"}:
            status = SiteStatus.REVIEW

        state = {
            "schema_version": 1,
            "parent": "gavrik",
            "project_key": work_order["project_key"],
            "correlation_id": work_order["correlation_id"],
            "command": command,
            "status": status.value,
            "phase": status.value,
            "percent": self._percent(status),
            "assignments": [
                self._assignment(key, index, COMMAND_ROUTES[command])
                for index, key in enumerate(COMMAND_ROUTES[command])
            ],
            "artifacts": self._artifacts(work_order.get("artifacts") or []),
            "checks": list(work_order.get("checks") or []),
            "findings": list(work_order.get("findings") or []),
            "evidence": list(work_order.get("evidence") or []),
            "approvals_needed": approvals_needed,
            "next_action": self._next_action(status),
            "updated_at": self._now(),
        }
        self._save_atomic(state)
        self._append_event({"type": "dispatch", **state})
        return state

    def load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {
                "schema_version": 1,
                "parent": "gavrik",
                "status": SiteStatus.QUEUED.value,
                "phase": "not_started",
                "percent": 0,
                "artifacts": [],
                "checks": [],
                "findings": [],
                "evidence": [],
                "approvals_needed": [],
                "next_action": "Send site.create or site.audit through Gavrik.",
            }
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _save_atomic(self, state: dict[str, Any]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temp_path = self.state_path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.state_path)

    def _append_event(self, event: dict[str, Any]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    @staticmethod
    def _approval(scope: str) -> dict[str, Any]:
        return {"scope": scope, "human_approval": True, "via": "gavrik"}

    @staticmethod
    def _assignment(key: str, index: int, route: tuple[str, ...]) -> dict[str, Any]:
        value = asdict(AGENTS[key])
        value["owner"] = key
        value["dependencies"] = [] if index == 0 else [route[index - 1]]
        return value

    @staticmethod
    def _artifacts(items: list[Any]) -> list[dict[str, Any]]:
        result = []
        for item in items:
            if isinstance(item, str):
                result.append({"type": "file", "path": item, "sha256": None})
            elif isinstance(item, dict):
                result.append(item)
            else:
                raise ContractError("artifacts must contain paths or objects")
        return result

    @staticmethod
    def _percent(status: SiteStatus) -> int:
        return {
            SiteStatus.QUEUED: 0,
            SiteStatus.PLANNING: 10,
            SiteStatus.BUILDING: 45,
            SiteStatus.REVIEW: 75,
            SiteStatus.BLOCKED: 0,
            SiteStatus.READY_FOR_APPROVAL: 95,
            SiteStatus.RELEASED: 100,
            SiteStatus.FAILED: 0,
        }[status]

    @staticmethod
    def _next_action(status: SiteStatus) -> str:
        if status == SiteStatus.READY_FOR_APPROVAL:
            return "Gavrik must request explicit publish approval from the owner."
        if status == SiteStatus.RELEASED:
            return "Return release evidence and monitoring status to Gavrik."
        if status == SiteStatus.REVIEW:
            return "Resolve critical/high findings before the next gate."
        return "Execute assignments, then return artifacts and checks to Gavrik."

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
