import asyncio
import logging
import sys
from pathlib import Path

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

from config import TELEGRAM_TOKEN, TELEGRAM_PROXY_URL
import handlers

# Консоль/файл-редирект на Windows по умолчанию в cp1251, а сообщения бота
# полны эмодзи (🤖💭✅) — без этого logging сам падает с UnicodeEncodeError
# на любой попытке залогировать такой текст, роняя весь процесс (в том
# числе изнутри обработчика ошибок aiogram, до которого дело даже не
# доходит). Отсюда были загадочные "молчания" бота на несколько секунд.
sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

_LOCK_PATH = Path(__file__).parent / ".bot.lock"


def _acquire_single_instance_lock():
    """Не даёт запустить второй bot.py одновременно — иначе оба дерутся за
    getUpdates и Telegram отвечает Conflict, из-за чего бот выглядит
    "тормозящим" вместо явной ошибки о втором инстансе."""
    try:
        lock_file = open(_LOCK_PATH, "w")
        lock_file.write("x")
        lock_file.flush()
        lock_file.seek(0)
        if sys.platform == "win32":
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log.error("Уже запущен другой процесс bot.py (файл-лок %s занят). Выхожу.", _LOCK_PATH)
        sys.exit(1)
    return lock_file  # держим открытым на весь процесс — лок снимается при выходе


async def _cz_scheduler_loop(bot: Bot):
    """Раз в 5 минут проверяет очередь публикаций ContentZavod (см.
    handlers.cz_run_scheduler_tick) — отдельная задача, не блокирует
    поллинг Telegram-апдейтов."""
    while True:
        try:
            await handlers.cz_run_scheduler_tick(bot)
        except Exception:
            log.exception("cz_scheduler_loop: тик провалился")
        await asyncio.sleep(300)


async def main():
    if not TELEGRAM_TOKEN:
        log.error("TELEGRAM_TOKEN не задан в .env")
        sys.exit(1)

    session = AiohttpSession(proxy=TELEGRAM_PROXY_URL) if TELEGRAM_PROXY_URL else None
    bot = Bot(
        token=TELEGRAM_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dp = Dispatcher()
    dp.include_router(handlers.router)

    @dp.error()
    async def on_error(event):
        # Без этого необработанное исключение в любом хендлере (например,
        # TelegramBadRequest от невалидной Markdown-разметки в ответе ИИ)
        # убивает весь процесс — бот "молчит" 5-15 сек, пока супервизор его
        # не перезапустит. Логируем и продолжаем поллинг остальных апдейтов.
        log.exception("Необработанная ошибка в хендлере: %s", event.exception)
        return True

    asyncio.create_task(_cz_scheduler_loop(bot))

    log.info("Гаврик запущен.")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    _lock_file = _acquire_single_instance_lock()
    asyncio.run(main())
