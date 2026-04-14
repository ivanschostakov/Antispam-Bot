from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import MOSCOW_TZ
from src.database.chat_member_state.model import ChatMemberState
from src.database.chat_member_state.schema import ChatMemberStateCreate, ChatMemberStateUpdate


async def get_chat_member_state(
    db: AsyncSession,
    chat_id: int,
    user_id: int,
) -> Optional[ChatMemberState]:
    result = await db.execute(
        select(ChatMemberState).where(
            ChatMemberState.chat_id == chat_id,
            ChatMemberState.user_id == user_id,
        )
    )
    return result.scalars().first()


async def get_state_by_active_poll(
    db: AsyncSession,
    *,
    user_id: int,
    poll_id: str,
) -> Optional[ChatMemberState]:
    result = await db.execute(
        select(ChatMemberState).where(
            ChatMemberState.user_id == user_id,
            ChatMemberState.poll_active.is_(True),
            ChatMemberState.poll_id == poll_id,
        )
    )
    return result.scalars().first()


async def create_chat_member_state(
    db: AsyncSession,
    user_in: ChatMemberStateCreate,
) -> ChatMemberState:
    db_state = ChatMemberState(**user_in.model_dump())
    db.add(db_state)
    await db.commit()
    await db.refresh(db_state)
    return db_state


async def update_chat_member_state(
    db: AsyncSession,
    chat_id: int,
    user_id: int,
    user_in: ChatMemberStateUpdate,
) -> Optional[ChatMemberState]:
    db_state = await get_chat_member_state(db, chat_id, user_id)
    if db_state is None:
        return None

    data = user_in.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(db_state, field, value)

    db.add(db_state)
    await db.commit()
    await db.refresh(db_state)
    return db_state


async def upsert_chat_member_state(
    db: AsyncSession,
    user_in: ChatMemberStateCreate,
) -> ChatMemberState:
    db_state = await get_chat_member_state(db, user_in.chat_id, user_in.user_id)
    if db_state is None:
        return await create_chat_member_state(db, user_in)

    update_data = ChatMemberStateUpdate(
        **user_in.model_dump(exclude={"chat_id", "user_id"})
    )
    updated = await update_chat_member_state(
        db,
        user_in.chat_id,
        user_in.user_id,
        update_data,
    )
    return updated  # type: ignore[return-value]


async def delete_chat_member_state(
    db: AsyncSession,
    *,
    chat_id: int,
    user_id: int,
) -> bool:
    db_state = await get_chat_member_state(db, chat_id, user_id)
    if db_state is None:
        return False

    await db.delete(db_state)
    await db.commit()
    return True


async def get_states_with_active_mute(
    db: AsyncSession,
    now: Optional[datetime] = None,
) -> list[ChatMemberState]:
    if now is None:
        now = datetime.now(tz=MOSCOW_TZ)

    result = await db.execute(
        select(ChatMemberState).where(
            ChatMemberState.muted_until.is_not(None),
            ChatMemberState.muted_until > now,
        )
    )
    return list(result.scalars().all())
