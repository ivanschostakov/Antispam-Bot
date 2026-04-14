from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.moderated_chat.model import ModeratedChat


async def get_moderated_chat(db: AsyncSession, chat_id: int) -> ModeratedChat | None:
    result = await db.execute(
        select(ModeratedChat).where(ModeratedChat.id == chat_id)
    )
    return result.scalars().first()


async def is_chat_moderated(db: AsyncSession, chat_id: int) -> bool:
    return (await get_moderated_chat(db, chat_id)) is not None


async def add_moderated_chat(db: AsyncSession, chat_id: int) -> bool:
    if await is_chat_moderated(db, chat_id):
        return False

    db.add(ModeratedChat(id=chat_id))
    await db.commit()
    return True


async def remove_moderated_chat(db: AsyncSession, chat_id: int) -> bool:
    chat = await get_moderated_chat(db, chat_id)
    if chat is None:
        return False

    await db.delete(chat)
    await db.commit()
    return True


async def list_moderated_chat_ids(db: AsyncSession) -> list[int]:
    result = await db.execute(
        select(ModeratedChat.id).order_by(ModeratedChat.id)
    )
    return list(result.scalars().all())
