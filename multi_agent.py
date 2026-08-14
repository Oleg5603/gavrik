"""Formal role registry and workflow policy for Gavrik's software crew."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import json


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class AgentRole:
    key: str
    title: str
    mission: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    exit_condition: str

    def prompt(self) -> str:
        return (
            f"Ты — {self.title}. {self.mission}\n"
            f"Входы: {', '.join(self.inputs)}.\n"
            f"Выходы: {', '.join(self.outputs)}.\n"
            f"Условие завершения: {self.exit_condition}.\n"
            "Все замечания ранжируй: critical/high/medium/low. "
            "Не повторяй уже закрытые замечания из журнала изменений."
        )


def _role(key: str, title: str, mission: str, inputs: str, outputs: str, exit_condition: str) -> AgentRole:
    return AgentRole(key, title, mission, tuple(inputs.split("|")), tuple(outputs.split("|")), exit_condition)


ROLES = {
    role.key: role
    for role in (
        _role("orchestrator", "Оркестратор", "Управляй маршрутом работы, артефактами и эскалациями; не подменяй специалистов.", "запрос|состояние процесса|журнал", "следующий этап|назначения|статус", "каждому этапу назначена роль и нет незакрытого обязательного gate"),
        _role("planner", "Планировщик", "Уточни цель, ограничения, критерии приёмки, зависимости, риски и разбей работу на проверяемые этапы.", "требования|контекст", "план|критерии приёмки|риски", "все задачи имеют владельца, результат и критерий готовности"),
        _role("architect", "Архитектор / Проектировщик", "Спроектируй модули, интерфейсы, данные и прототип без преждевременной реализации.", "утверждённый план|ограничения", "архитектура|контракты|прототип", "решение полное, трассируется к требованиям и готово к challenge"),
        _role("challenger", "Адверсарий", "Атакуй план и дизайн по полноте, допущениям, сбоям, сложности, стоимости и эксплуатации.", "план|архитектура|журнал", "ранжированные возражения|вердикт", "нет незакрытых critical/high рисков или они эскалированы человеку"),
        _role("developer", "Разработчик", "Пиши минимальный поддерживаемый код по утверждённому дизайну в режиме feature, bugfix или iteration.", "план|архитектура|критерии", "код|миграции|технические заметки", "код собирается и готов к review и QA"),
        _role("reviewer", "Критик / Ревьюер", "Проверь соответствие плану, корректность, читаемость, производительность и архитектуру.", "diff|план|архитектура", "review|вердикт", "нет незакрытых blocking-комментариев и выдан Approved"),
        _role("qa", "Тестировщик QA", "Создай тест-стратегию и проверь функциональность, регрессию, интеграции и граничные случаи.", "критерии|сборка|код", "тесты|отчёт о дефектах|вердикт", "обязательные тесты пройдены, critical/high дефекты отсутствуют"),
        _role("designer", "Дизайнер", "Обеспечь понятный UI/UX, доступность и визуальную согласованность.", "сценарии|бренд|ограничения", "макеты|токены|спецификация", "макеты покрывают ключевые состояния и ошибки"),
        _role("copywriter", "Копирайтер", "Подготовь ясные тексты интерфейса и продукта в нужном тоне.", "аудитория|сценарии|tone of voice", "тексты|варианты|словарь", "все пользовательские состояния имеют понятный текст"),
        _role("ux_tester", "UX Тестировщик", "Оцени продукт глазами пользователя: понятность, скорость, ошибки и доступность.", "прототип|сценарии|аудитория", "UX-отчёт|проблемы|рекомендации", "критические препятствия пользовательскому сценарию устранены"),
        _role("security", "Security Auditor", "Проведи threat modeling и аудит OWASP, секретов, прав, зависимостей и журналирования.", "архитектура|код|конфигурация", "модель угроз|security findings|вердикт", "critical/high уязвимости исправлены или релиз заблокирован"),
        _role("protector", "Инженер по целостности", "Определи границы дозволенного, контролируй риски, обратимость и технический долг.", "решения|риски|журнал", "guardrails|реестр техдолга|решение об эскалации", "опасные действия требуют подтверждения, долг записан с владельцем и сроком"),
        _role("controller", "Контролёр", "Проверь нефункциональные требования: производительность, масштабирование, надёжность и законодательство.", "NFR|архитектура|результаты тестов", "NFR-отчёт|compliance findings|вердикт", "измеримые NFR выполнены, обязательные нормы соблюдены"),
    )
}


WORKFLOW = (
    "planner", "architect", "challenger", "developer", "reviewer", "qa",
    "security", "controller", "ux_tester", "protector",
)

QUALITY_GATES = {
    "architecture": ("challenger", "human_approval"),
    "implementation": ("reviewer", "qa"),
    "release": ("security", "controller", "protector", "human_approval"),
}


class IterationLimitError(RuntimeError):
    pass


class WorkflowState:
    """Small shared JSON journal. Artifacts themselves remain in the project tree."""

    def __init__(self, path: Path, max_iterations: int = 3):
        self.path = path
        self.max_iterations = max_iterations
        self.data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"iterations": {}, "findings": [], "approvals": [], "events": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def begin_iteration(self, cycle: str) -> int:
        count = int(self.data["iterations"].get(cycle, 0)) + 1
        if count > self.max_iterations:
            raise IterationLimitError(f"Цикл {cycle!r} превысил лимит {self.max_iterations}; нужен человек.")
        self.data["iterations"][cycle] = count
        self.data["events"].append({"type": "iteration", "cycle": cycle, "number": count})
        self.save()
        return count

    def gate_passed(self, gate: str) -> bool:
        required = QUALITY_GATES[gate]
        approvals = set(self.data["approvals"])
        blockers = any(f.get("status") == "open" and f.get("severity") in {"critical", "high"} for f in self.data["findings"])
        return not blockers and all(item in approvals for item in required)


def orchestrator_context() -> str:
    names = ", ".join(role.title for role in ROLES.values())
    return (
        "Многоагентная команда разработки: " + names + ". "
        "Маршрут: " + " → ".join(WORKFLOW) + ". "
        "Максимум 3 итерации в каждом цикле; затем обязательная эскалация человеку. "
        "Архитектура и релиз требуют human approval; critical/high замечания блокируют следующий gate."
    )
