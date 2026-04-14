import asyncio
import csv
import io

from datetime import timedelta, datetime
from typing import Optional

from aiogram.fsm.context import FSMContext
from aiogram.types import Message, BufferedInputFile

from config import MOSCOW_TZ
from src.bot.services.admin_tools import ensure_chat_state, require_moderated_chat_context
from src.bot.services.telegram_tools import answer_ephemeral, pass_user, safe_restrict, safe_unrestrict
from src.bot.permissions import NEW_USER
from src.image import extract_text_from_image
from src.test_classifier import predict_spam_proba, probability_to_label
from src.helpers import _notify_user
from src.database import get_session
from src.database.crud import (
    add_allowed_link,
    add_moderated_chat,
    create_poll_question,
    delete_poll_question,
    get_allowed_links,
    get_moderated_chat,
    list_chat_poll_questions,
    list_default_poll_questions,
    list_moderated_chat_ids,
    remove_allowed_link,
    remove_moderated_chat,
    set_greetings_message,
    update_chat_member_state,
)
from src.database.schemas import ChatMemberStateUpdate
from src.database.utils import normalize_allowed_link
from src.bot.states.group_admin import GroupAdminStates

POLL_ADD_CSV_HEADER = "question,right,wrong1,wrong2,wrong3,\n"
POLL_ADD_CSV_SAMPLE = "Какого цвета небо днём?,Голубое,Зелёное,Красное,Чёрное,\n"


def _message_plain_text(message: Message) -> str:
    return message.text if message.text is not None else message.caption or ""


def _message_html_text(message: Message) -> str:
    if message.text is not None: return message.html_text or message.text
    return message.caption_html if message.caption is not None else message.caption or ""


def _html_payload_after_args(message: Message, command: str, skip_args: int = 0) -> str:
    plain = _message_plain_text(message).strip()
    html = _message_html_text(message).strip()
    if not plain.startswith(command): return ""

    index = len(command)
    for _ in range(skip_args):
        while index < len(plain) and plain[index].isspace(): index += 1
        while index < len(plain) and not plain[index].isspace(): index += 1
    while index < len(plain) and plain[index].isspace(): index += 1
    return html[index:].strip()


def _parse_poll_csv_rows(content: str) -> tuple[list[tuple[int, str, str, list[str]]], list[str]]:
    reader = csv.DictReader(io.StringIO(content))
    fieldnames = {f.strip() for f in (reader.fieldnames or []) if f and f.strip()}
    required = {"question", "right", "wrong1", "wrong2", "wrong3"}
    if not required.issubset(fieldnames):
        return [], [f"Неверный заголовок CSV. Нужен: <code>{POLL_ADD_CSV_HEADER.strip()}</code>"]

    rows: list[tuple[int, str, str, list[str]]] = []
    errors: list[str] = []
    for line_no, row in enumerate(reader, start=2):
        question = (row.get("question") or "").strip()
        right = (row.get("right") or "").strip()
        wrong1 = (row.get("wrong1") or "").strip()
        wrong2 = (row.get("wrong2") or "").strip()
        wrong3 = (row.get("wrong3") or "").strip()
        if not any([question, right, wrong1, wrong2, wrong3]): continue
        if not all([question, right, wrong1, wrong2, wrong3]):
            errors.append(f"Строка {line_no}: заполните все 5 колонок.")
            continue
        rows.append((line_no, question, right, [wrong1, wrong2, wrong3]))

    return rows, errors


async def _download_csv_text(message: Message) -> str | None:
    if not message.document: return None
    file = await message.bot.get_file(message.document.file_id)
    stream = await message.bot.download_file(file.file_path)
    if hasattr(stream, "seek"): stream.seek(0)
    raw = stream.read() if hasattr(stream, "read") else bytes(stream)
    try: return raw.decode("utf-8-sig")
    except Exception: return None




async def handle_chat_add(message: Message):
    raw = (message.text or "").strip().removeprefix("/chat_add").strip()
    try: chat_id = int(raw)
    except Exception: return await answer_ephemeral(message, "Использование: <code>/chat_add -1001234567890</code>")
    async with get_session() as session: added = await add_moderated_chat(session, chat_id)
    if added: return await answer_ephemeral(message, f"Чат <code>{chat_id}</code> добавлен в модерируемые.")
    return await answer_ephemeral(message, f"Чат <code>{chat_id}</code> уже в списке.")


async def handle_chat_remove(message: Message):
    raw = (message.text or "").strip().removeprefix("/chat_remove").strip()
    try: chat_id = int(raw)
    except Exception: return await answer_ephemeral(message, "Использование: <code>/chat_remove -1001234567890</code>")
    async with get_session() as session: removed = await remove_moderated_chat(session, chat_id)
    if removed: return await answer_ephemeral(message, f"Чат <code>{chat_id}</code> удалён из модерируемых.")
    return await answer_ephemeral(message, f"Чат <code>{chat_id}</code> не найден в списке.")


async def handle_chat_list(message: Message):
    async with get_session() as session: chat_ids = await list_moderated_chat_ids(session)
    if not chat_ids: return await answer_ephemeral(message, "Список модерируемых чатов пуст.")
    lines = "\n".join(f"- <code>{chat_id}</code>" for chat_id in chat_ids)
    return await answer_ephemeral(message, f"<b>Модерируемые чаты:</b>\n{lines}")


async def handle_set_greeting(message: Message):
    chat_id = await require_moderated_chat_context(message)
    if chat_id is None: return None
    payload = _html_payload_after_args(message, "/set_greeting")
    async with get_session() as session:
        if not payload:
            chat = await get_moderated_chat(session, chat_id)
            current = (chat.greetings_message or "").strip() if chat else ""
            if not current: return await answer_ephemeral(message, "Приветствие не задано.\nУстановить: <code>/set_greeting Добро пожаловать! Пройдите проверку.</code>")
            return await answer_ephemeral(message,f"<b>Текущее приветствие:</b>\n{current}")

        if payload.lower() in {"none", "null", "off", "clear", "reset", "-"}:
            await set_greetings_message(session, chat_id, None)
            return await answer_ephemeral(message, "Приветствие очищено.")

        await set_greetings_message(session, chat_id, payload)
        return await answer_ephemeral(message, "Приветствие сохранено.")


async def handle_set_greetings(message: Message):
    plain = _message_plain_text(message).strip()
    parts = plain.split(maxsplit=2)
    if len(parts) < 2: return await answer_ephemeral(message, "Использование: <code>/set_greetings -1001234567890 Приветствие с HTML</code>")

    try: chat_id = int(parts[1])
    except Exception: return await answer_ephemeral(message, "Первый аргумент должен быть <code>chat_id</code>.")

    payload = _html_payload_after_args(message, "/set_greetings", skip_args=1)
    async with get_session() as session:
        chat = await get_moderated_chat(session, chat_id)
        if chat is None: return await answer_ephemeral(message, f"Чат <code>{chat_id}</code> не найден в списке модерируемых.")
        if not payload:
            current = (chat.greetings_message or "").strip()
            if not current: return await answer_ephemeral(message, "Приветствие не задано.")
            return await answer_ephemeral(message, f"<b>Текущее приветствие для {chat_id}:</b>\n{current}")
        if payload.lower() in {"none", "null", "off", "clear", "reset", "-"}:
            await set_greetings_message(session, chat_id, None)
            return await answer_ephemeral(message, f"Приветствие для <code>{chat_id}</code> очищено.")
        await set_greetings_message(session, chat_id, payload)
        return await answer_ephemeral(message, f"Приветствие для <code>{chat_id}</code> сохранено.")


async def handle_poll_add(message: Message, state: FSMContext):
    chat_id = await require_moderated_chat_context(message)
    if chat_id is None: return None

    payload = _message_plain_text(message).strip().removeprefix("/poll_add").strip()
    if payload: return await answer_ephemeral(message, "Старый inline-формат удалён. Используйте CSV-шаблон: отправьте <code>/poll_add</code>, затем загрузите CSV следующим сообщением.")
    await state.set_state(GroupAdminStates.waiting_for_poll_csv)
    await state.update_data(chat_id=chat_id)
    file = BufferedInputFile((POLL_ADD_CSV_HEADER + POLL_ADD_CSV_SAMPLE).encode("utf-8"), filename=f"poll_template_{chat_id}.csv")
    return await message.answer_document(file, caption="1) Заполните CSV вопросами.\n2) Отправьте CSV следующим сообщением в этот чат.")


async def handle_poll_add_import(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data.get("chat_id") or message.chat.id
    if not message.document: return await answer_ephemeral(message, "Сейчас ожидается CSV-файл с вопросами. Отправьте документ или отмените состояние новой командой <code>/poll_add</code>.")

    csv_text = await _download_csv_text(message)
    if csv_text is None: return await answer_ephemeral(message, "Не удалось прочитать CSV. Используйте UTF-8 и отправьте файл повторно.")

    rows, errors = _parse_poll_csv_rows(csv_text)
    added = 0
    async with get_session() as session:
        for line_no, question, right, wrongs in rows:
            try:
                await create_poll_question(session, question=question, correct_answer=right, wrong_answers=wrongs, chat_id=chat_id)
                added += 1
            except ValueError as e:
                errors.append(f"Строка {line_no}: {e}")

    await state.clear()
    if not added and errors: return await answer_ephemeral(message, "Ничего не добавлено.\n" + "\n".join(errors[:12]))
    if errors: return await answer_ephemeral(message, f"Добавлено вопросов: <b>{added}</b>.\nОшибки: <b>{len(errors)}</b>\n" + "\n".join(errors[:10]))
    return await answer_ephemeral(message, f"Готово, добавлено вопросов: <b>{added}</b>.")


async def handle_poll_add_waiting(message: Message):
    return await answer_ephemeral(message, "Сейчас ожидается CSV-файл с вопросами. Отправьте документ следующим сообщением.")


async def handle_poll_delete(message: Message):
    chat_id = await require_moderated_chat_context(message)
    if chat_id is None: return None

    raw = (message.text or "").strip().removeprefix("/poll_delete").strip()
    if not raw.isdigit(): return await answer_ephemeral(message, "Использование: <code>/poll_delete [question_id]</code>")

    question_id = int(raw)
    async with get_session() as session: deleted = await delete_poll_question(session, question_id=question_id, chat_id=chat_id)

    if deleted: return await answer_ephemeral(message, f"Вопрос <code>{question_id}</code> удалён.")
    return await answer_ephemeral(message, "Вопрос не найден среди вопросов этого чата.")


async def handle_poll_list(message: Message):
    chat_id = await require_moderated_chat_context(message)
    if chat_id is None: return None

    async with get_session() as session:
        custom_questions = await list_chat_poll_questions(session, chat_id)
        using_defaults = not custom_questions
        questions = custom_questions if custom_questions else await list_default_poll_questions(session)

    if not questions: return await answer_ephemeral(message, "Вопросов в базе пока нет.")

    heading = "Кастомные вопросы этого чата:" if not using_defaults else "У этого чата нет своих вопросов, используются дефолтные:"
    lines = [heading]
    for q in questions:
        text = q.question.replace("\n", " ").strip()
        if len(text) > 120: text = text[:117] + "..."
        lines.append(f"{q.id}. {text}")

    body = "\n".join(lines)
    file = BufferedInputFile(body.encode("utf-8"), filename=f"poll_questions_{chat_id}.txt")
    return await message.answer_document(file, caption=f"Всего вопросов: {len(questions)}")


async def handle_allow_link(message: Message):
    chat_id = await require_moderated_chat_context(message)
    if chat_id is None: return None

    parts = (message.text or "").strip().split(maxsplit=1)
    raw_link = parts[1].strip() if len(parts) > 1 else ""
    if not raw_link:
        return await answer_ephemeral(message,
            "<b>Ошибка команды:</b> указывайте ссылку, которую нужно разрешить.\n\n"
            "<b>Пример:</b> <code>/allow_link https://example.com/path</code>",
        )

    allowed_value = normalize_allowed_link(raw_link)
    if not allowed_value: return await answer_ephemeral(message, "<b>Ошибка команды:</b> не удалось распознать ссылку или домен.")

    async with get_session() as session: added = await add_allowed_link(session, chat_id, allowed_value)
    label = "Ссылка" if allowed_value.startswith("t.me/") else "Домен"
    if added: return await answer_ephemeral(message, f"{label} <code>{allowed_value}</code> добавлен в allow-лист этого чата.")
    return await answer_ephemeral(message, f"{label} <code>{allowed_value}</code> уже есть в allow-листе этого чата.")


async def handle_unallow_link(message: Message):
    chat_id = await require_moderated_chat_context(message)
    if chat_id is None: return None

    parts = (message.text or "").strip().split(maxsplit=1)
    raw_link = parts[1].strip() if len(parts) > 1 else ""
    if not raw_link:
        return await answer_ephemeral(message,
            "<b>Ошибка команды:</b> указывайте ссылку, которую нужно убрать из allow-листа.\n\n"
            "<b>Пример:</b> <code>/unallow_link example.com</code>",
        )

    allowed_value = normalize_allowed_link(raw_link)
    if not allowed_value: return await answer_ephemeral(message, "<b>Ошибка команды:</b> не удалось распознать ссылку или домен.")

    async with get_session() as session: removed = await remove_allowed_link(session, chat_id, allowed_value)
    label = "Ссылка" if allowed_value.startswith("t.me/") else "Домен"
    if removed: return await answer_ephemeral(message, f"{label} <code>{allowed_value}</code> удалён из allow-листа этого чата.")
    return await answer_ephemeral(message, f"{label} <code>{allowed_value}</code> не найден в allow-листе этого чата.")


async def handle_allowed_links(message: Message):
    chat_id = await require_moderated_chat_context(message)
    if chat_id is None: return None

    async with get_session() as session: links = await get_allowed_links(session, chat_id)
    lines = sorted(links)
    body = "\n".join(lines) if lines else "Allow-лист этого чата пуст. Любые ссылки будут запрещены."
    file = BufferedInputFile(body.encode("utf-8"), filename=f"allowed_links_{chat_id}.txt")
    return await message.answer_document(file, caption=f"Разрешённых ссылок/доменов: {len(lines)}")


async def handle_spam(message: Message):
    chat_id = await require_moderated_chat_context(message)
    if chat_id is None: return None
    if not message.reply_to_message: return await answer_ephemeral(message, "<b>Ошибка команды: </b>отвечайте командой на нужное сообщение")
    if not message.reply_to_message.text or message.reply_to_message.photo: return await answer_ephemeral(message, "Сообщение без текста, пометить как спам нельзя.")

    target = message.reply_to_message.from_user
    if target is None: return await answer_ephemeral(message, "Не удалось определить пользователя сообщения.")
    spam_text = message.reply_to_message.text.strip()

    async with get_session() as session:
        state = await ensure_chat_state(session, chat_id, target.id, full_name=target.full_name or "", username=target.username)
        if state is not None:
            await update_chat_member_state(session, chat_id, target.id, ChatMemberStateUpdate(
                times_reported=(state.times_reported or 0) + 1,
                accused_spam=True,
                last_accused_text=spam_text,
            ))

    await safe_restrict(message.bot, chat_id, target.id, NEW_USER)
    asyncio.create_task(_notify_user(message, f"Сообщение маркировано как <b>спам</b>, пользователь {target.mention_html()} <b>ограничен</b>\n"
        f"Для возвращения прав используйте команду <code>/unmute {target.id}</code>",
        300,
    ))

    try: await message.reply_to_message.delete()
    except Exception: pass
    return None


async def handle_mute(message: Message):
    chat_id = await require_moderated_chat_context(message)
    if chat_id is None: return None
    if not message.reply_to_message: return await answer_ephemeral(message, "<b>Ошибка команды: </b>отвечайте командой на нужное сообщение")

    target = message.reply_to_message.from_user
    if target is None: return await answer_ephemeral(message, "Не удалось определить пользователя сообщения.")
    minutes_str = (message.text or "").strip().removeprefix("/mute").strip()

    timer = float(minutes_str) * 60 if minutes_str.isdigit() else None
    if timer:
        mute_until = datetime.now(tz=MOSCOW_TZ) + timedelta(seconds=timer)
        async with get_session() as session:
            state = await ensure_chat_state(session, chat_id, target.id, full_name=target.full_name or "", username=target.username)
            if state is not None:
                await update_chat_member_state(session, chat_id, target.id, ChatMemberStateUpdate(
                    muted_until=mute_until,
                    times_muted=(state.times_muted or 0) + 1,
                ))

        asyncio.create_task(pass_user(chat_id, target.id, message.bot, timer))
        await safe_restrict(message.bot, chat_id, target.id, NEW_USER, until_date=mute_until)
    else: await safe_restrict(message.bot, chat_id, target.id, NEW_USER)

    label = "" if not timer else f" на {minutes_str} минут"
    return asyncio.create_task(_notify_user(message, f"Пользователь {target.mention_html()} успешно <b>ограничен в правах{label}</b>\n"
        f"Для возвращения прав используйте команду <code>/unmute {target.id}</code>",
        300
    ))


async def handle_whitelist(message: Message):
    chat_id = await require_moderated_chat_context(message)
    if chat_id is None: return None

    text = message.text or ""
    args = text.strip().removeprefix("/whitelist").strip().split()
    if not args:
        return await answer_ephemeral(message,
            "<b>Использование:</b>\n<code>/whitelist add [user_id]</code> — добавить в белый список\n"
            "<code>/whitelist remove user_id</code> — убрать из белого списка\n\n"
            "Можно указать <code>user_id</code> или ответить командой на сообщение пользователя.",
        )

    action = args[0].lower()
    if action in ("add", "on", "+"): value = True
    elif action in ("remove", "rm", "off", "del", "-"): value = False
    else: return await answer_ephemeral(message, "<b>Ошибка команды:</b> неизвестное действие.\nИспользуйте <code>add</code> или <code>remove</code>.")

    user_id: Optional[int] = None
    full_name = ""
    username: Optional[str] = None
    if len(args) >= 2:
        try: user_id = int(args[1])
        except ValueError: user_id = None

    elif message.reply_to_message and message.reply_to_message.from_user:
        user_id = message.reply_to_message.from_user.id
        full_name = message.reply_to_message.from_user.full_name or ""
        username = message.reply_to_message.from_user.username

    if not user_id:
        return await answer_ephemeral(message,
            "Укажите <code>user_id</code> или ответьте командой на сообщение пользователя.\n\n"
            "<b>Пример:</b> <code>/whitelist add 123456789</code>",
        )

    async with get_session() as session:
        await ensure_chat_state(session, chat_id, user_id, full_name=full_name, username=username)
        user = await update_chat_member_state(session, chat_id, user_id, ChatMemberStateUpdate(whitelist=value))

    if not user: return await answer_ephemeral(message, "Не удалось обновить белый список для этого пользователя.")

    status = "добавлен в <b>белый список</b>" if value else "убран из <b>белого списка</b>"
    return await answer_ephemeral(message, f"Пользователь с <code>user_id={user_id}</code> {status}.")


async def handle_unmute(message: Message):
    chat_id = await require_moderated_chat_context(message)
    if chat_id is None: return None

    text = message.text or ""
    user_id_str = text.strip().removeprefix("/unmute").strip()

    user_id = int(user_id_str) if user_id_str.isdigit() else None
    if not user_id and message.reply_to_message and message.reply_to_message.from_user: user_id = message.reply_to_message.from_user.id
    if not user_id: return await answer_ephemeral(message,"Либо укажите user_id пользователя, либо ответьте командой на его сообщение\n\n<i>Напишите @ShostakovIV в ТГ, если не знаете как получить user_id</i>")

    ok = await safe_unrestrict(message.bot, chat_id, user_id)
    async with get_session() as session:
        await ensure_chat_state(session, chat_id, user_id)
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
    return await answer_ephemeral(message, "Пользователю успешно возвращены права" if ok else "Не удалось вернуть права: пользователь не найден или уже покинул чат")


async def handle_get_id(message: Message):
    return await answer_ephemeral(message, f"{message.message_thread_id}")


async def handle_private(message: Message):
    text = ""
    if message.text and message.text.strip(): text += "\n" + message.text.strip()
    if message.caption and message.caption.strip(): text += "\n" + message.caption.strip()
    if message.photo:
        largest_photo = message.photo[-1]
        file = await message.bot.get_file(largest_photo.file_id)
        image_bytes = await message.bot.download_file(file.file_path)
        ocr_text = await asyncio.to_thread(extract_text_from_image, image_bytes)
        print(ocr_text)
        if ocr_text and ocr_text.strip(): text += "\n" + ocr_text.strip()

    if not text: return await message.answer("Нужен текст")

    prob = await predict_spam_proba(text.strip())
    is_spam_flag = bool(probability_to_label(prob))
    percent = f"{prob * 100:.2f}%"
    verdict = "Спам" if is_spam_flag else "Не спам"
    return await message.reply(f"{verdict}: {percent}")
