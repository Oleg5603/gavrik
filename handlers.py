import base64
import logging
import subprocess
import asyncio
import sys
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path
import aiohttp
from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, FSInputFile, BufferedInputFile
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import (
    VK_TOKEN, VK_GROUP_ID, SITE_URL,
    CONTENT_PLAN_PATH, DIRECT_CSV_PATH, LANDING_DIR, ALLOWED_USER_IDS,
    VPS_HOST, VPS_USER, VPS_PASSWORD, CLAUDE_BIN, AGENT_PROVIDER, CODEX_BIN, BASE_DIR,
    ANTHROPIC_API_KEY, ANTHROPIC_MODEL, OLEG_TG_CHANNEL,
    YANDEX_ART_FOLDER_ID, YANDEX_ART_API_KEY, UPLOADS_DIR,
)
import json as _json_mod
from memory_graph import MemoryGraph
import projects_registry as _projects
import vk_lead_parser as _lead_parser
import media as _media

_memory = MemoryGraph(BASE_DIR / "knowledge_graph.jsonl")
_SESSIONS_FILE = BASE_DIR / "sessions.json"

log = logging.getLogger(__name__)
router = Router()

# Режимы и история — загружаются из файла, переживают перезапуск
_history: dict[int, list]
_agent_mode: set[int]
_coach_mode: set[int]


def _load_state() -> tuple[dict[int, list], set[int], set[int]]:
    """Загружает историю и активные режимы из файла."""
    try:
        if _SESSIONS_FILE.exists():
            data = _json_mod.loads(_SESSIONS_FILE.read_text(encoding="utf-8"))
            history = {int(k): v for k, v in data.get("history", {}).items()}
            agent = set(int(x) for x in data.get("agent_mode", []))
            coach = set(int(x) for x in data.get("coach_mode", []))
            return history, agent, coach
    except Exception as e:
        log.warning("Не удалось загрузить sessions.json: %s", e)
    return {}, set(), set()


def _save_history():
    try:
        _SESSIONS_FILE.write_text(
            _json_mod.dumps({
                "history": {str(k): v for k, v in _history.items()},
                "agent_mode": list(_agent_mode),
                "coach_mode": list(_coach_mode),
            }, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        log.warning("Не удалось сохранить sessions.json: %s", e)


# История и режимы — персистентные, переживают перезапуск бота
_history, _agent_mode, _coach_mode = _load_state()

AGENT_SYSTEM = (
    "Ты — Гаврик, умный персональный ИИ-ассистент и главный оркестратор проектов Олега. "
    "Отвечаешь чётко, по делу, на русском языке. "
    "Помнишь контекст разговора и используешь его в ответах.\n\n"
    + _projects.context_summary() + "\n\n"
    "Если пользователь спрашивает про статус/прогресс любого из этих проектов "
    "или просит что-то по ним сделать — используй эти сведения и команду /projects.\n\n"
    "Jarvis Architect (jarvis-architect) — твой субагент-мастерская: если пользователь просит "
    "развернуть нового агента на VPS, настроить напоминания или разработать что-то с нуля, "
    "укажи, что за это отвечают скиллы jarvis-architect (server-setup, reminder, discovery-interview, "
    "frontend-design, fullstack-developer), а не берись выполнять это сам."
)

COACH_SYSTEM = (
    "Ты — коуч по финансовой эффективности и личному росту.\n\n"

    "КТО ТЫ:\n"
    "Ты партнёр клиента, а не консультант. Ты НЕ даёшь готовых решений — "
    "ты задаёшь точные вопросы, которые помогают клиенту самому найти ответ. "
    "Совершенно не важно у кого родился ответ — у тебя или у клиента. "
    "Когда людей слышат и понимают — они движутся вперёд. "
    "Большинство людей используют 1% своего потенциала — коучинг раскрывает остальные 99%.\n\n"

    "ПРИНЦИПЫ РАБОТЫ:\n"
    "• Сначала выясни что беспокоит — только потом переходи к целям\n"
    "• Задавай открытые вопросы направленные в будущее\n"
    "• Работай только с цифрами и фактами клиента — никаких абстракций\n"
    "• Вещи которые человек терпит — отбирают энергию и мешают двигаться вперёд: сначала устрани их\n"
    "• Фиксируй договорённости — подотчётность это главная ценность коучинга\n"
    "• Не давай советов пока не получил ответы на вопросы\n\n"

    "ИНСТРУМЕНТЫ — выбирай по запросу:\n"
    "• Колесо баланса — оцени 8 сфер жизни/бизнеса по шкале 1-10, найди самую просевшую\n"
    "• Шкала 1-10 — для замера ясности, уверенности, прогресса\n"
    "• Формат конечного результата — когда цель ясна но нет плана действий\n"
    "• Перенос в будущее — 'Представь: цель достигнута. Что изменилось? Что ты сделал?'\n"
    "• Декартовы координаты — когда нужно выбрать одно из двух (4 вопроса про каждый вариант)\n"
    "• Пирамида логических уровней — когда цель непонятна или есть внутреннее сопротивление\n"
    "• Список 20 вещей которые терпишь — вскрыть энергодренажи\n\n"

    "СТРУКТУРА ПЕРВОЙ ВСТРЕЧИ (если клиент новый):\n"
    "1. Что приходится терпеть — список энергодренажей\n"
    "2. 5 конкретных измеримых результатов на 90 дней\n"
    "3. 3 глобальных изменения которые нужны для успеха\n"
    "4. Одно обязательство — первый шаг прямо сейчас\n\n"

    "Никаких банальностей. Отвечай по-русски, кратко и по делу. "
    "Когда клиент даёт цифры — работай с ними.\n\n"
)

# Хранилище chat_id для уведомлений (в памяти, при перезапуске сбрасывается)
_notify_chats: set[int] = set()

STAGES = [
    ("1", "Лендинг", "✅", "palkina-therapy.ru запущен, Метрика, цели"),
    ("2", "Яндекс.Директ", "⏸", "CSV готов — ждёт бюджета"),
    ("3", "ВКонтакте", "🔄", "Группа misemia, контент-план 12 постов, svet_bot"),
    ("4", "Парсинг аудитории ВК", "🔄", "Парсер готов, по всей России (9 групп), валидация по активности"),
    ("5", "Telegram svet_bot", "⚠️", "Код готов — нужен токен @LanaS777Bot"),
    ("6", "Яндекс Метрика", "✅", "Счётчик 109801157, цель form_submit"),
    ("7", "Прогрев контент", "⏳", "Серия прогревающих постов — не начат"),
    ("8", "A/B тесты", "⏳", "Оптимизация — не начат"),
]

TASKS = [
    ("svet_bot TELEGRAM_TOKEN", "Получить: @BotFather → /mybots → @LanaS777Bot → API Token"),
    ("svet_bot ALLOWED_USER_IDS", "Написать @userinfobot — узнать Telegram ID Светланы"),
    ("Фото на сайт", "Выбрать из G:\\ФОТО\\Света → скопировать как landing/photo.jpg → залить на Beget"),
    ("Отзывы на сайт", "Заменить 5 заглушек в index.html реальными отзывами Светланы"),
    ("Запустить svet_bot", "В папке semantic_scout: python svet_bot/bot.py"),
    ("ВК посты", "Публиковать по плану: пн 10:00, ср 12:00, пт 18:00"),
    ("Яндекс.Директ", "Загрузить output/direct_campaign.csv при наличии бюджета"),
    ("Парсинг аудитории ВК", "Этап 4"),
    ("Прогрев контент", "Этап 7 — серия прогревающих постов"),
    # --- ВК-продвижение (органика, 0 бюджет) ---
    ("✅ SEO описание misemia", "СДЕЛАНО 21.06 — ключи: психолог Чайковский, семейный консультант, помощь при разводе"),
    ("Личная страница Светланы", "Добавить ссылку на misemia в шапку личной страницы ВК + включить репосты постов группы"),
    ("Звонок юристу", "vk.com/oleneva.elena или vk.com/jur_chaik — предложить взаимные рекомендации"),
    ("Комментарий эксперта (ежедневно)", "Бот присылает посты → Светлана отвечает на 1 пост живым советом. Без рекламы, только помощь"),
    ("История клиентки", "Попросить клиентку написать анонимный пост в baby59ru: 'Нашла консультанта в Чайковском...'"),
]

VK_POSTS = [
    ("1 (Пн, нед.1)", "Знакомство", "Кто я и почему работаю именно с парами"),
    ("2 (Ср, нед.1)", "Полезное", "Почему пары откладывают обращение к психологу"),
    ("3 (Пт, нед.1)", "Миф", "Миф: к психологу идут только когда совсем плохо"),
    ("4 (Пн, нед.2)", "История", "Как вышли из двухлетней холодности"),
    ("5 (Ср, нед.2)", "Практика", "3 признака, что кризис в браке — не конец"),
    ("6 (Пт, нед.2)", "Вопрос-ответ", "Можно ли прийти на сессию одному, без партнёра?"),
    ("7 (Пн, нед.3)", "Измена", "5 вопросов до решения об измене"),
    ("8 (Ср, нед.3)", "Онлайн", "Онлайн-терапия vs очная — что выбрать паре"),
    ("9 (Пт, нед.3)", "Конфликты", "Почему «просто поговорить» не работает"),
    ("10 (Пн, нед.4)", "Запись", "Что происходит на первой сессии"),
    ("11 (Ср, нед.4)", "Цена", "Стоимость сессии vs стоимость развода"),
    ("12 (Пт, нед.4)", "Близость", "Можно ли вернуть эмоциональную близость"),
]


def _auth(message: Message) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    return message.from_user.id in ALLOWED_USER_IDS


async def _safe_answer(message: Message, text: str, **kwargs):
    """message.answer() с фолбэком на обычный текст.

    ИИ-сгенерированный текст иногда содержит незакрытую Markdown-разметку
    (одинокая * или _) — Telegram тогда отвечает TelegramBadRequest
    "can't parse entities", и если это не поймать, исключение убивает весь
    процесс бота (aiogram не перехватывает ошибки хендлеров сам), из-за чего
    бот "молчит" несколько секунд на рестарте. Вместо падения — шлём тем же
    текстом без разметки.
    """
    try:
        await message.answer(text, **kwargs)
    except TelegramBadRequest as e:
        if "can't parse entities" in str(e):
            log.warning("Markdown не распарсился, шлю как обычный текст: %s", e)
            await message.answer(text, parse_mode=None, **{k: v for k, v in kwargs.items() if k != "parse_mode"})
        else:
            raise


async def _safe_edit(message: Message, text: str, **kwargs):
    """Как _safe_answer, но для edit_text — тот же риск невалидного
    Markdown в ИИ-сгенерированном тексте карточек ContentZavod."""
    try:
        await message.edit_text(text, **kwargs)
    except TelegramBadRequest as e:
        if "can't parse entities" in str(e):
            log.warning("Markdown не распарсился при edit_text, шлю как обычный текст: %s", e)
            await message.edit_text(text, parse_mode=None, **{k: v for k, v in kwargs.items() if k != "parse_mode"})
        else:
            raise


def _coach_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="⚖️ Колесо баланса", callback_data="coach_ask_wheel")
    kb.button(text="🚫 Что вы терпите", callback_data="coach_ask_tolerations")
    kb.button(text="🎯 Цели на 90 дней", callback_data="coach_ask_90days")
    kb.button(text="🔀 Помоги выбрать", callback_data="coach_ask_choice")
    kb.button(text="📊 Анализ финансов", callback_data="coach_ask_audit")
    kb.button(text="📈 Рост дохода", callback_data="coach_ask_growth")
    kb.button(text="💡 Эффективность", callback_data="coach_ask_eff")
    kb.button(text="💰 Пассивный доход", callback_data="coach_ask_passive")
    kb.button(text="🧠 Мышление миллионера", callback_data="coach_ask_mindset")
    kb.button(text="❌ Выйти из коуча", callback_data="coach_exit")
    kb.adjust(2)
    return kb.as_markup()


def _main_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Этапы", callback_data="stages")
    kb.button(text="🌐 Сайт", callback_data="site")
    kb.button(text="📱 ВК", callback_data="vk")
    kb.button(text="📅 Контент-план", callback_data="plan")
    kb.button(text="✅ Задачи", callback_data="tasks")
    kb.button(text="🚀 Управление", callback_data="manage")
    kb.button(text="🤖 Агент", callback_data="agent_mode")
    kb.button(text="💼 Коуч", callback_data="coach_mode")
    kb.button(text="🗂 Все проекты", callback_data="projects")
    kb.adjust(2)
    return kb.as_markup()


@router.message(Command("start"))
async def cmd_start(message: Message):
    if not _auth(message):
        return
    _notify_chats.add(message.chat.id)
    await message.answer(
        "*Гаврик* — центр управления проектом Светланы Палкиной\n\n"
        "Выбери раздел:",
        reply_markup=_main_kb()
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    if not _auth(message):
        return
    await message.answer("Главное меню:", reply_markup=_main_kb())


# ───── ЭТАПЫ ─────

@router.message(Command("stages"))
async def cmd_stages(message: Message):
    if not _auth(message):
        return
    await _send_stages(message)


@router.callback_query(F.data == "stages")
async def cb_stages(callback: CallbackQuery):
    await _send_stages(callback.message)
    await callback.answer()


async def _send_stages(message: Message):
    lines = ["Этапы проекта palkina-therapy.ru\n"]
    for num, name, icon, desc in STAGES:
        lines.append(f"{icon} Этап {num}: {name}\n   {desc}\n")
    await message.answer("\n".join(lines), parse_mode=None)


# ───── САЙТ ─────

@router.message(Command("site"))
async def cmd_site(message: Message):
    if not _auth(message):
        return
    await _send_site(message)


@router.callback_query(F.data == "site")
async def cb_site(callback: CallbackQuery):
    await _send_site(callback.message)
    await callback.answer()


async def _send_site(message: Message):
    wait = await message.answer("Проверяю сайт...")
    ok = await _check_site()
    landing_files = sorted(f.name for f in LANDING_DIR.iterdir()) if LANDING_DIR.exists() else []
    text = (
        f"{'✅ Сайт работает' if ok else '❌ Сайт недоступен'}\n\n"
        f"*URL:* {SITE_URL}\n"
        f"*Хостинг:* Beget (ogp56bkn)\n"
        f"*Метрика:* 109801157\n"
        f"*Цель:* form\\_submit\n"
        f"*Calendly:* https://calendly.com/palkinoleg\n\n"
        f"*Файлы лендинга:*\n"
        + "\n".join(f"  • {f}" for f in landing_files)
    )
    await wait.delete()
    await message.answer(text)


# ───── ВКОНТАКТЕ ─────

@router.message(Command("vk"))
async def cmd_vk(message: Message):
    if not _auth(message):
        return
    await _send_vk(message)


@router.callback_query(F.data == "vk")
async def cb_vk(callback: CallbackQuery):
    await _send_vk(callback.message)
    await callback.answer()


async def _send_vk(message: Message):
    wait = await message.answer("Запрашиваю данные ВК...")
    info = await _get_vk_stats()
    await wait.delete()
    if info:
        text = (
            f"*ВКонтакте — misemia*\n\n"
            f"Подписчиков: *{info.get('members_count', '?')}*\n"
            f"Название: {info.get('name', '?')}\n"
            f"Статус: {info.get('status', '—') or '—'}\n\n"
            f"Группа: vk.com/misemia\n"
            f"Бот: @LanaS777Bot\n\n"
            f"*Расписание постов:*\n"
            f"  Пн 10:00 · Ср 12:00 · Пт 18:00\n\n"
            f"Чтобы создать пост: /newpost"
        )
    else:
        text = "❓ Нет данных ВК — проверь VK\\_TOKEN в .env"
    await message.answer(text)


# ───── КОНТЕНТ-ПЛАН ─────

@router.message(Command("plan"))
async def cmd_plan(message: Message):
    if not _auth(message):
        return
    await _send_plan(message)


@router.callback_query(F.data == "plan")
async def cb_plan(callback: CallbackQuery):
    await _send_plan(callback.message)
    await callback.answer()


async def _send_plan(message: Message):
    lines = ["*Контент-план ВКонтакте (12 постов, 4 недели)*\n"]
    for num, topic, title in VK_POSTS:
        lines.append(f"*{num}* — {topic}: {title}")
    lines.append("\n📄 Полный план: vk\\_content/content\\_plan.md")
    lines.append("Создать пост: /newpost")
    await message.answer("\n".join(lines))


# ───── ЗАДАЧИ ─────

@router.message(Command("tasks"))
async def cmd_tasks(message: Message):
    if not _auth(message):
        return
    await _send_tasks(message)


@router.callback_query(F.data == "tasks")
async def cb_tasks(callback: CallbackQuery):
    await _send_tasks(callback.message)
    await callback.answer()


async def _send_tasks(message: Message):
    lines = [f"Открытые задачи ({len(TASKS)})\n"]
    for i, (name, desc) in enumerate(TASKS, 1):
        lines.append(f"{i}. {name}\n   {desc}\n")
    await message.answer("\n".join(lines), parse_mode=None)


# ───── УПРАВЛЕНИЕ ─────

@router.message(Command("manage"))
async def cmd_manage(message: Message):
    if not _auth(message):
        return
    await _send_manage(message)


@router.callback_query(F.data == "manage")
async def cb_manage(callback: CallbackQuery):
    await _send_manage(callback.message)
    await callback.answer()


async def _send_manage(message: Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="🌐 Проверить сайт", callback_data="site")
    kb.button(text="📱 Статистика ВК", callback_data="vk")
    kb.button(text="✍️ Создать пост ВК", callback_data="newpost_menu")
    kb.button(text="📊 Все этапы", callback_data="stages")
    kb.button(text="✅ Задачи", callback_data="tasks")
    kb.adjust(2)
    text = (
        "*Управление проектом*\n\n"
        "Доступные команды:\n"
        "/site — проверить сайт\n"
        "/vk — статистика ВКонтакте\n"
        "/newpost — создать пост в ВК\n"
        "/stages — статус всех этапов\n"
        "/tasks — список задач\n"
        "/notify on|off — вкл/выкл уведомления\n"
        "/status — краткий статус всех проектов\n"
        "/projects — все проекты Олега (статус, git pull)"
    )
    await message.answer(text, reply_markup=kb.as_markup())


# ───── НОВЫЙ ПОСТ ─────

@router.message(Command("newpost"))
async def cmd_newpost(message: Message):
    if not _auth(message):
        return
    await _send_newpost_menu(message)


@router.callback_query(F.data == "newpost_menu")
async def cb_newpost_menu(callback: CallbackQuery):
    await _send_newpost_menu(callback.message)
    await callback.answer()


async def _send_newpost_menu(message: Message):
    kb = InlineKeyboardBuilder()
    for i, (num, topic, title) in enumerate(VK_POSTS):
        kb.button(text=f"Пост {num}: {topic}", callback_data=f"post_{i}")
    kb.adjust(2)
    await message.answer(
        "*Выбери пост из плана для публикации:*\n\n"
        "Гаврик покажет текст — ты его правишь и публикуешь через svet\\_bot\n"
        "или вручную на vk.com/misemia",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data.startswith("post_"))
async def cb_post_detail(callback: CallbackQuery):
    idx = int(callback.data.split("_")[1])
    num, topic, title = VK_POSTS[idx]
    post_texts = _get_post_template(idx)
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Скопировать текст поста", callback_data=f"copy_{idx}")
    kb.button(text="🔙 Назад к плану", callback_data="plan")
    kb.adjust(1)
    await callback.message.answer(
        f"*Пост {num} — {topic}*\n"
        f"_{title}_\n\n"
        f"{post_texts}",
        reply_markup=kb.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("copy_"))
async def cb_copy_post(callback: CallbackQuery):
    idx = int(callback.data.split("_")[1])
    num, topic, title = VK_POSTS[idx]
    text = _get_post_template(idx)
    await callback.message.answer(
        f"Готово к копированию:\n\n{text}",
    )
    await callback.answer("Текст отправлен")


# ───── СТАТУС ─────

@router.message(Command("status"))
async def cmd_status(message: Message):
    if not _auth(message):
        return
    wait = await message.answer("Проверяю...")
    site_ok = await _check_site()
    vk_info = await _get_vk_stats()
    await wait.delete()

    svet_ok = _check_env_key("svet_bot/.env", "TELEGRAM_TOKEN")
    direct_ok = DIRECT_CSV_PATH.exists()

    lines = [
        "*Статус проектов*\n",
        f"{'✅' if site_ok else '❌'} Сайт {SITE_URL}",
        f"{'✅' if vk_info else '❓'} ВК misemia — {vk_info.get('members_count', '?') if vk_info else '?'} подписчиков",
        f"{'✅' if svet_ok else '⚠️'} svet_bot — {'токен задан' if svet_ok else 'нужен токен'}",
        f"{'✅' if direct_ok else '⏸'} Яндекс.Директ — {'CSV готов' if direct_ok else 'ждёт бюджета'}",
        f"\n📊 /stages — подробно по этапам",
        f"✅ /tasks — {len(TASKS)} задач открыто",
    ]
    await message.answer("\n".join(lines))


# ───── ВСЕ ПРОЕКТЫ ─────

@router.message(Command("projects"))
async def cmd_projects(message: Message):
    if not _auth(message):
        return
    await _send_projects(message)


@router.callback_query(F.data == "projects")
async def cb_projects(callback: CallbackQuery):
    await _send_projects(callback.message)
    await callback.answer()


async def _send_projects(message: Message):
    kb = InlineKeyboardBuilder()
    for p in _projects.PROJECTS:
        kb.button(text=p.name, callback_data=f"proj_{p.key}")
    kb.adjust(2)
    await message.answer(
        f"*Все проекты ({len(_projects.PROJECTS)})*\n\nВыбери проект для статуса и управления:",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data.startswith("proj_"))
async def cb_project_detail(callback: CallbackQuery):
    key = callback.data.split("_", 1)[1]
    project = _projects.get_project(key)
    if not project:
        await callback.answer("Проект не найден")
        return
    wait = await callback.message.answer("Проверяю...")
    status = await _projects.get_status(project)
    await wait.delete()

    can_deploy = False
    if not status["synced"]:
        text = (
            f"*{project.name}*\n{project.description}\n\n"
            f"🚫 Не синхронизирован на этой машине (путь на ПК: `{project.win_path}`)"
        )
    elif not status["exists"] and project.repo_url:
        can_deploy = True
        text = (
            f"*{project.name}*\n{project.description}\n\n"
            f"📦 Ещё не развёрнут на сервере (репозиторий известен: `{project.repo_url}`)\n"
            f"Нажми «Развернуть на сервере», чтобы склонировать в `{project.path}`."
        )
    elif not status["exists"]:
        text = f"*{project.name}*\n\n❌ Путь не найден: `{project.path}`"
    elif not status["has_git"]:
        text = (
            f"*{project.name}*\n{project.description}\n\n"
            f"📁 `{project.path}`\n⚠️ Не git-репозиторий"
        )
    else:
        text = (
            f"*{project.name}*\n{project.description}\n\n"
            f"📁 `{project.path}`\n"
            f"🌿 Ветка: {status['branch'] or '?'}\n"
            f"📝 Последний коммит: {status['last_commit'] or '?'}\n"
            f"{'🔶 Есть незакоммиченные изменения' if status['dirty'] else '✅ Всё закоммичено'}"
        )

    kb = InlineKeyboardBuilder()
    if can_deploy:
        kb.button(text="🚀 Развернуть на сервере", callback_data=f"projdeploy_{project.key}")
    if status["has_git"]:
        kb.button(text="⬇️ git pull", callback_data=f"projpull_{project.key}")
    kb.button(text="🔙 Ко всем проектам", callback_data="projects")
    kb.adjust(1)
    await callback.message.answer(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("projdeploy_"))
async def cb_project_deploy(callback: CallbackQuery):
    key = callback.data.split("_", 1)[1]
    project = _projects.get_project(key)
    if not project:
        await callback.answer("Проект не найден")
        return
    wait = await callback.message.answer(f"🚀 Разворачиваю {project.name} на сервере...")
    result = await _projects.deploy(project)
    await wait.delete()
    await callback.message.answer(f"*{project.name}* — результат развёртывания:\n\n```\n{result}\n```")
    await callback.answer()


@router.callback_query(F.data.startswith("projpull_"))
async def cb_project_pull(callback: CallbackQuery):
    key = callback.data.split("_", 1)[1]
    project = _projects.get_project(key)
    if not project:
        await callback.answer("Проект не найден")
        return
    wait = await callback.message.answer(f"⬇️ git pull {project.name}...")
    result = await _projects.pull(project)
    await wait.delete()
    await callback.message.answer(f"*{project.name}* — результат pull:\n\n```\n{result}\n```")
    await callback.answer()


# ───── УВЕДОМЛЕНИЯ ─────

@router.message(Command("notify"))
async def cmd_notify(message: Message):
    if not _auth(message):
        return
    parts = message.text.split()
    arg = parts[1].lower() if len(parts) > 1 else ""
    if arg == "on":
        _notify_chats.add(message.chat.id)
        await message.answer("✅ Уведомления включены.\nТы будешь получать сигналы о новых заявках и публикациях.")
    elif arg == "off":
        _notify_chats.discard(message.chat.id)
        await message.answer("🔕 Уведомления отключены.")
    else:
        status = "включены ✅" if message.chat.id in _notify_chats else "отключены 🔕"
        await message.answer(
            f"Уведомления сейчас: *{status}*\n\n"
            "/notify on — включить\n"
            "/notify off — отключить"
        )


async def send_notification(bot, text: str):
    """Вызвать извне для отправки уведомлений во все подписанные чаты."""
    for chat_id in list(_notify_chats):
        try:
            await bot.send_message(chat_id, f"🔔 {text}")
        except Exception as e:
            log.warning("Не удалось отправить уведомление в %s: %s", chat_id, e)


# ───── ПОМОЩЬ ─────

@router.message(Command("help"))
async def cmd_help(message: Message):
    if not _auth(message):
        return
    await message.answer(
        "*Команды Гаврика*\n\n"
        "/start — главное меню\n"
        "/status — краткий статус всех проектов\n"
        "/stages — этапы (1–8) с иконками\n"
        "/site — проверить сайт\n"
        "/vk — статистика ВКонтакте\n"
        "/plan — контент-план (12 постов)\n"
        "/newpost — создать пост из плана\n"
        "/tasks — открытые задачи\n"
        "/manage — панель управления\n"
        "/projects — все проекты Олега (статус, git pull)\n"
        "/notify on|off — уведомления\n"
        "/coach — финансовый коуч\n"
        "/leads [группы|города] — парсинг аудитории ВК по всей России, фильтр опционален (Этап 4)\n"
        "/help — эта справка"
    )


# ───── ПАРСИНГ АУДИТОРИИ ВК (Этап 4) ─────

_LEADS_OUT_PATH = str(BASE_DIR / "leads.csv")


@router.message(Command("leads"))
async def cmd_leads(message: Message):
    """
    /leads misemia,other_group|Чайковский,Пермь
    Часть до "|" — группы-доноры через запятую, часть после — города-фильтр
    (можно опустить вместе с "|" — тогда без фильтра по городу).
    Без аргументов — группа по умолчанию (VK_GROUP_ID проекта), без фильтра.
    """
    if not _auth(message):
        return
    if not VK_TOKEN:
        await message.answer("❌ VK_TOKEN не задан в .env — парсинг недоступен.")
        return

    raw = message.text.partition(" ")[2].strip()
    if raw:
        groups_part, _, cities_part = raw.partition("|")
        groups = [g.strip() for g in groups_part.split(",") if g.strip()]
        cities = [c.strip() for c in cities_part.split(",") if c.strip()] or None
    else:
        groups = [str(VK_GROUP_ID)]
        cities = None

    wait = await message.answer(f"🔍 Парсю аудиторию ({', '.join(groups)})... (0с)")

    done_event = asyncio.Event()
    async def _ticker():
        elapsed = 0
        while not done_event.is_set():
            await asyncio.sleep(10)
            if done_event.is_set():
                break
            elapsed += 10
            try:
                await wait.edit_text(f"🔍 Парсю аудиторию ({', '.join(groups)})... ({elapsed}с)")
            except Exception:
                pass
    ticker_task = asyncio.create_task(_ticker())

    def _run_parser() -> tuple[int, int, int, int, str | None]:
        all_leads = []
        for raw_group in groups:
            try:
                group_id = _lead_parser.resolve_group_id(raw_group)
                all_leads.extend(_lead_parser.fetch_group_members(group_id, source_label=raw_group))
            except Exception as e:
                log.warning("lead-parser: группа '%s' пропущена: %s", raw_group, e)
        filtered = _lead_parser.filter_leads(all_leads, cities, max_days_inactive=30)
        deduped = _lead_parser.dedup_leads(filtered)
        if not deduped:
            return len(all_leads), 0, 0, 0, None
        _lead_parser.write_csv(deduped, _LEADS_OUT_PATH)
        return len(all_leads), len(filtered), len(deduped), len(deduped), _LEADS_OUT_PATH

    try:
        total, after_filter, deduped_count, valid_count, out_path = await asyncio.get_event_loop().run_in_executor(
            None, _run_parser
        )
    except Exception as e:
        done_event.set()
        ticker_task.cancel()
        await wait.edit_text(f"❌ Ошибка парсинга: {e}")
        return
    finally:
        done_event.set()
        ticker_task.cancel()

    await wait.delete()
    scope_text = "всей России" if not cities else f"городах: {', '.join(cities)}"
    await message.answer(
        f"✅ *Готово по {scope_text}*\n\n"
        f"Собрано: {total}\n"
        f"После фильтра город/активность: {after_filter}\n"
        f"После дедупликации: {deduped_count}\n"
        f"Валидных (готово к контакту): {valid_count}"
    )
    if out_path:
        await message.answer_document(FSInputFile(out_path), caption="leads.csv — потенциальные клиенты Светланы")
    else:
        await message.answer("Никого не осталось после фильтра — попробуй без фильтра городов или другие группы.")


# ───── CONTENTZAVOD — публикация в Telegram (Фаза 4, только ТГ) ─────
# ВК публикуется вручную (см. content_zavod/clients/oleg/platforms.md —
# VK-токен заблокирован модерацией VK, не наш баг).
#
# Одобрение ставит пост в очередь на публикацию (1/день в CZ_DAILY_HOUR:00,
# будни), а не публикует мгновенно — решено 2026-07-17. Фоновый шедулер
# в bot.py разбирает очередь. Картинка (Kandinsky/FusionBrain) генерируется
# сразу при одобрении, чтобы сбой генерации был виден сейчас, а не молча
# в 10 утра без присмотра.

_CZ_DIR = BASE_DIR / "content_zavod"
CZ_DAILY_HOUR = 10  # публикация в 10:00, см. решение пользователя 2026-07-17


def _cz_latest_drafts_path(client: str):
    drafts_dir = _CZ_DIR / "clients" / client / "drafts"
    candidates = sorted(drafts_dir.glob("drafts_final_*.json")) if drafts_dir.exists() else []
    return candidates[-1] if candidates else None


def _cz_publish_state_path(client: str):
    return _CZ_DIR / "clients" / client / "drafts" / "publish_state.json"


def _cz_load_publish_state(client: str, batch_filename: str) -> dict:
    path = _cz_publish_state_path(client)
    if not path.exists():
        return {}
    data = _json_mod.loads(path.read_text(encoding="utf-8"))
    if data.get("file") != batch_filename:
        return {}  # новая пачка недели — прошлые решения не применимы
    return data.get("decisions", {})


def _cz_save_publish_state(client: str, batch_filename: str, decisions: dict):
    _cz_publish_state_path(client).write_text(
        _json_mod.dumps({"file": batch_filename, "decisions": decisions}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _cz_next_slot(decisions: dict) -> datetime:
    """Следующий свободный будний день в CZ_DAILY_HOUR:00 — пропускает
    сб/вс (см. VK_PROMOTION_REQUIREMENTS: окна для аудитории предпринимателей
    только в будни) и не занятые другими scheduled/published слотами даты."""
    taken_dates = set()
    for d in decisions.values():
        if isinstance(d, dict) and d.get("at"):
            taken_dates.add(datetime.fromisoformat(d["at"]).date())

    now = datetime.now()
    candidate = now.date()
    if now.time() >= dt_time(CZ_DAILY_HOUR, 0):
        candidate += timedelta(days=1)

    while candidate.weekday() >= 5 or candidate in taken_dates:  # 5=сб, 6=вс
        candidate += timedelta(days=1)

    return datetime.combine(candidate, dt_time(CZ_DAILY_HOUR, 0))


_YANDEX_ART_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/imageGenerationAsync"
_YANDEX_OPERATIONS_URL = "https://llm.api.cloud.yandex.net/operations/"


async def _cz_generate_image(prompt: str) -> bytes | None:
    """YandexART (Yandex Cloud AI Studio) — обложка к посту. Возвращает
    None при отсутствии ключей или ошибке (публикация не должна падать
    целиком из-за картинки — просто уйдёт текстом). Переключились с
    Kandinsky/FusionBrain 2026-07-17 — тот сайт был недоступен."""
    if not YANDEX_ART_FOLDER_ID or not YANDEX_ART_API_KEY:
        return None
    headers = {"Authorization": f"Api-Key {YANDEX_ART_API_KEY}"}
    payload = {
        "modelUri": f"art://{YANDEX_ART_FOLDER_ID}/yandex-art/latest",
        "generationOptions": {"seed": "42", "aspectRatio": {"widthRatio": 1, "heightRatio": 1}},
        "messages": [{"weight": 1, "text": prompt}],
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(_YANDEX_ART_URL, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                run_data = await resp.json()
            operation_id = run_data["id"]

            status_url = _YANDEX_OPERATIONS_URL + operation_id
            for _ in range(20):  # до ~100с ожидания генерации
                await asyncio.sleep(5)
                async with session.get(status_url, headers=headers) as resp:
                    resp.raise_for_status()
                    status_data = await resp.json()
                if status_data.get("done"):
                    if "error" in status_data:
                        log.warning("YandexART: генерация провалилась: %s", status_data["error"])
                        return None
                    image_b64 = status_data["response"]["image"]
                    return base64.b64decode(image_b64)
            log.warning("YandexART: таймаут ожидания генерации")
            return None
    except Exception as e:
        log.warning("YandexART: ошибка генерации картинки: %s", e)
        return None


def _cz_image_path(client: str, idx: int) -> Path:
    return _CZ_DIR / "clients" / client / "drafts" / "images" / f"{idx}.png"


def _cz_draft_card_text(draft: dict, idx: int, total: int) -> str:
    return (
        f"*[{idx + 1}/{total}] {draft.get('topic', '')}*\n\n"
        f"_Хук: {draft.get('chosen_hook', '')}_\n\n"
        f"— — —\n{draft.get('tg_post', '')}\n— — —\n\n"
        f"Пост ВК (публикуй вручную):\n{draft.get('vk_post', '')}"
    )


def _cz_draft_kb(idx: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Одобрить (в очередь)", callback_data=f"cz_pub:{idx}")
    kb.button(text="⏭ Пропустить", callback_data=f"cz_skip:{idx}")
    kb.adjust(2)
    return kb.as_markup()


async def _cz_send_next(chat_id: int, bot: Bot, client: str):
    drafts_path = _cz_latest_drafts_path(client)
    if drafts_path is None:
        await bot.send_message(chat_id, f"Не найден drafts_final_*.json для клиента «{client}».")
        return
    drafts = _json_mod.loads(drafts_path.read_text(encoding="utf-8"))
    decisions = _cz_load_publish_state(client, drafts_path.name)

    pending = [i for i in range(len(drafts)) if str(i) not in decisions]
    if not pending:
        await bot.send_message(chat_id, "Все темы этой пачки уже обработаны (в очереди, опубликованы или пропущены).")
        return

    idx = pending[0]
    card_text = _cz_draft_card_text(drafts[idx], idx, len(drafts))
    try:
        await bot.send_message(chat_id, card_text, reply_markup=_cz_draft_kb(idx))
    except TelegramBadRequest as e:
        if "can't parse entities" in str(e):
            await bot.send_message(chat_id, card_text, reply_markup=_cz_draft_kb(idx), parse_mode=None)
        else:
            raise


@router.message(Command("cz_publish"))
async def cmd_cz_publish(message: Message, bot: Bot):
    if not _auth(message):
        return
    if not OLEG_TG_CHANNEL:
        await message.answer("❌ OLEG_TG_CHANNEL не задан в .env.")
        return
    await _cz_send_next(message.chat.id, bot, "oleg")


@router.callback_query(F.data.startswith("cz_pub:"))
async def cb_cz_publish_one(callback: CallbackQuery, bot: Bot):
    if not _auth(callback):
        return
    idx = int(callback.data.split(":", 1)[1])
    client = "oleg"
    drafts_path = _cz_latest_drafts_path(client)
    if drafts_path is None:
        await callback.answer("Пачка не найдена.", show_alert=True)
        return
    drafts = _json_mod.loads(drafts_path.read_text(encoding="utf-8"))
    draft = drafts[idx]

    decisions = _cz_load_publish_state(client, drafts_path.name)
    slot = _cz_next_slot(decisions)

    image_note = ""
    if YANDEX_ART_FOLDER_ID and YANDEX_ART_API_KEY:
        await callback.answer("Ставлю в очередь, генерирую картинку...")
        prompt = (
            f"Фото-иллюстрация к посту на тему: {draft.get('topic', '')}. "
            "Стиль: минималистичный, деловой, IT/технологии, реалистичное фото "
            "или чистая плоская иллюстрация. БЕЗ текста и надписей на картинке."
        )
        image_bytes = await _cz_generate_image(prompt)
        if image_bytes:
            img_path = _cz_image_path(client, idx)
            img_path.parent.mkdir(parents=True, exist_ok=True)
            img_path.write_bytes(image_bytes)
            image_note = "\n🖼 Картинка сгенерирована."
        else:
            image_note = "\n⚠ Картинка не сгенерировалась — уйдёт текстом."
    else:
        await callback.answer("Ставлю в очередь")

    decisions[str(idx)] = {"status": "scheduled", "at": slot.isoformat()}
    _cz_save_publish_state(client, drafts_path.name, decisions)

    date_str = slot.strftime("%d.%m.%Y %H:%M")
    await _safe_edit(
        callback.message,
        callback.message.text + f"\n\n🗓 *Запланировано на {date_str}*{image_note}",
        reply_markup=None,
    )
    await _cz_send_next(callback.message.chat.id, bot, client)


@router.callback_query(F.data.startswith("cz_skip:"))
async def cb_cz_skip_one(callback: CallbackQuery, bot: Bot):
    if not _auth(callback):
        return
    idx = int(callback.data.split(":", 1)[1])
    client = "oleg"
    drafts_path = _cz_latest_drafts_path(client)
    if drafts_path is None:
        await callback.answer("Пачка не найдена.", show_alert=True)
        return

    decisions = _cz_load_publish_state(client, drafts_path.name)
    decisions[str(idx)] = {"status": "skipped"}
    _cz_save_publish_state(client, drafts_path.name, decisions)

    await _safe_edit(callback.message, callback.message.text + "\n\n⏭ *Пропущено*", reply_markup=None)
    await callback.answer("Пропущено")
    await _cz_send_next(callback.message.chat.id, bot, client)


async def cz_run_scheduler_tick(bot: Bot):
    """Вызывается фоновым циклом из bot.py каждые несколько минут — публикует
    все темы, чей запланированный слот уже наступил. Один тик может
    опубликовать сразу несколько клиентов/тем, если накопилось (например
    бот был выключен дольше суток) — не привязано жёстко к одной теме за тик."""
    client = "oleg"
    if not OLEG_TG_CHANNEL:
        return
    drafts_path = _cz_latest_drafts_path(client)
    if drafts_path is None:
        return
    drafts = _json_mod.loads(drafts_path.read_text(encoding="utf-8"))
    decisions = _cz_load_publish_state(client, drafts_path.name)
    now = datetime.now()
    changed = False

    for idx_str, decision in list(decisions.items()):
        if not isinstance(decision, dict) or decision.get("status") != "scheduled":
            continue
        if datetime.fromisoformat(decision["at"]) > now:
            continue

        idx = int(idx_str)
        draft = drafts[idx]
        img_path = _cz_image_path(client, idx)
        caption = draft.get("tg_post", "")

        try:
            if img_path.exists():
                await bot.send_photo(
                    OLEG_TG_CHANNEL, BufferedInputFile(img_path.read_bytes(), filename="cover.png"),
                    caption=caption, parse_mode="Markdown",
                )
            else:
                await bot.send_message(OLEG_TG_CHANNEL, caption, parse_mode="Markdown")
        except TelegramBadRequest as e:
            if "can't parse entities" in str(e):
                if img_path.exists():
                    await bot.send_photo(
                        OLEG_TG_CHANNEL, BufferedInputFile(img_path.read_bytes(), filename="cover.png"),
                        caption=caption, parse_mode=None,
                    )
                else:
                    await bot.send_message(OLEG_TG_CHANNEL, caption, parse_mode=None)
            else:
                log.exception("cz_run_scheduler_tick: публикация темы %s провалилась", idx)
                continue
        except Exception:
            log.exception("cz_run_scheduler_tick: публикация темы %s провалилась", idx)
            continue

        decision["status"] = "published"
        changed = True

        for chat_id in ALLOWED_USER_IDS:
            try:
                await bot.send_message(chat_id, f"✅ Опубликовано в @textprodv: «{draft.get('topic', '')}»")
            except Exception:
                pass

    if changed:
        _cz_save_publish_state(client, drafts_path.name, decisions)


# ───── АГЕНТ ─────

@router.callback_query(F.data == "agent_mode")
async def cb_agent_mode(callback: CallbackQuery):
    _agent_mode.add(callback.message.chat.id)
    _save_history()
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Выйти из режима агента", callback_data="agent_exit")
    kb.button(text="🗑 Очистить историю", callback_data="agent_clear")
    kb.adjust(1)
    vps_info = f"VPS: {VPS_HOST}" if VPS_HOST else "Локально (claude на этом ПК)"
    await callback.message.answer(
        "🤖 *Режим агента активен*\n\n"
        f"Соединение: `{vps_info}`\n\n"
        "Просто напишите задачу — я передам агенту и верну ответ.\n\n"
        "_Для выхода нажмите кнопку или /menu_",
        reply_markup=kb.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data == "agent_exit")
async def cb_agent_exit(callback: CallbackQuery):
    _agent_mode.discard(callback.message.chat.id)
    _save_history()
    await callback.message.answer("Вышел из режима агента.", reply_markup=_main_kb())
    await callback.answer()

@router.callback_query(F.data == "agent_clear")
async def cb_agent_clear(callback: CallbackQuery):
    _history.pop(callback.message.chat.id, None)
    _save_history()
    await callback.message.answer("🗑 История разговора очищена.")
    await callback.answer()


@router.message(Command("reset"))
async def cmd_reset(message: Message):
    if not _auth(message):
        return
    _history.pop(message.chat.id, None)
    _save_history()
    await message.answer("🗑 История разговора очищена.")


@router.message(Command("agent"))
async def cmd_agent(message: Message):
    if not _auth(message):
        return
    _agent_mode.add(message.chat.id)
    _save_history()
    vps_info = f"VPS: {VPS_HOST}" if VPS_HOST else "Локально"
    await message.answer(
        f"🤖 Режим агента включён ({vps_info})\n"
        "Пишите задачу. /menu — вернуться в меню."
    )


# ───── ФИНАНСОВЫЙ КОУЧ ─────

@router.message(Command("coach"))
async def cmd_coach(message: Message):
    if not _auth(message):
        return
    _coach_mode.add(message.chat.id)
    _agent_mode.discard(message.chat.id)
    _save_history()
    await message.answer(
        "💼 *Финансовый коуч активирован*\n\n"
        "Я помогу разобраться с финансовой эффективностью и ростом.\n"
        "Выбери тему или напиши свой вопрос:",
        reply_markup=_coach_kb()
    )


@router.callback_query(F.data == "coach_mode")
async def cb_coach_mode_btn(callback: CallbackQuery):
    _coach_mode.add(callback.message.chat.id)
    _agent_mode.discard(callback.message.chat.id)
    _save_history()
    await callback.message.answer(
        "💼 *Финансовый коуч активирован*\n\n"
        "Выбери тему или напиши свой вопрос:",
        reply_markup=_coach_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "coach_exit")
async def cb_coach_exit(callback: CallbackQuery):
    _coach_mode.discard(callback.message.chat.id)
    _save_history()
    await callback.message.answer("Вышел из режима коуча.", reply_markup=_main_kb())
    await callback.answer()


_COACH_PRESETS = {
    "coach_ask_audit": (
        "Проведи экспресс-аудит финансов. "
        "Задай мне 5 ключевых вопросов чтобы понять мою финансовую ситуацию: "
        "доходы, расходы, активы, обязательства, точки утечек. "
        "После ответов дай конкретный анализ."
    ),
    "coach_ask_growth": (
        "Помоги мне найти точки роста дохода. "
        "Какие 3 конкретных шага я могу сделать прямо сейчас? "
        "Сначала спроси о моём текущем источнике дохода и навыках."
    ),
    "coach_ask_eff": (
        "Помоги повысить финансовую эффективность. "
        "Задай вопросы о моих расходах, времени и ресурсах "
        "чтобы найти где я теряю деньги или недополучаю."
    ),
    "coach_ask_goals": (
        "Помоги поставить финансовые цели по SMART. "
        "Спроси что я хочу достичь и в какие сроки, "
        "затем помоги сформулировать конкретную цель с числами и разбить на шаги."
    ),
    "coach_ask_passive": (
        "Помоги построить пассивный доход с нуля или масштабировать существующий. "
        "Задай вопросы о доступном капитале, времени и навыках "
        "чтобы предложить реалистичные варианты с цифрами."
    ),
    "coach_ask_mindset": (
        "Начни трансформацию мышления человека из бедняка в миллионера. "
        "Это не про деньги — это про убеждения, привычки восприятия и отношения к деньгам.\n\n"
        "Структура сессии:\n"
        "1. Диагностика — задай 3 точных вопроса чтобы вскрыть глубинные убеждения о деньгах "
        "(откуда берутся, достоин ли я, что такое богатство). "
        "Не давай советов пока не получишь ответы.\n"
        "2. Зеркало — покажи конкретно какие убеждения держат человека в бедности. "
        "Называй вещи своими именами, без мягкости.\n"
        "3. Разворот — для каждого ограничивающего убеждения дай точную противоположность "
        "которую миллионер думает автоматически. Не банальности — конкретные ментальные модели.\n"
        "4. Практика — одно конкретное действие на сегодня которое запустит новый нейронный путь.\n\n"
        "Тон: прямой, без сюсюканья, как ментор который видит потенциал и не позволяет прятаться. "
        "Начни с диагностики."
    ),
    "coach_ask_wheel": (
        "Проведи сессию 'Колесо баланса жизни/бизнеса'.\n\n"
        "Инструмент: клиент оценивает 8 сфер по шкале 1-10 где 1 — полный провал, 10 — идеально.\n\n"
        "Сферы для бизнеса и финансов:\n"
        "1. Доход (текущий уровень vs желаемый)\n"
        "2. Активы и накопления\n"
        "3. Профессиональные навыки и рост\n"
        "4. Деловые связи и партнёры\n"
        "5. Здоровье и энергия\n"
        "6. Семья и личные отношения\n"
        "7. Свободное время и отдых\n"
        "8. Ощущение смысла и направления\n\n"
        "Структура:\n"
        "1. Попроси поставить оценку 1-10 по каждой сфере — сначала только цифры без объяснений\n"
        "2. Найди самую низкую оценку — это точка входа\n"
        "3. Задай вопрос: 'Что должно произойти чтобы эта цифра выросла на 2 пункта?'\n"
        "4. Переведи ответ в конкретный первый шаг с датой\n\n"
        "Начни: 'Давай оценим где ты сейчас. Поставь оценку от 1 до 10 по каждому пункту — просто цифру, без объяснений.'"
    ),
    "coach_ask_tolerations": (
        "Проведи сессию по выявлению энергодренажей — вещей которые человек терпит.\n\n"
        "Контекст: вещи которые мы вынуждены терпеть отбирают нашу энергию, ресурсы и силу духа. "
        "Сложно строить что-то новое когда что-то другое постоянно истощает.\n\n"
        "Структура:\n"
        "1. Попроси назвать минимум 10 вещей которые он терпит прямо сейчас "
        "(люди, ситуации, обязательства, задачи, обстановка, здоровье, деньги — любая сфера). "
        "Скажи: 'Пиши всё что приходит в голову, не фильтруй.'\n"
        "2. После списка задай: 'Что из этого списка съедает больше всего энергии?'\n"
        "3. Возьми топ-3 энергодренажа и спроси по каждому: "
        "'Что конкретно нужно сделать чтобы это исчезло из твоей жизни навсегда?'\n"
        "4. По одному из них возьми обязательство: что ты сделаешь на этой неделе?\n\n"
        "Важно: не давай советов как убрать — клиент знает ответ. Просто задавай вопросы.\n\n"
        "Начни: 'Назови минимум 10 вещей которые ты сейчас вынужден терпеть. Любые — большие и маленькие. Просто список.'"
    ),
    "coach_ask_90days": (
        "Проведи сессию постановки целей на 90 дней.\n\n"
        "Принцип: цели должны быть конкретными, измеримыми, зависящими только от действий клиента — "
        "не от других людей, рынка или обстоятельств.\n\n"
        "Структура:\n"
        "1. Спроси: 'Какие 5 результатов ты хочешь достичь в следующие 90 дней? "
        "Называй конкретно: не «больше зарабатывать» а «выйти на 200 000 ₽/мес к 28 сентября».'\n"
        "2. После списка проверь каждую цель на SMART: есть ли цифра? есть ли дата? зависит ли только от тебя?\n"
        "3. Для нечётких целей задай уточняющий вопрос: 'Как ты поймёшь что достиг этого? Что конкретно изменится?'\n"
        "4. Выбери ОДНУ самую важную цель: 'Если из этих пяти можно достичь только одну — какую выбираешь?'\n"
        "5. Разбей её на первые 3 шага: 'Что ты сделаешь на этой неделе чтобы двинуться к этой цели?'\n"
        "6. Возьми обязательство — конкретное действие с датой.\n\n"
        "Начни: 'Назови 5 конкретных результатов которых ты хочешь достичь к концу сентября. Только измеримые — с цифрами.'"
    ),
    "coach_ask_choice": (
        "Проведи сессию 'Декартовы координаты' — помоги клиенту выбрать между двумя вариантами.\n\n"
        "Инструмент: 4 вопроса которые вскрывают скрытые страхи и истинные желания.\n\n"
        "Сначала попроси назвать два варианта которые стоят перед ним.\n\n"
        "Затем последовательно задай 4 вопроса по каждому варианту:\n"
        "1. 'Что произойдёт ЕСЛИ ты выберешь это?' (позитивные последствия)\n"
        "2. 'Что произойдёт ЕСЛИ ты НЕ выберешь это?' (негативные последствия отказа)\n"
        "3. 'Что НЕ произойдёт если ты выберешь это?' (что потеряешь)\n"
        "4. 'Что НЕ произойдёт если ты НЕ выберешь это?' (от чего избавишься)\n\n"
        "После ответов на все 8 вопросов задай: 'Теперь что ты чувствуешь? Какой вариант откликается сильнее?'\n\n"
        "Важно: не подсказывай ответ. Клиент сам придёт к решению через вопросы.\n\n"
        "Начни: 'Назови два варианта между которыми выбираешь. Одним предложением каждый.'"
    ),
}


@router.callback_query(F.data.startswith("coach_ask_"))
async def cb_coach_preset(callback: CallbackQuery):
    _coach_mode.add(callback.message.chat.id)
    preset_prompt = _COACH_PRESETS.get(callback.data)
    if not preset_prompt:
        await callback.answer("Неизвестная тема")
        return
    wait = await callback.message.answer("💭 Коуч думает... (0с)")

    done_event = asyncio.Event()
    async def _ticker():
        elapsed = 0
        while not done_event.is_set():
            await asyncio.sleep(10)
            if done_event.is_set():
                break
            elapsed += 10
            try:
                await wait.edit_text(f"💭 Коуч думает... ({elapsed}с)")
            except Exception:
                pass
    ticker_task = asyncio.create_task(_ticker())

    try:
        result = await _ask_ai(COACH_SYSTEM, preset_prompt, callback.message.chat.id)
    finally:
        done_event.set()
        ticker_task.cancel()

    await wait.delete()
    for i in range(0, len(result), 4000):
        await callback.message.answer(result[i:i+4000], reply_markup=_coach_kb() if i + 4000 >= len(result) else None)
    await callback.answer()


async def _dispatch_coach(message: Message):
    """Обрабатывает свободный текст в режиме коуча."""
    wait = await message.answer("💭 Коуч думает... (0с)")
    user_text = message.text.strip()

    done_event = asyncio.Event()
    async def _ticker():
        elapsed = 0
        while not done_event.is_set():
            await asyncio.sleep(10)
            if done_event.is_set():
                break
            elapsed += 10
            try:
                await wait.edit_text(f"💭 Коуч думает... ({elapsed}с)")
            except Exception:
                pass
    ticker_task = asyncio.create_task(_ticker())

    try:
        result = await _ask_ai(COACH_SYSTEM, user_text, message.chat.id)
    finally:
        done_event.set()
        ticker_task.cancel()

    # Сохраняем факты и историю коуч-сессии
    _memory.save_from_session(message.chat.id, user_text, result)
    hist = _history.setdefault(message.chat.id, [])
    hist.append(("user", user_text))
    hist.append(("assistant", result[:2500]))
    if len(hist) > 24:
        _history[message.chat.id] = hist[-24:]
    _save_history()

    await wait.delete()
    for i in range(0, len(result), 4000):
        await _safe_answer(message, result[i:i+4000], reply_markup=_coach_kb() if i + 4000 >= len(result) else None)


def _session_history_text(chat_id: int | None) -> str:
    """Форматирует последние сообщения текущей сессии для подстановки в промпт."""
    if chat_id is None:
        return ""
    session = _history.get(chat_id, [])
    if not session:
        return ""
    lines = "\n".join(
        f"{'Пользователь' if r == 'user' else 'Агент'}: {t}"
        for r, t in session[-12:]
    )
    return f"\n\n=== ИСТОРИЯ ТЕКУЩЕЙ СЕССИИ ===\n{lines}"


async def _ask_ai(system_prompt: str, user_message: str, chat_id: int | None = None,
                   image_path: Path | None = None) -> str:
    """
    Единая точка вызова AI.
    1. Если ANTHROPIC_API_KEY — прямой SDK (быстро, надёжно), история идёт как messages[].
       Если задан image_path — картинка уходит вместе с текстом мультимодальным
       сообщением (документы/видео через SDK не поддержаны, см. ниже).
    2. Иначе — subprocess claude через cmd /c + stdin (работает на Windows);
       здесь claude --print не хранит состояние между вызовами, поэтому история
       сессии подставляется в текст промпта явно. Т.к. subprocess запущен с
       --permission-mode bypassPermissions, Claude Code сам может прочитать
       файл по указанному пути своим инструментом Read (работает для фото,
       PDF, видео, аудио) — поэтому здесь image_path просто упоминается в
       тексте промпта, а не кодируется в base64.
    """
    if AGENT_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
        return await _run_anthropic_sdk(system_prompt, user_message, chat_id, image_path)
    full_prompt = (
        system_prompt
        + _session_history_text(chat_id)
        + "\n\n=== НОВОЕ СООБЩЕНИЕ ===\n"
        + user_message
    )
    if image_path is not None:
        full_prompt += f"\n\n(Прикреплённый файл — прочитай его инструментом Read: {image_path})"
    if AGENT_PROVIDER == "codex":
        return await _run_codex_subprocess(full_prompt)
    return await _run_claude_subprocess(full_prompt)


async def _run_codex_subprocess(full_prompt: str) -> str:
    """Run one non-interactive Codex turn, passing the prompt over stdin."""
    import os
    env = {**os.environ}
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        env.pop(key, None)

    try:
        proc = await asyncio.create_subprocess_exec(
            CODEX_BIN, "exec", "--skip-git-repo-check", "-C", str(BASE_DIR), "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=full_prompt.encode("utf-8", errors="replace")),
            timeout=600,
        )
        result = stdout.decode("utf-8", errors="replace").strip()
        error = stderr.decode("utf-8", errors="replace").strip()
        if proc.returncode and not result:
            return f"Ошибка Codex (код {proc.returncode}): {error or 'нет описания'}"
        return result or error or "Codex не вернул ответ."
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return "Таймаут 10 минут — Codex не ответил. Попробуйте разбить запрос на части."
    except Exception as exc:
        return f"Ошибка запуска Codex: {exc}"


def _build_user_content(user_message: str, image_path: Path | None):
    """Собирает content для Anthropic SDK — либо просто строка, либо список
    блоков (картинка + текст), если приложено изображение."""
    if image_path is None:
        return user_message

    import base64
    ext = image_path.suffix.lower().lstrip(".")
    media_type = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "gif": "image/gif", "webp": "image/webp",
    }.get(ext)
    if media_type is None:
        # Не изображение (PDF/видео/аудио) — SDK-путь картинки не поддерживает,
        # сообщаем модели путь текстом, честно предупреждая что содержимое
        # не приложено (лучше явное ограничение, чем молчаливая заглушка).
        return (
            f"{user_message}\n\n"
            f"(Файл {image_path.name} приложен пользователем, но этот тип "
            f"файла нельзя передать напрямую через Anthropic API — только "
            f"через subprocess-режим Claude Code. Скажи об этом честно.)"
        )

    data = base64.standard_b64encode(image_path.read_bytes()).decode("utf-8")
    return [
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
        {"type": "text", "text": user_message},
    ]


async def _run_anthropic_sdk(system_prompt: str, user_message: str, chat_id: int | None,
                              image_path: Path | None = None) -> str:
    """Прямой вызов Anthropic API через SDK."""
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

        messages: list = []
        if chat_id is not None:
            for role, text in _history.get(chat_id, [])[-12:]:
                messages.append({"role": role if role in ("user", "assistant") else "user", "content": text})
        messages.append({"role": "user", "content": _build_user_content(user_message, image_path)})

        response = await asyncio.wait_for(
            client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=2048,
                system=system_prompt,
                messages=messages,
            ),
            timeout=30,
        )
        return response.content[0].text.strip()
    except asyncio.TimeoutError:
        return "⏱ Таймаут 30с — попробуй ещё раз."
    except Exception as e:
        return f"❌ Ошибка API: {e}"


async def _run_claude_subprocess(full_prompt: str) -> str:
    """Запуск claude через cmd /c с передачей промпта через stdin (Windows-совместимо)."""
    import os
    env = {**os.environ}
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        env.pop(k, None)

    try:
        proc = await asyncio.create_subprocess_exec(
            "cmd", "/c", "claude", "--print", "--permission-mode", "bypassPermissions",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=full_prompt.encode("utf-8", errors="replace")),
            timeout=600,
        )
        result = stdout.decode("utf-8", errors="replace").strip()
        if not result:
            result = stderr.decode("utf-8", errors="replace").strip()
        return result or "Агент не вернул ответ."
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return "⏱ Таймаут 10 минут — claude не ответил, попробуй разбить запрос на части."
    except Exception as e:
        return f"❌ Ошибка subprocess: {e}"


async def _run_claude_local(prompt: str) -> str:
    """Обратная совместимость — делегирует в _run_claude_subprocess."""
    return await _run_claude_subprocess(prompt)


def _read_vps_file(client, path: str) -> str:
    """Читает файл с VPS, возвращает пустую строку если не найден."""
    try:
        _, out, _ = client.exec_command(f"cat {path} 2>/dev/null")
        return out.read().decode("utf-8", errors="replace").strip()
    except Exception:
        return ""

def _run_claude_vps_sync(full_prompt: str) -> str:
    """Синхронный SSH-вызов claude на VPS (запускается в thread pool)."""
    try:
        import paramiko
    except ImportError:
        return "❌ Установите paramiko: pip install paramiko"

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=10)
        stdin, stdout, _ = client.exec_command(
            "cd /root/telegram-bot && claude --print --permission-mode bypassPermissions 2>&1", timeout=120
        )
        stdin.write(full_prompt + "\n")
        stdin.channel.shutdown_write()
        stdout.channel.recv_exit_status()
        result = stdout.read().decode("utf-8", errors="replace").strip()
        client.close()
        return result or "Агент не вернул ответ."
    except Exception as e:
        return f"❌ Ошибка VPS: {e}"

def _build_prompt(chat_id: int, user_message: str) -> str:
    """Собирает полный промпт: память + история + новое сообщение."""
    import json as _json
    soul = memory = goals = ""
    saved_history = []

    try:
        import paramiko
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=10)
        soul   = _read_vps_file(client, "/root/telegram-bot/SOUL.md")
        memory = _read_vps_file(client, "/root/telegram-bot/MEMORY.md")
        goals  = _read_vps_file(client, "/root/telegram-bot/GOALS.md")
        # Читаем сохранённую историю из memory.json по chat_id
        raw_mem = _read_vps_file(client, "/root/telegram-bot/memory.json")
        if raw_mem:
            mem_data = _json.loads(raw_mem)
            saved_history = mem_data.get(str(chat_id), [])
        client.close()
    except Exception:
        pass

    parts = []
    if soul:
        parts.append(f"=== КТО ТЫ (SOUL.md) ===\n{soul}")
    if memory:
        parts.append(f"=== ДОЛГОСРОЧНАЯ ПАМЯТЬ (MEMORY.md) ===\n{memory}")
    if goals:
        parts.append(f"=== ЦЕЛИ (GOALS.md) ===\n{goals}")

    # Граф знаний пользователя (локальный, структурированный)
    graph_ctx = _memory.get_user_context(chat_id)
    if graph_ctx:
        parts.append(f"=== ГРАФ ЗНАНИЙ ПОЛЬЗОВАТЕЛЯ ===\n{graph_ctx}")

    # Последние 10 сообщений из сохранённой истории VPS
    if saved_history:
        last = saved_history[-20:]
        hist_text = "\n".join(
            f"{'Пользователь' if m['role'] == 'user' else 'Агент'}: {m['content'][:300]}"
            for m in last
        )
        parts.append(f"=== ИСТОРИЯ ПРЕДЫДУЩИХ РАЗГОВОРОВ ===\n{hist_text}")

    # Текущая сессия (в памяти бота)
    session = _history.get(chat_id, [])
    if session:
        sess_text = "\n".join(
            f"{'Пользователь' if r == 'user' else 'Агент'}: {t}"
            for r, t in session[-12:]
        )
        parts.append(f"=== ТЕКУЩАЯ СЕССИЯ ===\n{sess_text}")

    parts.append(f"=== НОВОЕ СООБЩЕНИЕ ===\n{user_message}")
    return "\n\n".join(parts)


def _build_local_coach_prompt(chat_id: int, user_message: str) -> str:
    """Собирает промпт коуча с графом знаний и историей сессии (для локального режима)."""
    parts = [COACH_SYSTEM.strip()]

    graph_ctx = _memory.get_user_context(chat_id)
    if graph_ctx:
        parts.append(f"=== ЧТО Я ЗНАЮ О ТЕБЕ ===\n{graph_ctx}")

    session = _history.get(chat_id, [])
    if session:
        hist_lines = "\n".join(
            f"{'Клиент' if r == 'user' else 'Коуч'}: {t}"
            for r, t in session[-12:]
        )
        parts.append(f"=== ИСТОРИЯ НАШЕЙ СЕССИИ ===\n{hist_lines}")

    parts.append(f"=== НОВОЕ СООБЩЕНИЕ КЛИЕНТА ===\n{user_message}")
    return "\n\n".join(parts)


def _save_to_vps_memory(chat_id: int, user_msg: str, assistant_msg: str):
    """Дописывает обмен в memory.json на VPS."""
    import json as _json
    try:
        import paramiko
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=10)
        raw = _read_vps_file(client, "/root/telegram-bot/memory.json")
        data = _json.loads(raw) if raw else {}
        key = str(chat_id)
        if key not in data:
            data[key] = []
        data[key].append({"role": "user",      "content": user_msg})
        data[key].append({"role": "assistant",  "content": assistant_msg[:800]})
        if len(data[key]) > 100:
            data[key] = data[key][-100:]
        new_json = _json.dumps(data, ensure_ascii=False, indent=2)
        stdin, stdout, _ = client.exec_command("cat > /root/telegram-bot/memory.json")
        stdin.write(new_json)
        stdin.channel.shutdown_write()
        stdout.channel.recv_exit_status()
        client.close()
    except Exception:
        pass

async def _run_claude_vps(chat_id: int, prompt: str) -> str:
    """Запускает SSH в отдельном потоке, не блокирует event loop."""
    full_prompt = await asyncio.get_event_loop().run_in_executor(
        None, _build_prompt, chat_id, prompt
    )
    return await asyncio.get_event_loop().run_in_executor(
        None, _run_claude_vps_sync, full_prompt
    )


async def _run_agent_and_reply(message: Message, bot: Bot, prompt: str,
                                image_path: Path | None = None) -> None:
    """Общий путь "спросить агента и ответить" — переиспользуется текстовым
    хендлером и хендлерами вложений (голос/фото/документы/видео), чтобы вся
    логика (тикер "Думаю...", история, теги файлов от агента) не дублировалась
    в каждом отдельно."""
    wait = await message.answer("🤖 Думаю... (0с)")

    # Таймер: обновляет сообщение каждые 10 сек пока агент думает
    done_event = asyncio.Event()
    async def _ticker():
        elapsed = 0
        while not done_event.is_set():
            await asyncio.sleep(10)
            if done_event.is_set():
                break
            elapsed += 10
            try:
                await wait.edit_text(f"🤖 Думаю... ({elapsed}с)")
            except Exception:
                pass
    ticker_task = asyncio.create_task(_ticker())

    try:
        result = await _ask_ai(AGENT_SYSTEM, prompt, message.chat.id, image_path=image_path)
    finally:
        done_event.set()
        ticker_task.cancel()

    # Сохраняем в историю сессии
    hist = _history.setdefault(message.chat.id, [])
    hist.append(("user", prompt))
    hist.append(("assistant", result[:2500]))
    if len(hist) > 24:
        _history[message.chat.id] = hist[-24:]
    _save_history()

    # Сохраняем факты в граф знаний
    _memory.save_from_session(message.chat.id, prompt, result)

    await wait.delete()

    # Агент мог сослаться на файлы тегами [ФАЙЛ: путь] и т.п. — вырезаем их
    # из текста и прикладываем реальными файлами (см. media.py).
    text_only, file_tags = _media.extract_file_tags(result)
    found_files, missing_paths = _media.resolve_existing_files(file_tags)

    # Разбиваем длинные ответы на части (лимит Telegram 4096 символов)
    if text_only:
        for i in range(0, len(text_only), 4000):
            await _safe_answer(message, text_only[i:i + 4000])

    for method, path in found_files:
        try:
            input_file = FSInputFile(path)
            sender = getattr(message, f"answer_{method}")
            await sender(input_file)
        except Exception as e:
            log.warning("Не удалось отправить файл %s (%s): %s", path, method, e)
            await message.answer(f"⚠ Агент создал файл {path.name}, но отправить его не удалось: {e}")

    if missing_paths:
        paths_list = "\n".join(f"— {p}" for p in missing_paths)
        await message.answer(
            f"⚠ Агент сослался на файл(ы), которых не нашлось на диске:\n{paths_list}"
        )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_agent_message(message: Message, bot: Bot):
    """Перехватывает свободный текст — если агент или коуч включён, отправляет запрос."""
    if not _auth(message):
        return
    if message.chat.id in _coach_mode:
        await _dispatch_coach(message)
        return
    if message.chat.id not in _agent_mode:
        return  # не в режиме агента — игнорируем

    await _run_agent_and_reply(message, bot, message.text.strip())


def _agent_mode_hint(kind: str) -> str:
    return (
        f"{kind} получен(о), но режим агента выключен — я не обрабатываю вложения "
        f"вне режима агента. Напиши /agent, чтобы включить, и пришли ещё раз."
    )


@router.message(F.voice | F.audio)
async def handle_voice_message(message: Message, bot: Bot):
    """Голосовые/аудио → Deepgram → расшифровка идёт в агента как обычный
    текстовый запрос. Раньше такие сообщения попадали в handle_unmatched
    с ответом "не умею обрабатывать"."""
    if not _auth(message):
        return
    if message.chat.id not in _agent_mode:
        await message.answer(_agent_mode_hint("🎤 Голосовое"))
        return

    voice = message.voice or message.audio
    status = await message.answer("🎤 Слушаю голосовое...")

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    is_voice = message.voice is not None
    ext = "ogg" if is_voice else (Path(getattr(voice, "file_name", None) or "audio.mp3").suffix.lstrip(".") or "mp3")
    dest = UPLOADS_DIR / f"voice_{message.message_id}.{ext}"

    try:
        await bot.download(voice, destination=dest)
        mime = "audio/ogg" if is_voice else "audio/mpeg"
        transcript = await _media.transcribe_voice(dest.read_bytes(), mime_type=mime)
    except _media.TranscriptionNotConfigured as e:
        await status.edit_text(str(e))
        return
    except _media.TranscriptionError as e:
        await status.edit_text(f"❌ Не удалось расшифровать голосовое: {e}")
        return
    except Exception as e:
        log.exception("Ошибка обработки голосового")
        await status.edit_text(f"❌ Ошибка при обработке голосового: {e}")
        return

    preview = transcript[:100] + ("…" if len(transcript) > 100 else "")
    await status.edit_text(f"Распознано: «{preview}»")

    await _run_agent_and_reply(message, bot, transcript)


@router.message(F.photo)
async def handle_photo_message(message: Message, bot: Bot):
    """Фото → скачивается и уходит агенту на анализ (мультимодально через
    Anthropic SDK, либо через инструмент Read у Claude Code в subprocess-режиме)."""
    if not _auth(message):
        return
    if message.chat.id not in _agent_mode:
        await message.answer(_agent_mode_hint("📷 Фото"))
        return

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    largest = message.photo[-1]
    dest = UPLOADS_DIR / f"photo_{message.message_id}.jpg"
    await bot.download(largest, destination=dest)

    prompt = message.caption.strip() if message.caption else "Что на этом фото? Опиши подробно."
    await _run_agent_and_reply(message, bot, prompt, image_path=dest)


@router.message(F.document)
async def handle_document_message(message: Message, bot: Bot):
    """PDF/Word/txt/любой файл → скачивается, путь передаётся агенту (Read
    инструмент Claude Code читает PDF/офисные форматы; через Anthropic SDK
    честно предупреждаем, что документ не приложен напрямую — см. media.py)."""
    if not _auth(message):
        return
    if message.chat.id not in _agent_mode:
        await message.answer(_agent_mode_hint("📄 Документ"))
        return

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    doc = message.document
    suffix = Path(doc.file_name or "file").suffix or ""
    dest = UPLOADS_DIR / f"doc_{message.message_id}{suffix}"
    await bot.download(doc, destination=dest)

    prompt = message.caption.strip() if message.caption else f"Изучи файл {doc.file_name} и перескажи суть."
    await _run_agent_and_reply(message, bot, prompt, image_path=dest)


@router.message(F.video | F.video_note)
async def handle_video_message(message: Message, bot: Bot):
    """Видео/видео-кружок → скачивается, дальше как документ (Read-инструмент
    Claude Code умеет разбирать видео; через SDK — честное предупреждение)."""
    if not _auth(message):
        return
    if message.chat.id not in _agent_mode:
        await message.answer(_agent_mode_hint("🎬 Видео"))
        return

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    video = message.video or message.video_note
    dest = UPLOADS_DIR / f"video_{message.message_id}.mp4"
    await bot.download(video, destination=dest)

    prompt = message.caption.strip() if message.caption else "Посмотри это видео и опиши, что происходит."
    await _run_agent_and_reply(message, bot, prompt, image_path=dest)


@router.message()
async def handle_unmatched(message: Message):
    """Ловит всё, что не подошло под остальные фильтры (стикеры, контакты,
    геолокация и т.п. — голос/фото/документы/видео теперь обрабатываются
    отдельными хендлерами выше). Раньше такие сообщения проглатывались
    молча, и бот выглядел "зависшим"/"молчащим" без единой строчки ответа."""
    if not _auth(message):
        return
    log.info("Необработанное сообщение chat_id=%s content_type=%s", message.chat.id, message.content_type)
    if message.text and message.text.startswith("/"):
        await message.answer(
            f"Неизвестная команда {message.text.split()[0]}. /help — список команд."
        )
    else:
        await message.answer(
            f"Не умею обрабатывать сообщения такого типа ({message.content_type}). Пришли текстом."
        )


# ───── ВСПОМОГАТЕЛЬНЫЕ ─────

async def _check_site() -> bool:
    timeout = aiohttp.ClientTimeout(total=8)
    for url in [SITE_URL, SITE_URL.replace("https://", "http://")]:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, allow_redirects=True) as resp:
                    if resp.status == 200:
                        return True
        except Exception:
            continue
    return False


async def _get_vk_stats() -> dict | None:
    if not VK_TOKEN:
        return None
    url = "https://api.vk.com/method/groups.getById"
    params = {
        "group_ids": str(VK_GROUP_ID),
        "fields": "members_count,status,name",
        "access_token": VK_TOKEN,
        "v": "5.199",
    }
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
                groups = data.get("response", {}).get("groups", [])
                return groups[0] if groups else None
    except Exception as e:
        log.warning("VK stats error: %s", e)
        return None


def _check_env_key(rel_path: str, key: str) -> bool:
    from pathlib import Path
    env_path = Path(__file__).parent.parent / rel_path
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith(f"{key}="):
                    val = line.split("=", 1)[1].strip()
                    return bool(val)
    except Exception:
        pass
    return False


def _get_post_template(idx: int) -> str:
    templates = [
        "Меня зовут Светлана Палкина — я психотерапевт, работаю с парами.\n\nЯ выбрала именно эту специализацию, потому что отношения — это главное, что есть у людей. И то, как они складываются, определяет качество всей жизни.\n\nЯ работаю онлайн. Это значит, вы можете прийти ко мне из любого города, в удобное время, без дороги и стресса.\n\nЧто привело вас на эту страницу? Напишите в комментарии.\n\n#психотерапевт #семейнаятерапия #СветланаПалкина",
        "Знаете, почему пары приходят к психологу в последний момент?\n\n1. «Само пройдёт». Не проходит.\n2. «Ещё не всё так плохо». К моменту, когда «всё так плохо» — уходит много сил и времени.\n3. «Психолог — это слабость». Это смелость.\n\nЧем раньше прийти — тем быстрее результат и тем легче путь.\n\nУзнали себя? Поставьте ❤️\n\n#психология #отношения #семья",
        "Миф: «К психологу идут только когда совсем плохо».\n\nРеальность: пары, которые приходят на профилактику — решают проблемы за 3–5 встреч.\n\nПары, которые ждут кризиса — работают месяцами.\n\nПсихолог — это не скорая помощь. Это инструмент.\n\nА вы как считаете?\n\n#мифыопсихологии #терапия #пары",
        "Однажды ко мне пришла пара — они не разговаривали почти два года. Жили в одной квартире, вели общий быт, воспитывали ребёнка.\n\nНо как чужие.\n\nЗа 8 сессий они нашли путь обратно друг к другу.\n\nЭто не магия. Это работа.\n\nПохожая ситуация? Напишите мне.\n\n#историяпары #близость #отношения",
        "Кризис в браке — не приговор.\n\n3 признака, что ещё можно выйти:\n1. Оба хотят сохранить отношения (даже если не говорят об этом)\n2. Есть общая история — дети, воспоминания, совместное прошлое\n3. Есть хотя бы одна точка, в которой вы ещё вместе\n\nЕсли хотя бы один пункт — да, шанс есть.\n\nСохраните пост — пригодится.\n\n#кризисвбраке #семья #психолог",
        "Частый вопрос: «Можно ли прийти на сессию одному, без партнёра?»\n\nДа. Это работает.\n\nКогда партнёр отказывается идти — вы всё равно можете начать. Изменения в одном человеке меняют систему целиком.\n\nЯ работаю и с парами, и с одним партнёром.\n\nЕщё вопросы? Пишите в комментарии.\n\n#вопросыпсихологу #онлайнтерапия",
        "Если случилась измена, до того как принять решение — стоит задать себе 5 вопросов:\n\n1. Что стояло за изменой — случайность или симптом?\n2. Хочу ли я разобраться — или уже всё решено?\n3. Есть ли у нас что сохранять?\n4. Могу ли я работать над доверием?\n5. Что я хочу для себя — независимо от партнёра?\n\nЭти вопросы не дают ответов. Они дают ясность.\n\nПоделитесь с тем, кому это нужно.\n\n#измена #отношения #психолог",
        "Онлайн-терапия vs очная: что выбрать паре?\n\nОнлайн:\n✅ Любой город\n✅ Не нужно ехать вместе\n✅ Привычная обстановка снижает тревогу\n\nОчная:\n✅ Физическое присутствие\n✅ Для некоторых — ощущение «серьёзности»\n\nЯ работаю онлайн. 90% моих клиентов — это пары из разных городов.\n\nВы пробовали онлайн-сессии?\n\n#онлайнтерапия #психологонлайн",
        "Почему «просто поговорить» в конфликте не работает?\n\nПотому что в момент ссоры оба человека в режиме защиты. Слышат не слова — слышат угрозу.\n\nЧто работает:\n— Пауза (выйти из комнаты, остыть)\n— Говорить о себе: «Я чувствую...» вместо «Ты всегда...»\n— Один вопрос: «Что тебе сейчас нужно?\"\n\nПокажите партнёру.\n\n#конфликты #ссоры #семья",
        "Что происходит на первой сессии — честно.\n\nДо: волнение, «а вдруг осудят» — нормально.\n\nВо время:\n— Знакомство: кто вы, что случилось\n— Я не даю советов сразу — я слушаю\n— Мы вместе формулируем запрос\n\nПосле:\n— Ясность: что будем делать\n— Договорённость о следующем шаге\n\nПервичная сессия 60–90 мин — 5000 ₽\n\nЗаписаться: palkina-therapy.ru\n\n#перваясессия #терапия #психолог",
        "Стоимость сессии — 3000–5000 ₽.\nСтоимость развода — от 50 000 ₽ + годы на восстановление.\n\nЭто не реклама.\n\nЭто просто математика.\n\nПервичная сессия — 5000 ₽. Без предоплаты. Онлайн.\n\nЗапись в комментарии или на сайте.\n\n#стоимостьтерапии #инвестиции",
        "Можно ли вернуть близость, если её не было уже несколько лет?\n\nДа. Но это работа.\n\nЭмоциональное отчуждение — не конец. Это сигнал.\n\nЯ видела пары, которые нашли путь обратно после 5 лет холодности.\n\nЕсли чувствуете, что стали чужими — напишите мне. Разберёмся вместе.\n\n#близость #отношения #психотерапевт",
    ]
    if 0 <= idx < len(templates):
        return templates[idx]
    return "Текст поста не найден."
