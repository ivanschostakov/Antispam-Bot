from aiogram import Router
from aiogram.enums import ChatType
from aiogram.filters import CommandStart
from aiogram.types import Message

from src.bot.services.user_flow import on_private_start

router = Router(name="private_user")
router.message.filter(lambda message: message.chat.type == ChatType.PRIVATE)


@router.message(CommandStart())
async def handle_private_start(message: Message):
    return await on_private_start(message)
