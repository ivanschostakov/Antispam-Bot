import os
from os import getenv
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

os.environ["TOKENIZERS_PARALLELISM"] = "false"

WORKING_DIR=Path(__file__).parent
LOGS_DIR=WORKING_DIR / "logs"
MESSAGES_LOGS_DIR=LOGS_DIR / "messages"
SRC_DIR=WORKING_DIR / "src"
STATS_CSV_PATH=LOGS_DIR / "messages.csv"
LABELED_CSV_PATH=LOGS_DIR / "messages_labeled_legacy.csv"
MISSES_PATH=LOGS_DIR / "misses.csv"
HF_SAVE_DIR=SRC_DIR / "hf_rubert_spam"
CLF_PATH=SRC_DIR / "spam_classifier.joblib"
MAX_LENGTH=128
MODEL_NAME="cointegrated/rubert-tiny"

CAPTCHA_MAX_ATTEMPTS = 3
POLL_TIMEOUT_SECONDS = 30
POLL_TIMEOUT_BUFFER = 3

MOSCOW_TZ=ZoneInfo("Europe/Moscow")
ANTISPAM_BOT_TOKEN=getenv("ANTISPAM_BOT_TOKEN")

def _parse_optional_int(name: str) -> int | None:
    raw = getenv(name)
    if raw is None or raw.strip() == "":
        return None
    return int(raw)


def _parse_int_list(raw: str | None) -> list[int]:
    if not raw:
        return []

    out: list[int] = []
    for chunk in raw.split(","):
        value = chunk.strip()
        if not value:
            continue
        out.append(int(value))
    return out


ELIXIR_CHAT_ID=_parse_optional_int("ELIXIR_CHAT_ID")
MODERATED_CHAT_IDS=_parse_int_list(getenv("MODERATED_CHAT_IDS"))
if not MODERATED_CHAT_IDS and ELIXIR_CHAT_ID is not None:
    MODERATED_CHAT_IDS=[ELIXIR_CHAT_ID]
REPORTS_CHANNEL_ID=int(getenv("REPORTS_CHANNEL_ID"))

POSTGRES_USER=getenv("POSTGRES_USER")
POSTGRES_PASSWORD=getenv("POSTGRES_PASSWORD")
POSTGRES_DB=getenv("POSTGRES_DB")
POSTGRES_HOST=getenv("POSTGRES_HOST")
POSTGRES_PORT=getenv("POSTGRES_PORT")

SYNC_DATABASE_URL=f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
ASYNC_DATABASE_URL=f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
