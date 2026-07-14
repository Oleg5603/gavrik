"""
Реестр всех проектов пользователя — даёт Гаврику осведомлённость
и базовые команды управления (статус, git pull) по каждому.
"""
import asyncio
import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DEPLOY_ROOT = "/root/gavrik-projects"


@dataclass
class Project:
    key: str
    name: str
    win_path: str
    description: str
    linux_path: str | None = None  # None = ещё не синхронизирован на VPS
    repo_url: str | None = None  # GitHub-репозиторий — если задан, бот может сам склонировать на VPS

    @property
    def path(self) -> Path | None:
        if os.name == "nt":
            return Path(self.win_path) if self.win_path else None
        if self.linux_path:
            return Path(self.linux_path)
        if self.repo_url:
            # Ещё не разворачивали на сервере, но знаем откуда клонировать —
            # это то место, куда ляжет проект после нажатия «Развернуть на сервере».
            return Path(DEFAULT_DEPLOY_ROOT) / self.key
        return None


PROJECTS: list[Project] = [
    Project("jarvis-gold", "Jarvis Gold (монорепо)", r"C:\Users\HP\Documents\Project",
            "Основной рабочий репозиторий: подпроекты, боты, торговые советники"),
    Project("keen-lead-scoop", "Keen Lead Scoop", r"C:\Users\HP\Documents\Project\keen-lead-scoop",
            "Дашборд лидов, TanStack Start/React, Lovable.dev",
            repo_url="https://github.com/Oleg5603/keen-lead-scoop.git"),
    Project("jarvis-architect", "Jarvis Architect", r"C:\Users\HP\jarvis-architect",
            "Не отдельный бот, а мастерская-субагент: набор скиллов Claude Code для установки новых "
            "агентов на VPS (server-setup), напоминаний (reminder) и разработки (discovery-interview, "
            "frontend-design, fullstack-developer). Также держит runbook для восстановления самого Гаврика "
            "(knowledge/gavrik-recovery.md) — Гавр использует его как справочник при сбоях.",
            linux_path="/root/jarvis-architect"),
    Project("graphify", "Graphify", r"C:\Users\HP\graphify",
            "Codebase → knowledge graph, PyPI-пакет, YC S26"),
    Project("sleep-cube", "Sleep Cube", r"C:\Users\HP\sleep-cube",
            "Android-приложение для сна, Kotlin/Compose",
            repo_url="https://github.com/Oleg5603/sleep-cube.git"),
    Project("tkm", "ТКМ", r"C:\Users\HP\tkm",
            "Подбор точек ТКМ, Python десктоп + Flask веб",
            repo_url="https://github.com/Oleg5603/tkm-acupuncture.git"),
    Project("galactic-academy", "Galactic Academy", r"C:\Users\HP\Проекты\galactic_academy",
            "PDF-ридер с озвучкой голосами Star Wars", linux_path="/home/agent/projects/galactic-academy"),
    Project("periph-eyes", "PeriphEyes", r"C:\Users\HP\Проекты\oftalm\periph_eyes",
            "Windows-оверлей для тренировки периферийного зрения", linux_path="/home/agent/projects/PeriphEyes"),
    Project("sibvaleo", "Sibvaleo", r"C:\Users\HP\Проекты\sibvaleo",
            "Flutter-приложение для консультантов Siberian Wellness", linux_path="/root/gavrik-projects/sibvaleo",
            repo_url="https://github.com/Oleg5603/sibvaleo.git"),
    Project("sniper-ea", "Sniper EA", r"C:\Users\HP\Форекс\sniper_ea",
            "Торговый советник MT4 по золоту (XAUUSD)"),
    Project("gavrik", "Гаврик (этот бот)", r"C:\Users\HP\gavrik",
            "Telegram-бот управления проектом Светланы Палкиной", linux_path="/root/gavrik"),
    Project("jurist", "Jurist", r"C:\Users\HP\Jurist",
            "Веб-приложение для частного юриста РФ: чат по праву, генерация документов, анализ договоров (FastAPI + OpenRouter)",
            repo_url="https://github.com/Oleg5603/Jurist.git"),
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
    result = {"exists": False, "branch": "", "last_commit": "", "dirty": False, "has_git": False, "synced": bool(project.path)}
    if project.path is None:
        return result
    result["exists"] = project.path.exists()
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
    if project.path is None:
        return "Проект ещё не синхронизирован на этой машине."
    if not (project.path / ".git").exists():
        return "Не git-репозиторий."
    return await _run_git(project.path, "pull") or "Нет изменений или ошибка pull."


async def deploy(project: Project) -> str:
    """Клонирует project.repo_url в project.path (только если ещё не там)."""
    if not project.repo_url:
        return "Для этого проекта не задан GitHub-репозиторий — клонировать некуда."
    if project.path is None:
        return "Не удалось определить путь для развёртывания."
    if (project.path / ".git").exists():
        return "Уже развёрнут — используй git pull."
    project.path.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", project.repo_url, str(project.path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        if proc.returncode != 0:
            return f"Ошибка клонирования:\n{stderr.decode('utf-8', errors='replace').strip()}"
        return f"Склонировано в {project.path}."
    except Exception as e:
        return f"Ошибка клонирования: {e}"


def context_summary() -> str:
    """Компактное текстовое описание всех проектов — для системного промпта агента."""
    lines = ["Известные проекты пользователя (Олег, соло-разработчик 15+ side-проектов):"]
    for p in PROJECTS:
        where = str(p.path) if p.path else f"{p.win_path} (на этой машине не синхронизирован)"
        lines.append(f"- {p.name} ({p.key}): {p.description} — путь: {where}")
    return "\n".join(lines)
