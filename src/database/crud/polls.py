import random

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import PollQuestion


def _validate_poll(question: str, correct_answer: str, wrong_answers: list[str]) -> tuple[str, str, str, str, str]:
    clean_question = question.strip()
    if not clean_question:
        raise ValueError("Question must not be empty.")
    if len(wrong_answers) != 3:
        raise ValueError("Exactly 3 wrong answers are required.")

    options = [correct_answer, *wrong_answers]
    cleaned = [opt.strip() for opt in options]
    if any(not opt for opt in cleaned):
        raise ValueError("All 4 answer options must be non-empty.")
    if len({opt.casefold() for opt in cleaned}) != 4:
        raise ValueError("All 4 answer options must be unique.")
    return clean_question, cleaned[0], cleaned[1], cleaned[2], cleaned[3]


async def create_poll_question(
    db: AsyncSession,
    *,
    question: str,
    correct_answer: str,
    wrong_answers: list[str],
) -> PollQuestion:
    clean_question, right, wrong1, wrong2, wrong3 = _validate_poll(question, correct_answer, wrong_answers)
    db_question = PollQuestion(question=clean_question, right=right, wrong1=wrong1, wrong2=wrong2, wrong3=wrong3)
    db.add(db_question)
    await db.commit()
    await db.refresh(db_question)
    return db_question


async def list_default_poll_questions(db: AsyncSession) -> list[PollQuestion]:
    result = await db.execute(select(PollQuestion).order_by(PollQuestion.id))
    return list(result.scalars().all())


async def get_random_default_poll_question(db: AsyncSession) -> PollQuestion | None:
    question_ids_result = await db.execute(select(PollQuestion.id))
    question_ids = list(question_ids_result.scalars().all())
    if not question_ids:
        return None

    question_id = random.choice(question_ids)
    question_result = await db.execute(select(PollQuestion).where(PollQuestion.id == question_id))
    question = question_result.scalars().first()
    if question is None:
        return None
    if not all([question.right, question.wrong1, question.wrong2, question.wrong3]):
        return None
    if len({question.right.casefold(), question.wrong1.casefold(), question.wrong2.casefold(), question.wrong3.casefold()}) != 4:
        return None
    return question


async def count_default_poll_questions(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(PollQuestion))
    return int(result.scalar_one() or 0)
