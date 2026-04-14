import random

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import PollAnswer, PollQuestion


def _unique_answers(correct_answer: str, wrong_answers: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    for raw in [correct_answer] + list(wrong_answers):
        answer = raw.strip()
        if not answer:
            continue
        key = answer.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(answer)

    return out


async def create_poll_question(
    db: AsyncSession,
    *,
    question: str,
    correct_answer: str,
    wrong_answers: list[str],
    chat_id: int | None,
) -> PollQuestion:
    clean_question = question.strip()
    if not clean_question:
        raise ValueError("Question must not be empty.")

    options = _unique_answers(correct_answer, wrong_answers)
    if len(options) < 2:
        raise ValueError("Question must contain at least two unique answer options.")

    db_question = PollQuestion(chat_id=chat_id, question=clean_question, right_answer_id=None)
    db.add(db_question)
    await db.flush()

    answer_rows: list[PollAnswer] = []
    for option in options:
        row = PollAnswer(question_id=db_question.id, answer=option)
        db.add(row)
        answer_rows.append(row)

    await db.flush()
    db_question.right_answer_id = answer_rows[0].id
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
    if chat_id is None:
        stmt = stmt.where(PollQuestion.chat_id.is_(None))
    else:
        stmt = stmt.where(PollQuestion.chat_id == chat_id)

    result = await db.execute(stmt)
    db_question = result.scalars().first()
    if db_question is None:
        return False

    await db.delete(db_question)
    await db.commit()
    return True


async def get_poll_answers_for_question(db: AsyncSession, question_id: int) -> list[PollAnswer]:
    result = await db.execute(
        select(PollAnswer)
        .where(PollAnswer.question_id == question_id)
        .order_by(PollAnswer.id)
    )
    return list(result.scalars().all())


async def list_chat_poll_questions(db: AsyncSession, chat_id: int) -> list[PollQuestion]:
    result = await db.execute(
        select(PollQuestion)
        .where(PollQuestion.chat_id == chat_id)
        .order_by(PollQuestion.id)
    )
    return list(result.scalars().all())


async def list_default_poll_questions(db: AsyncSession) -> list[PollQuestion]:
    result = await db.execute(
        select(PollQuestion)
        .where(PollQuestion.chat_id.is_(None))
        .order_by(PollQuestion.id)
    )
    return list(result.scalars().all())


async def list_effective_poll_questions_for_chat(db: AsyncSession, chat_id: int) -> list[PollQuestion]:
    chat_specific = await list_chat_poll_questions(db, chat_id)
    if chat_specific:
        return chat_specific
    return await list_default_poll_questions(db)


async def get_random_poll_for_chat(
    db: AsyncSession,
    chat_id: int,
) -> tuple[PollQuestion, list[PollAnswer]] | None:
    question_ids_result = await db.execute(
        select(PollQuestion.id).where(PollQuestion.chat_id == chat_id)
    )
    question_ids = list(question_ids_result.scalars().all())

    if not question_ids:
        default_ids_result = await db.execute(
            select(PollQuestion.id).where(PollQuestion.chat_id.is_(None))
        )
        question_ids = list(default_ids_result.scalars().all())

    if not question_ids:
        return None

    question_id = random.choice(question_ids)

    question_result = await db.execute(
        select(PollQuestion).where(PollQuestion.id == question_id)
    )
    question = question_result.scalars().first()
    if question is None:
        return None

    answers = await get_poll_answers_for_question(db, question.id)
    if len(answers) < 2:
        return None

    return question, answers


async def count_default_poll_questions(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(PollQuestion)
        .where(PollQuestion.chat_id.is_(None))
    )
    return int(result.scalar_one() or 0)
