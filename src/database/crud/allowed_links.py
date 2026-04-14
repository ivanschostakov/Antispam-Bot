from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import AllowedLink


async def add_allowed_link(db: AsyncSession, chat_id: int, url: str) -> bool:
    normalized = url.strip().lower()
    result = await db.execute(
        select(AllowedLink).where(
            AllowedLink.chat_id == chat_id,
            AllowedLink.url == normalized,
        )
    )
    if result.scalars().first(): return False
    db.add(AllowedLink(chat_id=chat_id, url=normalized))
    await db.commit()
    return True


async def remove_allowed_link(db: AsyncSession, chat_id: int, url: str) -> bool:
    normalized = url.strip().lower()
    result = await db.execute(
        select(AllowedLink).where(
            AllowedLink.chat_id == chat_id,
            AllowedLink.url == normalized,
        )
    )
    db_link = result.scalars().first()
    if not db_link: return False

    await db.delete(db_link)
    await db.commit()
    return True


async def get_allowed_links(db: AsyncSession, chat_id: int) -> set[str]:
    result = await db.execute(select(AllowedLink.url).where(AllowedLink.chat_id == chat_id))
    return set(result.scalars().all())
