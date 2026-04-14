from datetime import datetime

from aiogram import Router, Bot
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION
from aiogram.types import Message, ChatMemberUpdated, PollAnswer

from config import MOSCOW_TZ, CAPTCHA_MAX_ATTEMPTS
from src.helpers import append_message_stats_to_csv, CHAT_ADMIN_FILTER
from src.test_classifier import predict_spam_proba
from src.database import get_session
from src.database.chat_member_state import (
    ChatMemberStateUpdate,
    get_chat_member_state,
    get_state_by_active_poll,
    update_chat_member_state,
    upsert_chat_member_state,
)
from src.database.moderated_chat import is_chat_moderated
from src.bot.handlers.chat_helpers import far_future, build_chat_member_state_create, extract_message_text, is_command_message
from src.bot.handlers.chat_shared import send_ephemeral_message, safe_ban_user, safe_delete_message
from src.bot.handlers.chat_captcha import start_captcha

router = Router(name="chat")


@router.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def handle_new_member(event: ChatMemberUpdated):
    user = event.new_chat_member.user
    if user.is_bot:
        return

    chat_id = event.chat.id
    async with get_session() as session:
        if not await is_chat_moderated(session, chat_id):
            return None

        state = await get_chat_member_state(session, chat_id, user.id)
        if state is None:
            await upsert_chat_member_state(
                session,
                build_chat_member_state_create(
                    chat_id,
                    user.id,
                    full_name=user.full_name or "",
                    username=user.username,
                    passed_poll=False,
                    messages_sent=0,
                ),
            )
            return None

        await update_chat_member_state(
            session,
            chat_id,
            user.id,
            ChatMemberStateUpdate(
                full_name=user.full_name or "",
                username=user.username,
                passed_poll=False,
                poll_attempts=0,
                poll_active=False,
                poll_message_id=None,
                poll_chat_id=None,
                poll_thread_id=None,
                poll_id=None,
                poll_correct_option_id=None,
                poll_started_at=None,
            ),
        )
    return None


@router.poll_answer()
async def handle_poll_answer(answer: PollAnswer, bot: Bot):
    user_id = answer.user.id
    poll_id = answer.poll_id
    chosen = answer.option_ids[0] if answer.option_ids else None
    now = datetime.now(tz=MOSCOW_TZ)

    async with get_session() as session:
        state = await get_state_by_active_poll(session, user_id=user_id, poll_id=poll_id)
        if not state or state.passed_poll:
            return None

        chat_id = state.chat_id
        msg_id = state.poll_message_id
        thread_id = state.poll_thread_id
        if msg_id:
            await safe_delete_message(bot, chat_id, msg_id)

        correct_id = state.poll_correct_option_id
        if chosen is not None and correct_id is not None and chosen == correct_id:
            await update_chat_member_state(
                session,
                chat_id,
                user_id,
                ChatMemberStateUpdate(
                    passed_poll=True,
                    poll_attempts=state.poll_attempts,
                    poll_active=False,
                    poll_chat_id=None,
                    poll_thread_id=None,
                    poll_message_id=None,
                    poll_id=None,
                    poll_correct_option_id=None,
                    poll_started_at=None,
                ),
            )
            await send_ephemeral_message(
                bot,
                chat_id,
                f"{answer.user.mention_html()}, проверка пройдена.\nТеперь вы можете отправлять сообщения в чат.",
                thread_id=thread_id,
            )
            return None

        attempts = (state.poll_attempts or 0) + 1
        if attempts >= CAPTCHA_MAX_ATTEMPTS:
            await update_chat_member_state(
                session,
                chat_id,
                user_id,
                ChatMemberStateUpdate(
                    poll_attempts=attempts,
                    poll_active=False,
                    poll_chat_id=None,
                    poll_thread_id=None,
                    poll_message_id=None,
                    poll_id=None,
                    poll_correct_option_id=None,
                    poll_started_at=None,
                    muted_until=far_future(now),
                    banned_until=None,
                    times_banned=(state.times_banned or 0) + 1,
                ),
            )
            await safe_ban_user(bot, chat_id, user_id)
            await send_ephemeral_message(
                bot,
                chat_id,
                f"{answer.user.mention_html()}, проверка не пройдена.\nКоличество попыток исчерпано. "
                "Права на отправку сообщений ограничены до решения администратора.",
                thread_id=thread_id,
            )
        else:
            await update_chat_member_state(
                session,
                chat_id,
                user_id,
                ChatMemberStateUpdate(
                    poll_attempts=attempts,
                    poll_active=False,
                    poll_chat_id=None,
                    poll_thread_id=None,
                    poll_message_id=None,
                    poll_id=None,
                    poll_correct_option_id=None,
                    poll_started_at=None,
                ),
            )
            left = CAPTCHA_MAX_ATTEMPTS - attempts
            await send_ephemeral_message(
                bot,
                chat_id,
                f"{answer.user.mention_html()}, ответ неверный.\nОсталось попыток: {left}. "
                "Для новой попытки отправьте любое сообщение в чат.",
                thread_id=thread_id,
            )

    return None


@router.message(lambda message: not is_command_message(message))
async def handle_chat_message(message: Message):
    text = await extract_message_text(message)
    if not text:
        return None
    user = message.from_user
    if not user:
        return None

    chat_id = message.chat.id
    trusted_user = await CHAT_ADMIN_FILTER(message, message.bot)
    passed_poll = True

    async with get_session() as session:
        if not await is_chat_moderated(session, chat_id):
            return None

        state = await get_chat_member_state(session, chat_id, user.id)
        if state is None:
            await upsert_chat_member_state(
                session,
                build_chat_member_state_create(
                    chat_id,
                    user.id,
                    full_name=user.full_name or "",
                    username=user.username,
                    passed_poll=trusted_user,
                    messages_sent=0,
                ),
            )
            state = await get_chat_member_state(session, chat_id, user.id)

        if state is None:
            return None

        trusted_user = trusted_user or bool(state.whitelist)
        passed_poll = trusted_user or bool(state.passed_poll)
        if passed_poll:
            new_messages_sent = (state.messages_sent or 0) + 1
            await update_chat_member_state(
                session,
                chat_id,
                user.id,
                ChatMemberStateUpdate(
                    full_name=user.full_name or "",
                    username=user.username,
                    messages_sent=new_messages_sent,
                ),
            )

    if not passed_poll:
        await safe_delete_message(message.bot, message.chat.id, message.message_id)
        await start_captcha(message.bot, message.chat.id, user.id, message.message_thread_id)
        return None

    proba_spam = await predict_spam_proba(text)
    await append_message_stats_to_csv(
        chat_id=chat_id,
        user_id=user.id,
        message_id=message.message_id,
        text=text,
        predicted_proba=proba_spam,
    )
    return None
