import asyncio

from datetime import datetime, timedelta
from typing import Optional

from aiogram.enums import MessageEntityType
from aiogram.types import Message

from src.image import extract_text_from_image
from src.database.crud import update_chat_member_state
from src.database.schemas import ChatMemberStateCreate, ChatMemberStateUpdate
from src.database.utils import extract_base_domain, normalize_allowed_link

PERMANENT_RESTRICTION_DAYS = 365 * 100
PERMANENT_BAN_THRESHOLD_DAYS = 365 * 10


def is_command_message(message: Message) -> bool:
    entities = list(message.entities or []) + list(message.caption_entities or [])
    return any(entity.type == MessageEntityType.BOT_COMMAND and entity.offset == 0 for entity in entities)


def far_future(now: datetime) -> datetime: return now + timedelta(days=PERMANENT_RESTRICTION_DAYS)
def is_permanently_banned(user, now: datetime) -> bool: return bool(user and user.banned_until and user.banned_until > now + timedelta(days=PERMANENT_BAN_THRESHOLD_DAYS))


def build_chat_member_state_create(chat_id: int, user_id: int, full_name: str, username: Optional[str], *, passed_poll: bool, messages_sent: int) -> ChatMemberStateCreate:
    return ChatMemberStateCreate(
        chat_id=chat_id, user_id=user_id, full_name=full_name, username=username, passed_poll=passed_poll, whitelist=False,
        muted_until=None, times_muted=0, banned_until=None, times_banned=0, messages_sent=messages_sent, times_reported=0,
        accused_spam=False, last_accused_text=None, poll_attempts=0, poll_active=False, poll_message_id=None, poll_chat_id=None,
        poll_thread_id=None, poll_id=None, poll_correct_option_id=None, poll_started_at=None, poll_question_order=None, poll_question_index=0,
    )


def mute_label(mute_delta: timedelta) -> str:
    if mute_delta.days >= 30: return "на 1 месяц"
    if mute_delta.days >= 7: return "на 1 неделю"
    if mute_delta.days >= 1: return "на 1 день"
    return "временно"


def resolve_spam_mute_delta(times_muted: int) -> Optional[timedelta]:
    if times_muted == 2: return timedelta(days=1)
    if times_muted == 3: return timedelta(weeks=1)
    if times_muted == 4: return timedelta(days=30)
    return None


def extract_entity_links(message: Message) -> set[str]:
    domains: set[str] = set()
    for entity in (message.entities or []) + (message.caption_entities or []):
        if entity.type != MessageEntityType.TEXT_LINK or not entity.url: continue
        allowed_target = normalize_allowed_link(entity.url)
        if allowed_target: domains.add(allowed_target)
        entity_domain = extract_base_domain(entity.url)
        if entity_domain: domains.add(entity_domain)
    return domains


async def extract_message_text(message: Message) -> str:
    text_parts: list[str] = []
    if message.text and message.text.strip(): text_parts.append(message.text.strip())
    if message.caption and message.caption.strip(): text_parts.append(message.caption.strip())
    if message.photo:
        largest_photo = message.photo[-1]
        file = await message.bot.get_file(largest_photo.file_id)
        image_bytes = await message.bot.download_file(file.file_path)
        ocr_text = await asyncio.to_thread(extract_text_from_image, image_bytes)
        print(ocr_text)
        if ocr_text and ocr_text.strip(): text_parts.append(ocr_text.strip())
    return "\n".join(text_parts).strip()


async def apply_permanent_restriction(chat_id: int, user_id: int, chat_user, session, now: datetime, text: str, times_muted: Optional[int] = None) -> None:
    payload = {
        "times_reported": (chat_user.times_reported if chat_user else 0) + 1,
        "accused_spam": True,
        "last_accused_text": text[:1024],
        "banned_until": None,
        "muted_until": far_future(now),
        "times_banned": (chat_user.times_banned if chat_user else 0) + 1,
    }
    if times_muted is not None: payload["times_muted"] = times_muted
    await update_chat_member_state(session, chat_id, user_id, ChatMemberStateUpdate(**payload))
