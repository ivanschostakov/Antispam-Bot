from os import getenv, environ
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()
environ["TOKENIZERS_PARALLELISM"]  =  "false"

WORKING_DIR = Path(__file__).parent
LOGS_DIR = WORKING_DIR / "logs"
MESSAGES_LOGS_DIR = LOGS_DIR / "messages"
SRC_DIR = WORKING_DIR / "src"
STATS_CSV_PATH = LOGS_DIR / "messages.csv"
LABELED_CSV_PATH = LOGS_DIR / "messages_labeled_legacy.csv"
MISSES_PATH = LOGS_DIR / "misses.csv"
HF_SAVE_DIR = SRC_DIR / "hf_rubert_spam"
CLF_PATH = SRC_DIR / "spam_classifier.joblib"
MAX_LENGTH = 128
MODEL_NAME = "cointegrated/rubert-tiny"

CAPTCHA_MAX_ATTEMPTS  =  3
POLL_TIMEOUT_SECONDS  =  30
POLL_TIMEOUT_BUFFER  =  3

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
ANTISPAM_BOT_TOKEN = getenv("ANTISPAM_BOT_TOKEN")

REPORTS_CHANNEL_ID = int(getenv("REPORTS_CHANNEL_ID", 0))

POSTGRES_DB = getenv("POSTGRES_DB")
POSTGRES_USER = getenv("POSTGRES_USER")
POSTGRES_HOST = getenv("POSTGRES_HOST")
POSTGRES_PORT = getenv("POSTGRES_PORT")
POSTGRES_PASSWORD = getenv("POSTGRES_PASSWORD")

SYNC_DATABASE_URL = f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
ASYNC_DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
