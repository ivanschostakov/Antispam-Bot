from typing import Optional
from aiogram.enums import ChatType
from aiogram.types import Message

from src.bot.services.chat_tools import build_chat_member_state_create
from src.bot.services.telegram_tools import answer_ephemeral
from src.database import get_session
from src.database.crud import (
    get_chat_member_state,
    is_chat_moderated,
    list_moderated_chat_ids,
    upsert_chat_member_state,
)


async def is_admin_or_creator(bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception: return False


async def admin_or_private_admin_filter(message: Message, bot) -> bool:
    if message.chat.type != ChatType.PRIVATE:
        is_chat_add_command = (message.text or "").strip().startswith("/chat_add")
        async with get_session() as session:
            if not await is_chat_moderated(session, message.chat.id) and not is_chat_add_command: return False
        if message.sender_chat and message.sender_chat.id == message.chat.id: return True
        if not message.from_user: return False
        return await is_admin_or_creator(bot, message.chat.id, message.from_user.id)

    if not message.from_user: return False
    async with get_session() as session: chat_ids = await list_moderated_chat_ids(session)
    for chat_id in chat_ids:
        if await is_admin_or_creator(bot, chat_id, message.from_user.id): return True
    return False


async def group_admin_filter(message: Message, bot) -> bool:
    if message.chat.type == ChatType.PRIVATE: return False
    async with get_session() as session:
        if not await is_chat_moderated(session, message.chat.id): return False
    if message.sender_chat and message.sender_chat.id == message.chat.id: return True
    if not message.from_user: return False
    return await is_admin_or_creator(bot, message.chat.id, message.from_user.id)


async def private_admin_filter(message: Message, bot) -> bool:
    if message.chat.type != ChatType.PRIVATE or not message.from_user: return False
    async with get_session() as session: chat_ids = await list_moderated_chat_ids(session)
    for chat_id in chat_ids:
        if await is_admin_or_creator(bot, chat_id, message.from_user.id): return True
    return False


async def require_moderated_chat_context(message: Message) -> int | None:
    if message.chat.type == ChatType.PRIVATE:
        await answer_ephemeral(message, "Эту команду нужно запускать внутри модерируемого чата.")
        return None

    async with get_session() as session:
        if await is_chat_moderated(session, message.chat.id): return message.chat.id

    await answer_ephemeral(message, "Этот чат не находится в списке модерируемых.")
    return None


async def ensure_chat_state(session, chat_id: int, user_id: int, full_name: str = "", username: Optional[str] = None):
    state = await get_chat_member_state(session, chat_id, user_id)
    if state is not None: return state

    await upsert_chat_member_state(session, build_chat_member_state_create(chat_id, user_id, full_name=full_name, username=username, passed_poll=True, messages_sent=0))
    return await get_chat_member_state(session, chat_id, user_id)
