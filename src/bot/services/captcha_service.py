import asyncio
import random

from datetime import datetime
from html import escape
from typing import Optional

from aiogram import Bot
from aiogram.types import User

from config import MOSCOW_TZ, CAPTCHA_MAX_ATTEMPTS, POLL_TIMEOUT_BUFFER, POLL_TIMEOUT_SECONDS
from src.bot.services.chat_tools import build_chat_member_state_create, far_future, is_permanently_banned
from src.bot.services.state_updates import poll_reset_state
from src.bot.services.telegram_tools import safe_ban_user, safe_delete_message, send_ephemeral_message
from src.database import get_session
from src.database.crud import get_chat_member_state, get_random_default_poll_question, update_chat_member_state, upsert_chat_member_state
from src.database.schemas import ChatMemberStateUpdate


def _is_valid_poll_question(question) -> bool:
    if question is None:
        return False
    options = [question.right, question.wrong1, question.wrong2, question.wrong3]
    if any(not option or not option.strip() for option in options):
        return False
    return len({option.strip().casefold() for option in options}) == 4


async def send_join_greeting(
    bot: Bot,
    chat_id: int,
    user: User,
    *,
    greeting_text: str | None = None,
    thread_id: Optional[int] = None,
) -> None:
    intro = (greeting_text or "").strip() or "Добро пожаловать. Чтобы писать в чат, сначала пройдите проверку."
    text = f"{user.mention_html()}, {intro}\nПроверочный вопрос появится, когда вы отправите первое сообщение."
    await send_ephemeral_message(bot, chat_id, text, thread_id=thread_id)


async def captcha_timeout_worker(
    bot: Bot,
    poll_id: str,
    user_id: int,
    chat_id: int,
    thread_id: Optional[int],
    timeout: int = POLL_TIMEOUT_SECONDS + POLL_TIMEOUT_BUFFER,
) -> None:
    await asyncio.sleep(timeout)
    now = datetime.now(tz=MOSCOW_TZ)
    async with get_session() as session:
        user = await get_chat_member_state(session, chat_id, user_id)
        if not user or user.passed_poll or not user.poll_active or not user.poll_id or user.poll_id != poll_id:
            return

        delivery_chat_id = user.poll_chat_id or chat_id
        thread_id_db = user.poll_thread_id if user.poll_thread_id is not None else thread_id
        if user.poll_message_id:
            await safe_delete_message(bot, delivery_chat_id, user.poll_message_id)

        attempts = (user.poll_attempts or 0) + 1
        if attempts >= CAPTCHA_MAX_ATTEMPTS:
            await update_chat_member_state(
                session,
                chat_id,
                user_id,
                poll_reset_state(
                    poll_attempts=attempts,
                    muted_until=far_future(now),
                    banned_until=None,
                    times_banned=(user.times_banned or 0) + 1,
                ),
            )
            await safe_ban_user(bot, chat_id, user_id)
            await send_ephemeral_message(
                bot,
                chat_id,
                f'<a href="tg://user?id={user_id}">Пользователь</a> не прошёл проверку.\n'
                "Количество попыток исчерпано. Права на отправку сообщений ограничены до решения администратора.",
                thread_id=thread_id_db,
            )
            return

        await update_chat_member_state(session, chat_id, user_id, poll_reset_state(poll_attempts=attempts))
        left = CAPTCHA_MAX_ATTEMPTS - attempts
        await send_ephemeral_message(
            bot,
            chat_id,
            f'<a href="tg://user?id={user_id}">Пользователь</a> не успел ответить на проверочный вопрос.\n'
            f"Осталось попыток: {left}. Для новой попытки отправьте сообщение в чат.",
            thread_id=thread_id_db,
        )


async def start_captcha(bot: Bot, chat_id: int, user_id: int, thread_id: Optional[int]) -> None:
    now = datetime.now(tz=MOSCOW_TZ)
    async with get_session() as session:
        user = await get_chat_member_state(session, chat_id, user_id)
        if user is None:
            await upsert_chat_member_state(
                session,
                build_chat_member_state_create(
                    chat_id,
                    user_id,
                    full_name="",
                    username=None,
                    passed_poll=False,
                    messages_sent=0,
                ),
            )
            user = await get_chat_member_state(session, chat_id, user_id)

        if user is None or is_permanently_banned(user, now):
            return

        if user.poll_attempts >= CAPTCHA_MAX_ATTEMPTS and not user.passed_poll:
            await send_ephemeral_message(
                bot,
                chat_id,
                f'<a href="tg://user?id={user_id}">Пользователь</a> не прошёл проверку.\n'
                "Права на отправку сообщений ограничены до решения администратора.",
                thread_id=thread_id,
            )
            return

        if user.poll_active and user.poll_message_id and user.poll_chat_id:
            await send_ephemeral_message(
                bot,
                chat_id,
                f'<a href="tg://user?id={user_id}">Пользователь</a>, у вас уже есть активный вопрос выше. '
                "Сначала ответьте на него.",
                thread_id=thread_id,
            )
            return

        poll_question = await get_random_default_poll_question(session)
        if poll_question is None or not _is_valid_poll_question(poll_question):
            await send_ephemeral_message(
                bot,
                chat_id,
                "Не удалось запустить проверку: в базе нет доступных дефолтных вопросов.",
                thread_id=thread_id,
            )
            return

        options_with_mark = [
            (poll_question.right, True),
            (poll_question.wrong1, False),
            (poll_question.wrong2, False),
            (poll_question.wrong3, False),
        ]
        random.shuffle(options_with_mark)
        options = [answer_text for answer_text, _ in options_with_mark]
        correct_option_id = next(idx for idx, (_, is_right) in enumerate(options_with_mark) if is_right)

        mention_html = f'<a href="tg://user?id={user_id}">{escape((user.full_name or "").strip() or "Пользователь")}</a>'
        await send_ephemeral_message(
            bot,
            chat_id,
            f"{mention_html}, чтобы отправлять сообщения в чат, ответьте на проверочный вопрос ниже. "
            "Всего доступно три попытки.",
            thread_id=thread_id,
        )

        kwargs = {"message_thread_id": thread_id} if thread_id is not None else {}
        poll_message = await bot.send_poll(
            chat_id=chat_id,
            question=poll_question.question,
            options=options,
            type="quiz",
            correct_option_id=correct_option_id,
            is_anonymous=False,
            open_period=POLL_TIMEOUT_SECONDS,
            **kwargs,
        )

        await update_chat_member_state(
            session,
            chat_id,
            user_id,
            ChatMemberStateUpdate(
                poll_active=True,
                poll_chat_id=chat_id,
                poll_thread_id=thread_id,
                poll_message_id=poll_message.message_id,
                poll_id=poll_message.poll.id,
                poll_correct_option_id=correct_option_id,
                poll_started_at=now,
            ),
        )

    asyncio.create_task(
        captcha_timeout_worker(
            bot,
            poll_message.poll.id,
            user_id,
            chat_id,
            thread_id,
            timeout=POLL_TIMEOUT_SECONDS + POLL_TIMEOUT_BUFFER,
        )
    )
