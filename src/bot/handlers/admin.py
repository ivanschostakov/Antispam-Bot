import asyncio

from datetime import timedelta, datetime
from typing import Optional

from aiogram import Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile

from config import MOSCOW_TZ, ELIXIR_CHAT_ID
from src.bot.handlers.chat_helpers import build_chat_member_state_create
from src.bot.handlers.chat_shared import answer_ephemeral, safe_unrestrict, safe_restrict, pass_user
from src.bot.permissions import NEW_USER
from src.image import extract_text_from_image
from src.test_classifier import predict_spam_proba, probability_to_label
from src.helpers import _notify_user
from src.database import get_session
from src.database.chat_member_state import (
    ChatMemberStateUpdate,
    get_chat_member_state,
    update_chat_member_state,
    upsert_chat_member_state,
)
from src.database.blocked_links import add_blocked_link, remove_blocked_link, get_blocked_links, normalize_blocked_link
from src.database.moderated_chat import (
    add_moderated_chat,
    is_chat_moderated,
    list_moderated_chat_ids,
    remove_moderated_chat,
)
from src.database.poll import (
    create_poll_question,
    delete_poll_question,
    list_chat_poll_questions,
    list_default_poll_questions,
)

router = Router(name="admin")


async def _is_admin_or_creator(bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


async def ADMIN_OR_PRIVATE_ADMIN_FILTER(message: Message, bot) -> bool:
    if message.chat.type != ChatType.PRIVATE:
        is_chat_add_command = (message.text or "").strip().startswith("/chat_add")
        async with get_session() as session:
            if not await is_chat_moderated(session, message.chat.id) and not is_chat_add_command:
                return False

        if message.sender_chat and message.sender_chat.id == message.chat.id:
            return True
        if not message.from_user:
            return False
        return await _is_admin_or_creator(bot, message.chat.id, message.from_user.id)

    if not message.from_user:
        return False

    async with get_session() as session:
        chat_ids = await list_moderated_chat_ids(session)
    if not chat_ids and ELIXIR_CHAT_ID is not None:
        chat_ids = [ELIXIR_CHAT_ID]

    for chat_id in chat_ids:
        if await _is_admin_or_creator(bot, chat_id, message.from_user.id):
            return True
    return False


router.message.filter(ADMIN_OR_PRIVATE_ADMIN_FILTER)


async def _require_moderated_chat_context(message: Message) -> int | None:
    if message.chat.type == ChatType.PRIVATE:
        await answer_ephemeral(message, "Эту команду нужно запускать внутри модерируемого чата.")
        return None

    async with get_session() as session:
        if await is_chat_moderated(session, message.chat.id):
            return message.chat.id

    await answer_ephemeral(message, "Этот чат не находится в списке модерируемых.")
    return None


async def _ensure_chat_state(
    session,
    chat_id: int,
    user_id: int,
    full_name: str = "",
    username: Optional[str] = None,
):
    state = await get_chat_member_state(session, chat_id, user_id)
    if state is not None:
        return state

    await upsert_chat_member_state(
        session,
        build_chat_member_state_create(
            chat_id,
            user_id,
            full_name=full_name,
            username=username,
            passed_poll=True,
            messages_sent=0,
        ),
    )
    return await get_chat_member_state(session, chat_id, user_id)


@router.message(Command("chat_add"))
async def handle_chat_add(message: Message):
    raw = (message.text or "").strip().removeprefix("/chat_add").strip()
    try:
        chat_id = int(raw)
    except Exception:
        return await answer_ephemeral(message, "Использование: <code>/chat_add -1001234567890</code>")

    async with get_session() as session:
        added = await add_moderated_chat(session, chat_id)

    if added:
        return await answer_ephemeral(message, f"Чат <code>{chat_id}</code> добавлен в модерируемые.")
    return await answer_ephemeral(message, f"Чат <code>{chat_id}</code> уже в списке.")


@router.message(Command("chat_remove"))
async def handle_chat_remove(message: Message):
    raw = (message.text or "").strip().removeprefix("/chat_remove").strip()
    try:
        chat_id = int(raw)
    except Exception:
        return await answer_ephemeral(message, "Использование: <code>/chat_remove -1001234567890</code>")

    async with get_session() as session:
        removed = await remove_moderated_chat(session, chat_id)

    if removed:
        return await answer_ephemeral(message, f"Чат <code>{chat_id}</code> удалён из модерируемых.")
    return await answer_ephemeral(message, f"Чат <code>{chat_id}</code> не найден в списке.")


@router.message(Command("chat_list"))
async def handle_chat_list(message: Message):
    async with get_session() as session:
        chat_ids = await list_moderated_chat_ids(session)

    if not chat_ids:
        return await answer_ephemeral(message, "Список модерируемых чатов пуст.")

    lines = "\n".join(f"- <code>{chat_id}</code>" for chat_id in chat_ids)
    return await answer_ephemeral(message, f"<b>Модерируемые чаты:</b>\n{lines}")


@router.message(Command("poll_add"))
async def handle_poll_add(message: Message):
    chat_id = await _require_moderated_chat_context(message)
    if chat_id is None:
        return None

    payload = (message.text or "").strip().removeprefix("/poll_add").strip()
    if not payload:
        return await answer_ephemeral(
            message,
            "Использование:\n<code>/poll_add Вопрос | Правильный | Неправильный1 | Неправильный2 | Неправильный3</code>",
        )

    parts = [part.strip() for part in payload.split("|")]
    if len(parts) < 5:
        return await answer_ephemeral(
            message,
            "Нужно минимум 5 частей через <code>|</code>: вопрос, правильный и минимум 3 неверных ответа.",
        )

    question = parts[0]
    correct = parts[1]
    wrong_answers = parts[2:]

    async with get_session() as session:
        try:
            created = await create_poll_question(
                session,
                question=question,
                correct_answer=correct,
                wrong_answers=wrong_answers,
                chat_id=chat_id,
            )
        except ValueError as e:
            return await answer_ephemeral(message, f"Ошибка вопроса: {e}")

    return await answer_ephemeral(
        message,
        f"Вопрос добавлен для этого чата. <code>question_id={created.id}</code>",
    )


@router.message(Command("poll_delete"))
async def handle_poll_delete(message: Message):
    chat_id = await _require_moderated_chat_context(message)
    if chat_id is None:
        return None

    raw = (message.text or "").strip().removeprefix("/poll_delete").strip()
    if not raw.isdigit():
        return await answer_ephemeral(message, "Использование: <code>/poll_delete [question_id]</code>")

    question_id = int(raw)
    async with get_session() as session:
        deleted = await delete_poll_question(session, question_id=question_id, chat_id=chat_id)

    if deleted:
        return await answer_ephemeral(message, f"Вопрос <code>{question_id}</code> удалён.")
    return await answer_ephemeral(message, "Вопрос не найден среди вопросов этого чата.")


@router.message(Command("poll_list"))
async def handle_poll_list(message: Message):
    chat_id = await _require_moderated_chat_context(message)
    if chat_id is None:
        return None

    async with get_session() as session:
        custom_questions = await list_chat_poll_questions(session, chat_id)
        using_defaults = not custom_questions
        questions = custom_questions if custom_questions else await list_default_poll_questions(session)

    if not questions:
        return await answer_ephemeral(message, "Вопросов в базе пока нет.")

    heading = (
        "Кастомные вопросы этого чата:"
        if not using_defaults
        else "У этого чата нет своих вопросов, используются дефолтные:"
    )
    lines = [heading]
    for q in questions:
        text = q.question.replace("\n", " ").strip()
        if len(text) > 120:
            text = text[:117] + "..."
        lines.append(f"{q.id}. {text}")

    body = "\n".join(lines)
    file = BufferedInputFile(body.encode("utf-8"), filename=f"poll_questions_{chat_id}.txt")
    return await message.answer_document(file, caption=f"Всего вопросов: {len(questions)}")


@router.message(Command("block_link"))
async def handle_block_link(message: Message):
    parts = (message.text or "").strip().split(maxsplit=1)
    raw_link = parts[1].strip() if len(parts) > 1 else ""
    if not raw_link:
        return await answer_ephemeral(
            message,
            "<b>Ошибка команды:</b> указывайте ссылку, которую нужно заблокировать.\n\n"
            "<b>Пример:</b> <code>/block_link https://spam.example.com/promo</code>",
        )

    blocked_value = normalize_blocked_link(raw_link)
    if not blocked_value:
        return await answer_ephemeral(message, "<b>Ошибка команды:</b> не удалось распознать ссылку или домен.")

    async with get_session() as session:
        added = await add_blocked_link(session, blocked_value)
    label = "Ссылка" if blocked_value.startswith("t.me/") else "Домен"
    if added:
        return await answer_ephemeral(message, f"{label} <code>{blocked_value}</code> добавлен в блок-лист.")
    return await answer_ephemeral(message, f"{label} <code>{blocked_value}</code> уже находится в блок-листе.")


@router.message(Command("unblock_link"))
async def handle_unblock_link(message: Message):
    parts = (message.text or "").strip().split(maxsplit=1)
    raw_link = parts[1].strip() if len(parts) > 1 else ""
    if not raw_link:
        return await answer_ephemeral(
            message,
            "<b>Ошибка команды:</b> указывайте ссылку, которую нужно разблокировать.\n\n"
            "<b>Пример:</b> <code>/unblock_link https://spam.example.com/promo</code>",
        )

    blocked_value = normalize_blocked_link(raw_link)
    if not blocked_value:
        return await answer_ephemeral(message, "<b>Ошибка команды:</b> не удалось распознать ссылку или домен.")

    async with get_session() as session:
        removed = await remove_blocked_link(session, blocked_value)
    label = "Ссылка" if blocked_value.startswith("t.me/") else "Домен"
    if removed:
        return await answer_ephemeral(message, f"{label} <code>{blocked_value}</code> удален из блок-листа.")
    return await answer_ephemeral(message, f"{label} <code>{blocked_value}</code> не найден в блок-листе.")


@router.message(Command("links"))
async def handle_links(message: Message):
    async with get_session() as session:
        links = await get_blocked_links(session)
    lines = sorted(links)
    body = "\n".join(lines) if lines else "Список заблокированных ссылок пуст."
    file = BufferedInputFile(body.encode("utf-8"), filename="blocked_links.txt")
    return await message.answer_document(file, caption=f"Заблокированных ссылок/доменов: {len(lines)}")


@router.message(Command("spam"))
async def handle_spam(message: Message):
    chat_id = await _require_moderated_chat_context(message)
    if chat_id is None:
        return None
    if not message.reply_to_message:
        return await answer_ephemeral(message, "<b>Ошибка команды: </b>отвечайте командой на нужное сообщение")
    if not message.reply_to_message.text or message.reply_to_message.photo:
        return await answer_ephemeral(message, "Сообщение без текста, пометить как спам нельзя.")

    target = message.reply_to_message.from_user
    if target is None:
        return await answer_ephemeral(message, "Не удалось определить пользователя сообщения.")
    spam_text = message.reply_to_message.text.strip()

    async with get_session() as session:
        state = await _ensure_chat_state(
            session,
            chat_id,
            target.id,
            full_name=target.full_name or "",
            username=target.username,
        )
        if state is not None:
            await update_chat_member_state(
                session,
                chat_id,
                target.id,
                ChatMemberStateUpdate(
                    times_reported=(state.times_reported or 0) + 1,
                    accused_spam=True,
                    last_accused_text=spam_text,
                ),
            )

    await safe_restrict(message.bot, chat_id, target.id, NEW_USER)
    asyncio.create_task(
        _notify_user(
            message,
            f"Сообщение маркировано как <b>спам</b>, пользователь {target.mention_html()} <b>ограничен</b>\n"
            f"Для возвращения прав используйте команду <code>/unmute {target.id}</code>",
            300,
        )
    )

    try:
        await message.reply_to_message.delete()
    except Exception:
        pass
    return None


@router.message(Command("mute"))
async def handle_mute(message: Message):
    chat_id = await _require_moderated_chat_context(message)
    if chat_id is None:
        return None
    if not message.reply_to_message:
        return await answer_ephemeral(message, "<b>Ошибка команды: </b>отвечайте командой на нужное сообщение")

    target = message.reply_to_message.from_user
    if target is None:
        return await answer_ephemeral(message, "Не удалось определить пользователя сообщения.")
    minutes_str = (message.text or "").strip().removeprefix("/mute").strip()

    timer = float(minutes_str) * 60 if minutes_str.isdigit() else None
    if timer:
        mute_until = datetime.now(tz=MOSCOW_TZ) + timedelta(seconds=timer)
        async with get_session() as session:
            state = await _ensure_chat_state(
                session,
                chat_id,
                target.id,
                full_name=target.full_name or "",
                username=target.username,
            )
            if state is not None:
                await update_chat_member_state(
                    session,
                    chat_id,
                    target.id,
                    ChatMemberStateUpdate(
                        muted_until=mute_until,
                        times_muted=(state.times_muted or 0) + 1,
                    ),
                )

        asyncio.create_task(pass_user(chat_id, target.id, message.bot, timer))
        await safe_restrict(message.bot, chat_id, target.id, NEW_USER, until_date=mute_until)
    else:
        await safe_restrict(message.bot, chat_id, target.id, NEW_USER)

    label = "" if not timer else f" на {minutes_str} минут"
    return asyncio.create_task(
        _notify_user(
            message,
            f"Пользователь {target.mention_html()} успешно <b>ограничен в правах{label}</b>\n"
            f"Для возвращения прав используйте команду <code>/unmute {target.id}</code>",
            300,
        )
    )


@router.message(Command("whitelist"))
async def handle_whitelist(message: Message):
    chat_id = await _require_moderated_chat_context(message)
    if chat_id is None:
        return None

    text = message.text or ""
    args = text.strip().removeprefix("/whitelist").strip().split()
    if not args:
        return await answer_ephemeral(
            message,
            "<b>Использование:</b>\n<code>/whitelist add [user_id]</code> — добавить в белый список\n"
            "<code>/whitelist remove user_id</code> — убрать из белого списка\n\n"
            "Можно указать <code>user_id</code> или ответить командой на сообщение пользователя.",
        )

    action = args[0].lower()
    if action in ("add", "on", "+"):
        value = True
    elif action in ("remove", "rm", "off", "del", "-"):
        value = False
    else:
        return await answer_ephemeral(
            message,
            "<b>Ошибка команды:</b> неизвестное действие.\nИспользуйте <code>add</code> или <code>remove</code>.",
        )

    user_id: Optional[int] = None
    full_name = ""
    username: Optional[str] = None
    if len(args) >= 2:
        try:
            user_id = int(args[1])
        except ValueError:
            user_id = None
    elif message.reply_to_message and message.reply_to_message.from_user:
        user_id = message.reply_to_message.from_user.id
        full_name = message.reply_to_message.from_user.full_name or ""
        username = message.reply_to_message.from_user.username

    if not user_id:
        return await answer_ephemeral(
            message,
            "Укажите <code>user_id</code> или ответьте командой на сообщение пользователя.\n\n"
            "<b>Пример:</b> <code>/whitelist add 123456789</code>",
        )

    async with get_session() as session:
        await _ensure_chat_state(session, chat_id, user_id, full_name=full_name, username=username)
        user = await update_chat_member_state(
            session,
            chat_id,
            user_id,
            ChatMemberStateUpdate(whitelist=value),
        )

    if not user:
        return await answer_ephemeral(message, "Не удалось обновить белый список для этого пользователя.")

    status = "добавлен в <b>белый список</b>" if value else "убран из <b>белого списка</b>"
    return await answer_ephemeral(message, f"Пользователь с <code>user_id={user_id}</code> {status}.")


@router.message(Command("unmute"))
async def handle_unmute(message: Message):
    chat_id = await _require_moderated_chat_context(message)
    if chat_id is None:
        return None

    text = message.text or ""
    user_id_str = text.strip().removeprefix("/unmute").strip()

    user_id = int(user_id_str) if user_id_str.isdigit() else None
    if not user_id and message.reply_to_message and message.reply_to_message.from_user:
        user_id = message.reply_to_message.from_user.id
    if not user_id:
        return await answer_ephemeral(
            message,
            "Либо укажите user_id пользователя, либо ответьте командой на его сообщение\n\n"
            "<i>Напишите @ShostakovIV в ТГ, если не знаете как получить user_id</i>",
        )

    ok = await safe_unrestrict(message.bot, chat_id, user_id)
    async with get_session() as session:
        await _ensure_chat_state(session, chat_id, user_id)
        await update_chat_member_state(
            session,
            chat_id,
            user_id,
            ChatMemberStateUpdate(
                muted_until=None,
                banned_until=None,
                passed_poll=True,
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
    return await answer_ephemeral(
        message,
        "Пользователю успешно возвращены права" if ok else "Не удалось вернуть права: пользователь не найден или уже покинул чат",
    )


@router.message(Command("get_thread"))
async def handle_get_id(message: Message):
    return await answer_ephemeral(message, f"{message.message_thread_id}")


@router.message(lambda message: message.chat.type == ChatType.PRIVATE)
async def handle_private(message: Message):
    text = ""
    if message.text and message.text.strip():
        text += "\n" + message.text.strip()
    if message.caption and message.caption.strip():
        text += "\n" + message.caption.strip()
    if message.photo:
        largest_photo = message.photo[-1]
        file = await message.bot.get_file(largest_photo.file_id)
        image_bytes = await message.bot.download_file(file.file_path)
        ocr_text = await asyncio.to_thread(extract_text_from_image, image_bytes)
        print(ocr_text)
        if ocr_text and ocr_text.strip():
            text += "\n" + ocr_text.strip()

    if not text:
        return await message.answer("Нужен текст")

    prob = await predict_spam_proba(text.strip())
    is_spam_flag = bool(probability_to_label(prob))
    percent = f"{prob * 100:.2f}%"
    verdict = "Спам" if is_spam_flag else "Не спам"
    return await message.reply(f"{verdict}: {percent}")
