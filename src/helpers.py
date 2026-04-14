import asyncio
import csv

from datetime import datetime, timezone
from logging import Logger
from pathlib import Path
from typing import Optional

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.types import Message

from config import MESSAGES_LOGS_DIR

STATS_CSV_HEADER = [
    "TimestampUTC",
    "ChatID",
    "UserID",
    "MessageID",
    "Message",
    "PredictedProba",
    "TrueLabel",
]

_csv_registry_lock = asyncio.Lock()
_csv_locks: dict[Path, asyncio.Lock] = {}


def normalize_message_for_stats(text: str) -> str:
    return " ".join(str(text).strip().split())


def _read_csv_header(path: Path) -> Optional[list[str]]:
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            return next(reader)
        except StopIteration:
            return []


def _write_stats_csv_header(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL).writerow(STATS_CSV_HEADER)


def ensure_stats_csv_ready(chat_id: int) -> Path:
    path = MESSAGES_LOGS_DIR / f"{chat_id}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    stats_header = _read_csv_header(path)

    if stats_header is None or stats_header == []:
        _write_stats_csv_header(path)
        return path

    if stats_header != STATS_CSV_HEADER:
        raise RuntimeError(
            f"Unexpected stats CSV header in {path}: {stats_header!r}. "
            f"Expected {STATS_CSV_HEADER!r}."
        )

    return path


async def _get_file_lock(path: Path) -> asyncio.Lock:
    async with _csv_registry_lock:
        if path not in _csv_locks:
            _csv_locks[path] = asyncio.Lock()
        return _csv_locks[path]


async def append_message_stats_to_csv(
    *,
    chat_id: int,
    user_id: int,
    message_id: int,
    text: str,
    predicted_proba: float,
    true_label: Optional[int] = None,
) -> None:
    text = normalize_message_for_stats(text)
    path = ensure_stats_csv_ready(chat_id)
    lock = await _get_file_lock(path)

    async with lock:
        timestamp_utc = datetime.now(timezone.utc).isoformat()
        with path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(
                [
                    timestamp_utc,
                    chat_id,
                    user_id,
                    message_id,
                    text,
                    predicted_proba,
                    "" if true_label is None else int(true_label),
                ]
            )


async def _notify_user(message: Message, text: str, timer: float | None = None, logger: Logger = None) -> None:
    if logger:
        logger.info("Notify user %s | text_preview=%r | timer=%s", message.from_user.id, text[:100], timer)
    x = await message.answer(text, parse_mode="HTML")
    if timer:
        await asyncio.sleep(timer)
        await x.delete()
        if logger:
            logger.debug("Deleted notification message for user %s", message.from_user.id)


async def CHAT_ADMIN_FILTER(message: Message, bot: Bot) -> bool:
    if message.sender_chat and message.sender_chat.id == message.chat.id:
        return True

    if message.from_user:
        try:
            member = await bot.get_chat_member(message.chat.id, message.from_user.id)
            return member.status in ("administrator", "creator")
        except Exception:
            return False

    return False


async def CHAT_NOT_BANNED_FILTER(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status not in [ChatMemberStatus.KICKED]
    except Exception:
        return True
