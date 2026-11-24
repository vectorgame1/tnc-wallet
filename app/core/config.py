import os
from pathlib import Path
from dotenv import load_dotenv
BASE = Path(__file__).resolve().parents[2]
load_dotenv(BASE / ".env")
class Settings:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    WEBAPP_URL = os.getenv("WEBAPP_URL", "")
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(BASE/'tnc.db').as_posix()}")
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    PORT = int(os.getenv("PORT", "8000"))
    ADMIN_IDS = {int(v) for v in os.getenv("ADMIN_IDS", "").split(",") if v.strip().isdigit()}
    AUTH_MAX_AGE = 86400
settings = Settings()
