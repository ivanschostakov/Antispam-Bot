from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import REPORTS_CHANNEL_ID
from src.bot.handlers.chat_helpers import build_chat_member_state_create
from src.bot.handlers.chat_shared import answer_ephemeral
from src.database import get_session
from src.database.crud import (
    get_chat_member_state,
    is_chat_moderated,
    update_chat_member_state,
    upsert_chat_member_state,
)
from src.database.schemas import ChatMemberStateUpdate

router = Router(name="user")


@router.message(Command("report"))
async def handle_report(message: Message):
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await answer_ephemeral(
            message,
            "Ответьте командой <code>/report</code> на сообщение пользователя, на которого хотите пожаловаться.",
        )

    if message.from_user is None:
        return None

    chat_id = message.chat.id
    target = message.reply_to_message.from_user
    if target.id == message.from_user.id:
        return await answer_ephemeral(message, "Нельзя отправить жалобу на самого себя.")

    async with get_session() as session:
        if not await is_chat_moderated(session, chat_id):
            return await answer_ephemeral(message, "Этот чат не находится в списке модерируемых.")

        state = await get_chat_member_state(session, chat_id, target.id)
        if state is None:
            await upsert_chat_member_state(
                session,
                build_chat_member_state_create(
                    chat_id,
                    target.id,
                    full_name=target.full_name or "",
                    username=target.username,
                    passed_poll=True,
                    messages_sent=0,
                ),
            )
            state = await get_chat_member_state(session, chat_id, target.id)

        if state is None:
            return await answer_ephemeral(message, "Не удалось обработать жалобу, попробуйте ещё раз.")

        await update_chat_member_state(
            session,
            chat_id,
            target.id,
            ChatMemberStateUpdate(
                times_reported=(state.times_reported or 0) + 1,
                accused_spam=False,
            ),
        )

    await answer_ephemeral(message, "Спасибо, жалоба отправлена. Администраторы чата смогут её увидеть.")

    await message.reply_to_message.forward(REPORTS_CHANNEL_ID)
    return await message.forward(REPORTS_CHANNEL_ID)
