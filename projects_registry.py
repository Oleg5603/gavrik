"""
Реестр всех проектов пользователя — даёт Гаврику осведомлённость
и базовые команды управления (статус, git pull) по каждому.
"""
import asyncio
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Project:
    key: str
    name: str
    path: Path
    description: str
    is_git: bool = True


PROJECTS: list[Project] = [
    Project("jarvis-gold", "Jarvis Gold (монорепо)", Path(r"C:\Users\HP\Documents\Project"),
            "Основной рабочий репозиторий: подпроекты, боты, торговые советники"),
    Project("keen-lead-scoop", "Keen Lead Scoop", Path(r"C:\Users\HP\Documents\Project\keen-lead-scoop"),
            "Дашборд лидов, TanStack Start/React, Lovable.dev"),
    Project("jarvis-architect", "Jarvis Architect", Path(r"C:\Users\HP\jarvis-architect"),
            "Шаблон персонального AI-агента на Claude Code + Telegram-бот"),
    Project("graphify", "Graphify", Path(r"C:\Users\HP\graphify"),
            "Codebase → knowledge graph, PyPI-пакет, YC S26"),
    Project("sleep-cube", "Sleep Cube", Path(r"C:\Users\HP\sleep-cube"),
            "Android-приложение для сна, Kotlin/Compose"),
    Project("tkm", "ТКМ", Path(r"C:\Users\HP\tkm"),
            "Подбор точек ТКМ, Python десктоп + Flask веб"),
    Project("galactic-academy", "Galactic Academy", Path(r"C:\Users\HP\Проекты\galactic_academy"),
            "PDF-ридер с озвучкой голосами Star Wars"),
    Project("periph-eyes", "PeriphEyes", Path(r"C:\Users\HP\Проекты\oftalm\periph_eyes"),
            "Windows-оверлей для тренировки периферийного зрения"),
    Project("sibvaleo", "Sibvaleo", Path(r"C:\Users\HP\Проекты\sibvaleo"),
            "Flutter-приложение для консультантов Siberian Wellness"),
    Project("sniper-ea", "Sniper EA", Path(r"C:\Users\HP\Форекс\sniper_ea"),
            "Торговый советник MT4 по золоту (XAUUSD)"),
    Project("gavrik", "Гаврик (этот бот)", Path(r"C:\Users\HP\gavrik"),
            "Telegram-бот управления проектом Светланы Палкиной"),
]


def get_project(key: str) -> Project | None:
    return next((p for p in PROJECTS if p.key == key), None)


async def _run_git(path: Path, *args: str) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", str(path), *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode != 0:
            return ""
        return stdout.decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


async def get_status(project: Project) -> dict:
    """Короткий статус проекта: существует ли путь, ветка, последний коммит, есть ли незакоммиченное."""
    result = {"exists": project.path.exists(), "branch": "", "last_commit": "", "dirty": False, "has_git": False}
    if not result["exists"]:
        return result

    has_git = (project.path / ".git").exists()
    result["has_git"] = has_git
    if not has_git:
        return result

    branch = await _run_git(project.path, "rev-parse", "--abbrev-ref", "HEAD")
    last_commit = await _run_git(project.path, "log", "-1", "--format=%ad %s", "--date=short")
    dirty = await _run_git(project.path, "status", "--porcelain")

    result["branch"] = branch
    result["last_commit"] = last_commit
    result["dirty"] = bool(dirty)
    return result


async def pull(project: Project) -> str:
    if not (project.path / ".git").exists():
        return "Не git-репозиторий."
    return await _run_git(project.path, "pull") or "Нет изменений или ошибка pull."


def context_summary() -> str:
    """Компактное текстовое описание всех проектов — для системного промпта агента."""
    lines = ["Известные проекты пользователя (Олег, соло-разработчик 15+ side-проектов):"]
    for p in PROJECTS:
        lines.append(f"- {p.name} ({p.key}): {p.description} — путь: {p.path}")
    return "\n".join(lines)
