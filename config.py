import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent

load_dotenv(BASE_DIR / ".env")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
# Fallback, если api.telegram.org недоступен напрямую с сервера (например http://user:pass@host:port)
TELEGRAM_PROXY_URL = os.getenv("TELEGRAM_PROXY_URL", "")
VK_TOKEN = os.getenv("VK_TOKEN", "")
VK_GROUP_ID = int(os.getenv("VK_GROUP_ID", "227082800"))
SITE_URL = os.getenv("SITE_URL", "https://palkina-therapy.ru")

# VPS агент (опционально — если не задан, claude запускается локально)
VPS_HOST = os.getenv("VPS_HOST", "")
VPS_USER = os.getenv("VPS_USER", "agent")
VPS_PASSWORD = os.getenv("VPS_PASSWORD", "")
CLAUDE_BIN = os.getenv("CLAUDE_BIN", "claude")
AGENT_PROVIDER = os.getenv("AGENT_PROVIDER", "codex").strip().lower()
CODEX_BIN = os.getenv("CODEX_BIN", "codex")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

# Расшифровка голосовых сообщений (см. media.py). Получить бесплатно:
# https://console.deepgram.com/api-keys — $200 кредитов без карты.
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")

# Куда сохранять входящие вложения (голос/фото/документы/видео) перед
# отправкой агенту на анализ.
UPLOADS_DIR = BASE_DIR / ".uploads"

_raw_ids = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_USER_IDS: list[int] = [
    int(x.strip()) for x in _raw_ids.split(",") if x.strip().isdigit()
]

PROJECT_ROOT = BASE_DIR.parent
CONTENT_PLAN_PATH = PROJECT_ROOT / "vk_content" / "content_plan.md"
DIRECT_CSV_PATH = PROJECT_ROOT / "output" / "direct_campaign.csv"
LANDING_DIR = PROJECT_ROOT / "landing"

# ContentZavod — публикация для Олега (см. content_zavod/clients/oleg/platforms.md)
OLEG_TG_CHANNEL = os.getenv("OLEG_TG_CHANNEL", "")

# ContentZavod — генерация картинок (YandexART / AI Studio)
YANDEX_ART_FOLDER_ID = os.getenv("YANDEX_ART_FOLDER_ID", "")
YANDEX_ART_API_KEY = os.getenv("YANDEX_ART_API_KEY", "")
