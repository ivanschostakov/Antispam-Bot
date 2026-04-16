from aiogram.types import Message
from aiogram.utils.deep_linking import decode_payload

from config import REPORTS_CHANNEL_ID
from src.bot.services.captcha_service import start_deep_captcha
from src.bot.services.chat_tools import build_chat_member_state_create
from src.bot.services.telegram_tools import answer_ephemeral
from src.database import get_session
from src.database.crud import get_chat_member_state, is_chat_moderated, update_chat_member_state, upsert_chat_member_state
from src.database.schemas import ChatMemberStateUpdate


async def on_report(message: Message):
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await answer_ephemeral(message, "Ответьте командой <code>/report</code> на сообщение пользователя, на которого хотите пожаловаться.")
    if message.from_user is None: return None

    chat_id, target = message.chat.id, message.reply_to_message.from_user
    if target.id == message.from_user.id: return await answer_ephemeral(message, "Нельзя отправить жалобу на самого себя.")

    async with get_session() as session:
        if not await is_chat_moderated(session, chat_id): return await answer_ephemeral(message, "Этот чат не находится в списке модерируемых.")

        state = await get_chat_member_state(session, chat_id, target.id)
        if state is None:
            await upsert_chat_member_state(session, build_chat_member_state_create(chat_id, target.id, full_name=target.full_name or "", username=target.username, passed_poll=True, messages_sent=0))
            state = await get_chat_member_state(session, chat_id, target.id)
        if state is None: return await answer_ephemeral(message, "Не удалось обработать жалобу, попробуйте ещё раз.")

        await update_chat_member_state(session, chat_id, target.id, ChatMemberStateUpdate(times_reported=(state.times_reported or 0) + 1, accused_spam=False))

    await answer_ephemeral(message, "Спасибо, жалоба отправлена. Администраторы чата смогут её увидеть.")
    await message.reply_to_message.forward(REPORTS_CHANNEL_ID)
    return await message.forward(REPORTS_CHANNEL_ID)


async def on_private_start(message: Message):
    text = (message.text or "").strip()
    if not message.from_user:
        return None

    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return await answer_ephemeral(
            message,
            "Эта команда запускается из кнопки проверки в групповом чате.",
        )

    try:
        payload = decode_payload(parts[1])
    except Exception:
        payload = parts[1]

    try:
        chat_id = int(payload)
    except ValueError:
        return await answer_ephemeral(message, "Неверная ссылка запуска проверки.")

    async with get_session() as session:
        if not await is_chat_moderated(session, chat_id):
            return await answer_ephemeral(message, "Этот чат не модерируется ботом.")

        state = await get_chat_member_state(session, chat_id, message.from_user.id)
        if state is None:
            await upsert_chat_member_state(
                session,
                build_chat_member_state_create(
                    chat_id,
                    message.from_user.id,
                    full_name=message.from_user.full_name or "",
                    username=message.from_user.username,
                    passed_poll=False,
                    messages_sent=0,
                ),
            )

    await start_deep_captcha(message.bot, chat_id, message.from_user.id, delivery_chat_id=message.chat.id)
    return None
