import asyncio

from datetime import datetime, timedelta
from aiogram import Bot
from aiogram.types import ChatMemberUpdated, Message, PollAnswer

from config import MOSCOW_TZ, CAPTCHA_MAX_ATTEMPTS
from src.helpers import CHAT_ADMIN_FILTER, append_message_stats_to_csv
from src.test_classifier import predict_spam_proba
from src.database import get_session
from src.database.crud import (
    add_moderated_chat,
    get_allowed_links,
    get_chat_member_state,
    get_moderated_chat,
    get_state_by_active_poll,
    is_chat_moderated,
    update_chat_member_state,
    upsert_chat_member_state,
)
from src.database.schemas import ChatMemberStateUpdate
from src.bot.services.state_updates import poll_reset_state
from src.database.utils import extract_allowed_targets_from_text
from src.bot.services.captcha_service import send_join_greeting, start_captcha, start_deep_captcha
from src.bot.services.chat_tools import (
    build_chat_member_state_create,
    extract_entity_links,
    extract_message_text,
    far_future,
)
from src.bot.services.telegram_tools import pass_user, safe_ban_user, safe_delete_message, safe_restrict, send_ephemeral_message
from src.bot.permissions import NEW_USER


def _parse_question_order(raw: str | None) -> list[int]:
    if not raw:
        return []
    result: list[int] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            result.append(int(item))
        except ValueError:
            continue
    return result


async def on_bot_status_changed(event: ChatMemberUpdated):
    chat_type, old_status, new_status = event.chat.type, event.old_chat_member.status, event.new_chat_member.status
    if chat_type not in {"group", "supergroup"} or new_status not in {"administrator", "creator"}:
        return None

    member = event.new_chat_member
    has_rights = new_status == "creator" or (getattr(member, "can_delete_messages", False) and getattr(member, "can_restrict_members", False))
    if not has_rights:
        return None

    async with get_session() as session:
        added = await add_moderated_chat(session, event.chat.id)

    if old_status in {"left", "kicked"} or old_status != new_status or added:
        await event.bot.send_message(
            event.chat.id,
            "Антиспам-бот активирован для этого чата.\n"
            "Чат добавлен в список модерируемых.\n"
            "Приветствие можно задать командой <code>/set_greeting ...</code> в чате или <code>/set_greetings CHAT_ID ...</code> в личке.",
        )
    return None


async def on_new_member(event: ChatMemberUpdated):
    user = event.new_chat_member.user
    if user.is_bot:
        return None

    chat_id = event.chat.id
    async with get_session() as session:
        moderated_chat = await get_moderated_chat(session, chat_id)
        if moderated_chat is None:
            return None

        state = await get_chat_member_state(session, chat_id, user.id)
        if state is None:
            await upsert_chat_member_state(session, build_chat_member_state_create(chat_id, user.id, full_name=user.full_name or "", username=user.username, passed_poll=False, messages_sent=0))
        else:
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
                    poll_question_order=None,
                    poll_question_index=0,
                ),
            )

    await send_join_greeting(
        event.bot,
        chat_id,
        user,
        user_full_name=user.full_name or "",
        greeting_text=moderated_chat.greetings_message if moderated_chat else None,
        thread_id=22,
    )
    return None


async def on_poll_answer(answer: PollAnswer, bot: Bot):
    user_id, poll_id = answer.user.id, answer.poll_id
    chosen = answer.option_ids[0] if answer.option_ids else None
    now = datetime.now(tz=MOSCOW_TZ)

    async with get_session() as session:
        state = await get_state_by_active_poll(session, user_id=user_id, poll_id=poll_id)
        if not state or state.passed_poll:
            return None

        chat_id, msg_id, thread_id = state.chat_id, state.poll_message_id, state.poll_thread_id
        delivery_chat_id = state.poll_chat_id or chat_id
        if msg_id:
            await safe_delete_message(bot, delivery_chat_id, msg_id)

        is_deep_flow = bool((state.poll_question_order or "").strip())
        correct_id = state.poll_correct_option_id
        if chosen is not None and correct_id is not None and chosen == correct_id:
            if is_deep_flow:
                order = _parse_question_order(state.poll_question_order)
                next_index = (state.poll_question_index or 0) + 1
                if order and next_index < len(order):
                    await update_chat_member_state(
                        session,
                        chat_id,
                        user_id,
                        poll_reset_state(
                            poll_attempts=state.poll_attempts,
                            poll_question_order=state.poll_question_order,
                            poll_question_index=next_index,
                        ),
                    )
                    await send_ephemeral_message(bot, delivery_chat_id, "Ответ верный. Следующий вопрос.")
                    await start_deep_captcha(bot, chat_id, user_id, delivery_chat_id=delivery_chat_id)
                    return None

                await update_chat_member_state(
                    session,
                    chat_id,
                    user_id,
                    poll_reset_state(passed_poll=True, poll_attempts=state.poll_attempts, poll_question_order=None, poll_question_index=0),
                )
                await send_ephemeral_message(bot, delivery_chat_id, "Проверка пройдена. Теперь вы можете отправлять сообщения в чат.")
                await send_ephemeral_message(bot, chat_id, f"{answer.user.mention_html()}, проверка пройдена. Теперь вы можете отправлять сообщения в чат.")
                return None

            await update_chat_member_state(session, chat_id, user_id, poll_reset_state(passed_poll=True, poll_attempts=state.poll_attempts, poll_question_order=None, poll_question_index=0))
            await send_ephemeral_message(bot, chat_id, f"{answer.user.mention_html()}, проверка пройдена.\nТеперь вы можете отправлять сообщения в чат.", thread_id=thread_id)
            return None

        attempts = (state.poll_attempts or 0) + 1
        if attempts >= CAPTCHA_MAX_ATTEMPTS:
            await update_chat_member_state(
                session,
                chat_id,
                user_id,
                poll_reset_state(
                    poll_attempts=attempts,
                    muted_until=far_future(now),
                    banned_until=None,
                    times_banned=(state.times_banned or 0) + 1,
                    poll_question_order=None,
                    poll_question_index=0,
                ),
            )
            await safe_ban_user(bot, chat_id, user_id)
            if is_deep_flow:
                await send_ephemeral_message(bot, chat_id, f"{answer.user.mention_html()}, проверка не пройдена.\nКоличество попыток исчерпано. Права на отправку сообщений ограничены до решения администратора.")
                await send_ephemeral_message(bot, delivery_chat_id, "Проверка не пройдена. Количество попыток исчерпано.")
            else:
                await send_ephemeral_message(bot, chat_id, f"{answer.user.mention_html()}, проверка не пройдена.\nКоличество попыток исчерпано. Права на отправку сообщений ограничены до решения администратора.", thread_id=thread_id)
            return None

        if is_deep_flow:
            await update_chat_member_state(
                session,
                chat_id,
                user_id,
                poll_reset_state(poll_attempts=attempts, poll_question_order=state.poll_question_order, poll_question_index=state.poll_question_index),
            )
            left = CAPTCHA_MAX_ATTEMPTS - attempts
            await send_ephemeral_message(bot, delivery_chat_id, f"Ответ неверный. Осталось попыток: {left}. Попробуйте снова.")
            await start_deep_captcha(bot, chat_id, user_id, delivery_chat_id=delivery_chat_id)
            return None

        await update_chat_member_state(session, chat_id, user_id, poll_reset_state(poll_attempts=attempts, poll_question_order=None, poll_question_index=0))
        left = CAPTCHA_MAX_ATTEMPTS - attempts
        await send_ephemeral_message(bot, chat_id, f"{answer.user.mention_html()}, ответ неверный.\nОсталось попыток: {left}. Для новой попытки отправьте любое сообщение в чат.", thread_id=thread_id)
    return None


async def on_chat_message(message: Message):
    text = await extract_message_text(message)
    if not text:
        return None
    user = message.from_user
    if not user:
        return None

    chat_id = message.chat.id
    is_admin, trusted_user, passed_poll = await CHAT_ADMIN_FILTER(message, message.bot), False, True
    mute_for_disallowed_link, mute_until, disallowed_links = False, None, []

    async with get_session() as session:
        if not await is_chat_moderated(session, chat_id):
            return None

        state = await get_chat_member_state(session, chat_id, user.id)
        if state is None:
            await upsert_chat_member_state(session, build_chat_member_state_create(chat_id, user.id, full_name=user.full_name or "", username=user.username, passed_poll=is_admin, messages_sent=0))
            state = await get_chat_member_state(session, chat_id, user.id)

        if state is None:
            return None

        trusted_user, passed_poll = is_admin or bool(state.whitelist), (is_admin or bool(state.whitelist)) or bool(state.passed_poll)
        if passed_poll and not is_admin:
            detected_links = extract_allowed_targets_from_text(text) | extract_entity_links(message)
            if detected_links:
                allowed_links = await get_allowed_links(session, chat_id)
                disallowed_links = sorted(target for target in detected_links if target not in allowed_links)
                if disallowed_links:
                    mute_until = datetime.now(tz=MOSCOW_TZ) + timedelta(minutes=5)
                    await update_chat_member_state(session, chat_id, user.id, ChatMemberStateUpdate(muted_until=mute_until, times_muted=(state.times_muted or 0) + 1))
                    mute_for_disallowed_link = True

        if passed_poll and not mute_for_disallowed_link:
            await update_chat_member_state(session, chat_id, user.id, ChatMemberStateUpdate(full_name=user.full_name or "", username=user.username, messages_sent=(state.messages_sent or 0) + 1))

    if not passed_poll:
        await safe_delete_message(message.bot, message.chat.id, message.message_id)
        await start_captcha(message.bot, message.chat.id, user.id, message.message_thread_id)
        return None

    if mute_for_disallowed_link:
        await safe_delete_message(message.bot, message.chat.id, message.message_id)
        if mute_until is not None:
            await safe_restrict(message.bot, chat_id, user.id, NEW_USER, until_date=mute_until)
            asyncio.create_task(pass_user(chat_id, user.id, message.bot, 5 * 60))

        preview = ", ".join(disallowed_links[:5]) + (", ..." if len(disallowed_links) > 5 else "")
        await send_ephemeral_message(message.bot, chat_id, f"{user.mention_html()}, отправка ссылок запрещена, кроме разрешённых для этого чата.\nОбнаружено: <code>{preview}</code>\nВы ограничены на 5 минут.", thread_id=message.message_thread_id)
        return None

    proba_spam = await predict_spam_proba(text)
    await append_message_stats_to_csv(chat_id=chat_id, user_id=user.id, message_id=message.message_id, text=text, predicted_proba=proba_spam)
    return None
