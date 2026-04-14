import random

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import PollQuestion


def _validate_poll(question: str, correct_answer: str, wrong_answers: list[str]) -> tuple[str, str, str, str, str]:
    clean_question = question.strip()
    if not clean_question: raise ValueError("Question must not be empty.")
    if len(wrong_answers) != 3: raise ValueError("Exactly 3 wrong answers are required.")

    options = [correct_answer, *wrong_answers]
    cleaned = [opt.strip() for opt in options]
    if any(not opt for opt in cleaned): raise ValueError("All 4 answer options must be non-empty.")
    if len({opt.casefold() for opt in cleaned}) != 4: raise ValueError("All 4 answer options must be unique.")
    return clean_question, cleaned[0], cleaned[1], cleaned[2], cleaned[3]


async def create_poll_question(
    db: AsyncSession,
    *,
    question: str,
    correct_answer: str,
    wrong_answers: list[str],
    chat_id: int | None,
) -> PollQuestion:
    clean_question, right, wrong1, wrong2, wrong3 = _validate_poll(question, correct_answer, wrong_answers)
    db_question = PollQuestion(chat_id=chat_id, question=clean_question, right=right, wrong1=wrong1, wrong2=wrong2, wrong3=wrong3)
    db.add(db_question)
    await db.commit()
    await db.refresh(db_question)
    return db_question


async def delete_poll_question(
    db: AsyncSession,
    *,
    question_id: int,
    chat_id: int | None = None,
) -> bool:
    stmt = select(PollQuestion).where(PollQuestion.id == question_id)
    stmt = stmt.where(PollQuestion.chat_id.is_(None) if chat_id is None else PollQuestion.chat_id == chat_id)
    result = await db.execute(stmt)
    db_question = result.scalars().first()
    if db_question is None: return False

    await db.delete(db_question)
    await db.commit()
    return True


async def list_chat_poll_questions(db: AsyncSession, chat_id: int) -> list[PollQuestion]:
    result = await db.execute(select(PollQuestion).where(PollQuestion.chat_id == chat_id).order_by(PollQuestion.id))
    return list(result.scalars().all())


async def list_default_poll_questions(db: AsyncSession) -> list[PollQuestion]:
    result = await db.execute(select(PollQuestion).where(PollQuestion.chat_id.is_(None)).order_by(PollQuestion.id))
    return list(result.scalars().all())


async def list_effective_poll_questions_for_chat(db: AsyncSession, chat_id: int) -> list[PollQuestion]:
    chat_specific = await list_chat_poll_questions(db, chat_id)
    return chat_specific if chat_specific else await list_default_poll_questions(db)


async def get_random_poll_for_chat(db: AsyncSession, chat_id: int) -> PollQuestion | None:
    question_ids_result = await db.execute(select(PollQuestion.id).where(PollQuestion.chat_id == chat_id))
    question_ids = list(question_ids_result.scalars().all())
    if not question_ids:
        default_ids_result = await db.execute(select(PollQuestion.id).where(PollQuestion.chat_id.is_(None)))
        question_ids = list(default_ids_result.scalars().all())
    if not question_ids: return None

    question_id = random.choice(question_ids)
    question_result = await db.execute(select(PollQuestion).where(PollQuestion.id == question_id))
    question = question_result.scalars().first()
    if question is None: return None
    if not all([question.right, question.wrong1, question.wrong2, question.wrong3]): return None
    if len({question.right.casefold(), question.wrong1.casefold(), question.wrong2.casefold(), question.wrong3.casefold()}) != 4: return None
    return question


async def count_default_poll_questions(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(PollQuestion).where(PollQuestion.chat_id.is_(None)))
    return int(result.scalar_one() or 0)
