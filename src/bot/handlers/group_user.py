from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.filters import ChatMemberUpdatedFilter, Command, JOIN_TRANSITION
from aiogram.types import ChatMemberUpdated, Message, PollAnswer

from src.bot.services.chat_flow import on_bot_status_changed, on_chat_message, on_new_member, on_poll_answer
from src.bot.services.chat_tools import is_command_message
from src.bot.services.user_flow import on_report

router = Router(name="group_user")
router.message.filter(lambda message: message.chat.type != ChatType.PRIVATE)


@router.my_chat_member()
async def handle_my_chat_member(event: ChatMemberUpdated): return await on_bot_status_changed(event)


@router.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def handle_new_member(event: ChatMemberUpdated): return await on_new_member(event)


@router.poll_answer()
async def handle_poll_answer(answer: PollAnswer, bot: Bot): return await on_poll_answer(answer, bot)


@router.message(Command("report"))
async def handle_report(message: Message): return await on_report(message)


@router.message(lambda message: not is_command_message(message))
async def handle_chat_message(message: Message): return await on_chat_message(message)
