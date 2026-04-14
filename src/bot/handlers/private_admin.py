from aiogram import Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message

from src.bot.services.admin_flow import (
    handle_chat_add,
    handle_chat_list,
    handle_chat_remove,
    handle_private,
    handle_set_greetings,
)
from src.bot.services.admin_tools import private_admin_filter

router = Router(name="private_admin")
router.message.filter(private_admin_filter)


@router.message(Command("chat_add"))
async def chat_add(message: Message): return await handle_chat_add(message)


@router.message(Command("chat_remove"))
async def chat_remove(message: Message): return await handle_chat_remove(message)


@router.message(Command("chat_list"))
async def chat_list(message: Message): return await handle_chat_list(message)


@router.message(Command("set_greetings"))
async def set_greetings(message: Message): return await handle_set_greetings(message)


@router.message(lambda message: message.chat.type == ChatType.PRIVATE)
async def private_chat(message: Message): return await handle_private(message)
