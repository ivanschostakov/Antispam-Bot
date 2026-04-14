from sqlalchemy.ext.asyncio import AsyncSession

from config import MODERATED_CHAT_IDS
from src.database.moderated_chat import add_moderated_chat
from src.database.poll import count_default_poll_questions, create_poll_question
from src.poll_questions import POLL_QUESTIONS_RU


async def seed_moderated_chats(db: AsyncSession) -> None:
    for chat_id in MODERATED_CHAT_IDS:
        await add_moderated_chat(db, chat_id)


async def seed_default_poll_questions(db: AsyncSession) -> None:
    if await count_default_poll_questions(db) > 0:
        return

    for poll in POLL_QUESTIONS_RU:
        await create_poll_question(
            db,
            question=poll.text,
            correct_answer=poll.answer,
            wrong_answers=poll.others,
            chat_id=None,
        )


async def bootstrap_database_defaults(db: AsyncSession) -> None:
    await seed_moderated_chats(db)
    await seed_default_poll_questions(db)
