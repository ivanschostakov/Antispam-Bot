import asyncio
import random

from datetime import datetime
from html import escape
from typing import Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, User
from aiogram.utils.deep_linking import create_start_link

from config import MOSCOW_TZ, CAPTCHA_MAX_ATTEMPTS, POLL_TIMEOUT_BUFFER, POLL_TIMEOUT_SECONDS
from src.database import get_session
from src.database.crud import (
    get_chat_member_state, get_moderated_chat, get_poll_question_by_id, get_random_poll_for_chat, list_effective_poll_questions_for_chat, update_chat_member_state, upsert_chat_member_state,
)
from src.database.schemas import ChatMemberStateUpdate
from src.bot.services.chat_tools import build_chat_member_state_create, far_future, is_permanently_banned
from src.bot.services.state_updates import poll_reset_state
from src.bot.services.telegram_tools import safe_ban_user, safe_delete_message, send_ephemeral_message


def _parse_question_order(raw: str | None) -> list[int]:
    if not raw: return []
    result: list[int] = []
    for item in raw.split(","):
        item = item.strip()
        if not item: continue
        try: result.append(int(item))
        except ValueError: continue
    return result


def _serialize_question_order(question_ids: list[int]) -> str: return ",".join(str(question_id) for question_id in question_ids)

def _build_user_shuffled_question_order(question_ids: list[int], user_id: int) -> list[int]:
    shuffled = list(question_ids)
    random.Random(user_id).shuffle(shuffled)
    return shuffled


def _is_valid_poll_question(question) -> bool:
    if question is None: return False
    options = [question.right, question.wrong1, question.wrong2, question.wrong3]
    if any(not option or not option.strip() for option in options): return False
    return len({option.strip().casefold() for option in options}) == 4


async def build_start_keyboard(bot: Bot, chat_id: int) -> InlineKeyboardMarkup:
    start_link = await create_start_link(bot, payload=str(chat_id), encode=True)
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Пройти проверку", url=start_link)]],)


async def send_join_greeting(bot: Bot, chat_id: int, user: User, *, greeting_text: str | None = None, thread_id: Optional[int] = None) -> None:
    keyboard = await build_start_keyboard(bot, chat_id)
    intro = (greeting_text or "").strip() or "Добро пожаловать. Чтобы писать в чат, сначала пройдите проверку."
    text = f"<b>{user.mention_html()}</b>, {intro}\nНажмите кнопку ниже и ответьте на вопросы в личке с ботом."
    await send_ephemeral_message(bot, chat_id, text, thread_id=thread_id, reply_markup=keyboard)


async def captcha_timeout_worker(bot: Bot, poll_id: str, user_id: int, chat_id: int, thread_id: Optional[int], timeout: int = POLL_TIMEOUT_SECONDS + POLL_TIMEOUT_BUFFER) -> None:
    await asyncio.sleep(timeout)
    now = datetime.now(tz=MOSCOW_TZ)
    async with get_session() as session:
        user = await get_chat_member_state(session, chat_id, user_id)
        if not user: return
        if user.passed_poll or not user.poll_active or not user.poll_id or user.poll_id != poll_id: return

        is_deep_flow = bool((user.poll_question_order or "").strip())
        delivery_chat_id = user.poll_chat_id or (user_id if is_deep_flow else chat_id)
        thread_id_db = user.poll_thread_id if user.poll_thread_id is not None else thread_id
        msg_id = user.poll_message_id
        if msg_id: await safe_delete_message(bot, delivery_chat_id, msg_id)

        attempts = (user.poll_attempts or 0) + 1
        if attempts >= CAPTCHA_MAX_ATTEMPTS:
            await update_chat_member_state(session, chat_id, user_id, poll_reset_state(poll_attempts=attempts, muted_until=far_future(now), banned_until=None, times_banned=(user.times_banned or 0) + 1, poll_question_order=None, poll_question_index=0, ), )
            await safe_ban_user(bot, chat_id, user_id)
            await send_ephemeral_message(bot, chat_id, f'<a href="tg://user?id={user_id}">Пользователь</a> не прошёл проверку.\nКоличество попыток исчерпано. Права на отправку сообщений ограничены до решения администратора.', )
            if is_deep_flow: await send_ephemeral_message(bot, user_id, "Проверка не пройдена. Количество попыток исчерпано.")
            return

        await update_chat_member_state(session, chat_id, user_id, poll_reset_state(poll_attempts=attempts, poll_question_order=user.poll_question_order if is_deep_flow else None, poll_question_index=user.poll_question_index if is_deep_flow else 0, ),     )

        left = CAPTCHA_MAX_ATTEMPTS - attempts
        if is_deep_flow:
            keyboard = await build_start_keyboard(bot, chat_id)
            await send_ephemeral_message(bot, user_id, f"Время ответа истекло. Осталось попыток: {left}. Нажмите кнопку, чтобы продолжить.", reply_markup=keyboard, )
            return

        await send_ephemeral_message(
            bot, chat_id, f'<a href="tg://user?id={user_id}">Пользователь</a> не успел ответить на проверочный вопрос.\nОсталось попыток: {left}. Для новой попытки нужно отправить сообщение в чат.', thread_id=thread_id_db,     )


async def start_captcha(bot: Bot, chat_id: int, user_id: int, thread_id: Optional[int]) -> None:
    now = datetime.now(tz=MOSCOW_TZ)
    async with get_session() as session:
        user = await get_chat_member_state(session, chat_id, user_id)
        if user is None:
            await upsert_chat_member_state(session, build_chat_member_state_create(chat_id, user_id, full_name="", username=None, passed_poll=False, messages_sent=0), )
            user = await get_chat_member_state(session, chat_id, user_id)

        if user is None or is_permanently_banned(user, now): return

        if user.poll_attempts >= CAPTCHA_MAX_ATTEMPTS and not user.passed_poll:
            await send_ephemeral_message(bot, chat_id, f'<a href="tg://user?id={user_id}">Пользователь</a> не прошёл проверку.\nПрава на отправку сообщений ограничены до решения администратора.', thread_id=thread_id)
            return

        if user.poll_active and user.poll_message_id and user.poll_chat_id:
            if user.poll_chat_id == chat_id: await send_ephemeral_message(bot, chat_id, f'<a href="tg://user?id={user_id}">Пользователь</a>, у вас уже есть активный вопрос выше. Сначала ответьте на него.', thread_id=thread_id, )
            else:
                keyboard = await build_start_keyboard(bot, chat_id)
                await send_ephemeral_message(bot, chat_id, f'<a href="tg://user?id={user_id}">Пользователь</a>, у вас уже есть активная проверка в личке с ботом.', thread_id=thread_id, reply_markup=keyboard, )
            return

        moderated_chat = await get_moderated_chat(session, chat_id)
        greeting = (moderated_chat.greetings_message or "").strip() if moderated_chat else ""
        if greeting: await send_ephemeral_message(bot, chat_id, greeting, thread_id=thread_id)

        poll_question = await get_random_poll_for_chat(session, chat_id)
        if poll_question is None:
            await send_ephemeral_message(bot, chat_id, "Не удалось запустить проверку: в базе нет доступных вопросов.", thread_id=thread_id)
            return

        options_with_mark = [(poll_question.right, True), (poll_question.wrong1, False), (poll_question.wrong2, False), (poll_question.wrong3, False),     ]
        random.shuffle(options_with_mark)
        options = [answer_text for answer_text, _ in options_with_mark]
        correct_option_id = next(idx for idx, (_, is_right) in enumerate(options_with_mark) if is_right)

        await send_ephemeral_message(bot, chat_id, "Для отправки сообщений в чат необходимо пройти простую проверку.\nОтветьте на вопрос ниже. Всего доступно три попытки.", thread_id=thread_id,     )
        kwargs = {"message_thread_id": thread_id} if thread_id is not None else {}
        poll_message = await bot.send_poll(chat_id=chat_id, question=poll_question.question, options=options, type="quiz", correct_option_id=correct_option_id, is_anonymous=False, open_period=POLL_TIMEOUT_SECONDS, **kwargs,     )

        await update_chat_member_state(session, chat_id, user_id, ChatMemberStateUpdate(poll_active=True, poll_chat_id=chat_id, poll_thread_id=thread_id, poll_message_id=poll_message.message_id, poll_id=poll_message.poll.id, poll_correct_option_id=correct_option_id, poll_started_at=now, poll_question_order=None, poll_question_index=0, ),     )

    asyncio.create_task(captcha_timeout_worker(bot, poll_message.poll.id, user_id, chat_id, thread_id, timeout=POLL_TIMEOUT_SECONDS + POLL_TIMEOUT_BUFFER))


async def _resolve_question_order_for_user(session, chat_id: int, user) -> tuple[list[int], int]:
    existing_order = _parse_question_order(user.poll_question_order)
    if existing_order:
        index = max(0, min(user.poll_question_index or 0, len(existing_order) - 1))
        return existing_order, index

    questions = await list_effective_poll_questions_for_chat(session, chat_id)
    valid_questions = [question for question in questions if _is_valid_poll_question(question)]
    if not valid_questions: return [], 0

    ordered_ids = _build_user_shuffled_question_order([question.id for question in valid_questions], user.user_id)
    return ordered_ids, 0


async def _send_deep_poll_step(bot: Bot, *, chat_id: int, user, delivery_chat_id: int, now: datetime) -> bool:
    async with get_session() as session:
        question_ids, index = await _resolve_question_order_for_user(session, chat_id, user)
        if not question_ids:
            await send_ephemeral_message(bot, delivery_chat_id, "Не удалось запустить проверку: в базе нет доступных вопросов.")
            return False

        question_id = question_ids[index]
        poll_question = await get_poll_question_by_id(session, question_id)
        if not _is_valid_poll_question(poll_question):
            await send_ephemeral_message(bot, delivery_chat_id, "Не удалось запустить проверку: вопрос недоступен. Попробуйте ещё раз.")
            return False

        options_with_mark = [(poll_question.right, True), (poll_question.wrong1, False), (poll_question.wrong2, False), (poll_question.wrong3, False),     ]
        random.shuffle(options_with_mark)
        options = [answer_text for answer_text, _ in options_with_mark]
        correct_option_id = next(idx for idx, (_, is_right) in enumerate(options_with_mark) if is_right)

        await send_ephemeral_message(bot, delivery_chat_id, f"Вопрос {index + 1} из {len(question_ids)}. Выберите правильный вариант.")
        poll_message = await bot.send_poll(chat_id=delivery_chat_id, question=poll_question.question, options=options, type="quiz", correct_option_id=correct_option_id, is_anonymous=False, open_period=POLL_TIMEOUT_SECONDS,     )

        await update_chat_member_state(session, chat_id, user.user_id, ChatMemberStateUpdate(poll_active=True, poll_chat_id=delivery_chat_id, poll_thread_id=None, poll_message_id=poll_message.message_id, poll_id=poll_message.poll.id, poll_correct_option_id=correct_option_id, poll_started_at=now, poll_question_order=_serialize_question_order(question_ids), poll_question_index=index, ),     )

    asyncio.create_task(captcha_timeout_worker(bot, poll_message.poll.id, user.user_id, chat_id, None, timeout=POLL_TIMEOUT_SECONDS + POLL_TIMEOUT_BUFFER))
    return True


async def start_deep_captcha(bot: Bot, chat_id: int, user_id: int, *, delivery_chat_id: Optional[int] = None) -> None:
    now = datetime.now(tz=MOSCOW_TZ)
    delivery_chat_id = delivery_chat_id or user_id

    async with get_session() as session:
        user = await get_chat_member_state(session, chat_id, user_id)
        if user is None:
            await upsert_chat_member_state(session, build_chat_member_state_create(chat_id, user_id, full_name="", username=None, passed_poll=False, messages_sent=0), )
            user = await get_chat_member_state(session, chat_id, user_id)

        if user is None or is_permanently_banned(user, now): return

        if user.passed_poll:
            await send_ephemeral_message(bot, delivery_chat_id, "Проверка уже пройдена. Можно писать в чат.")
            return

        if user.poll_attempts >= CAPTCHA_MAX_ATTEMPTS:
            await send_ephemeral_message(bot, delivery_chat_id, "Права на отправку сообщений ограничены до решения администратора.")
            return

        if user.poll_active and user.poll_message_id and user.poll_chat_id:
            await send_ephemeral_message(bot, delivery_chat_id, "У вас уже есть активный вопрос. Сначала ответьте на него.")
            return

    fresh_now = datetime.now(tz=MOSCOW_TZ)
    await _send_deep_poll_step(bot, chat_id=chat_id, user=user, delivery_chat_id=delivery_chat_id, now=fresh_now)
