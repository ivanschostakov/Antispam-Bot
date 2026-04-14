import asyncio

from datetime import datetime
from aiogram import Dispatcher, Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import ANTISPAM_BOT_TOKEN, MOSCOW_TZ
from src.bot.services.telegram_tools import pass_user
from src.bot.handlers import *
from src.database import get_session, init_db
from src.database.crud import get_states_with_active_mute
from config import MESSAGES_LOGS_DIR

bot = Bot(ANTISPAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
dp.include_routers(private_admin_router, group_admin_router, group_user_router)

async def restore_mutes():
    now = datetime.now(tz=MOSCOW_TZ)
    async with get_session() as session: states = await get_states_with_active_mute(session, now)
    for state in states:
        timer = (state.muted_until - now).total_seconds()
        if timer < 0: timer = 0
        asyncio.create_task(pass_user(state.chat_id, state.user_id, bot, timer))

async def run_bot():
    MESSAGES_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    await init_db()
    await bot.delete_webhook(False)
    await restore_mutes()
    await dp.start_polling(bot)
