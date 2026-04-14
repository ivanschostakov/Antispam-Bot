from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.bot.services.admin_flow import (
    handle_allow_link,
    handle_allowed_links,
    handle_get_id,
    handle_mute,
    handle_poll_add,
    handle_poll_add_import,
    handle_poll_add_waiting,
    handle_poll_delete,
    handle_poll_list,
    handle_spam,
    handle_set_greeting,
    handle_unallow_link,
    handle_unmute,
    handle_whitelist,
)
from src.bot.services.admin_tools import group_admin_filter
from src.bot.states.group_admin import GroupAdminStates

router = Router(name="group_admin")
router.message.filter(group_admin_filter)


@router.message(Command("set_greeting"))
async def set_greeting(message: Message): return await handle_set_greeting(message)


@router.message(Command("poll_add"))
async def poll_add(message: Message, state: FSMContext): return await handle_poll_add(message, state)


@router.message(GroupAdminStates.waiting_for_poll_csv, F.document)
async def poll_add_csv(message: Message, state: FSMContext): return await handle_poll_add_import(message, state)


@router.message(GroupAdminStates.waiting_for_poll_csv)
async def poll_add_waiting(message: Message): return await handle_poll_add_waiting(message)


@router.message(Command("poll_delete"))
async def poll_delete(message: Message): return await handle_poll_delete(message)


@router.message(Command("poll_list"))
async def poll_list(message: Message): return await handle_poll_list(message)


@router.message(Command("allow_link"))
async def allow_link(message: Message): return await handle_allow_link(message)


@router.message(Command("unallow_link"))
async def unallow_link(message: Message): return await handle_unallow_link(message)


@router.message(Command("allowed_links"))
async def allowed_links(message: Message): return await handle_allowed_links(message)


@router.message(Command("spam"))
async def spam(message: Message): return await handle_spam(message)


@router.message(Command("mute"))
async def mute(message: Message): return await handle_mute(message)


@router.message(Command("whitelist"))
async def whitelist(message: Message): return await handle_whitelist(message)


@router.message(Command("unmute"))
async def unmute(message: Message): return await handle_unmute(message)


@router.message(Command("get_thread"))
async def get_thread(message: Message): return await handle_get_id(message)
