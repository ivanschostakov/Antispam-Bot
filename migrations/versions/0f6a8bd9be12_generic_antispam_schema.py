"""generic antispam schema

Revision ID: 0f6a8bd9be12
Revises: f3001e830989
Create Date: 2026-04-14 13:20:00.000000

"""

from __future__ import annotations
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0f6a8bd9be12"
down_revision: Union[str, Sequence[str], None] = "f3001e830989"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_POLL_QUESTIONS: list[tuple[str, str, list[str]]] = [
    ("Какого цвета небо днём?", "Голубое", ["Зелёное", "Красное", "Чёрное"]),
    ("Какой звук издаёт кошка?", "Мяу", ["Гав", "Му", "Пи-пи"]),
    ("Какой звук издаёт собака?", "Гав", ["Мяу", "Кря", "Му"]),
    ("Что делают пчёлы?", "Мёд", ["Кетчуп", "Пластик", "Газ"]),
    ("Где живут рыбы?", "В воде", ["В небе", "В шкафу", "В кастрюле по умолчанию"]),
    ("Сколько лап у кошки?", "4", ["2", "3", "6"]),
    ("Сколько ног у человека?", "2", ["4", "3", "6"]),
    ("Что надевают на ноги?", "Обувь", ["Шапку", "Перчатки", "Очки"]),
    ("Что из этого обычно пьют?", "Воду", ["Камень", "Подушку", "Ложку"]),
    ("Какое животное из списка умеет летать?", "Птица", ["Собака", "Кошка", "Корова"]),
    ("Чем человек видит?", "Глазами", ["Ушами", "Коленом", "Пальцем"]),
    ("Чем человек слышит?", "Ушами", ["Ногами", "Глазами", "Пупком"]),
    ("Чем человек чувствует запахи?", "Носом", ["Пяткой", "Ухом", "Локтем"]),
    ("Что надевают на голову зимой?", "Шапку", ["Туфли", "Перчатки", "Носки"]),
    ("Что обычно несут куры?", "Яйца", ["Камни", "Телефоны", "Автомобили"]),
    ("Что любит пить корова?", "Воду", ["Пепси", "Бензин", "Краску"]),
    ("Как обычно передвигается змея?", "Ползёт", ["Летает", "Скачет", "Бегает на лапах"]),
    ("Что делают дети на качелях?", "Качаются", ["Моют посуду", "Чинят машину", "Спят"]),
    ("Где растут яблоки?", "На дереве", ["Под водой", "В песке", "В холодильнике сами по себе"]),
    ("Куда человек надевает перчатки?", "На руки", ["На ноги", "На голову", "На уши"]),
]


def _seed_default_poll_questions() -> None:
    bind = op.get_bind()

    existing_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM poll_questions WHERE chat_id IS NULL")
    ).scalar_one()
    if int(existing_count or 0) > 0:
        return

    for question_text, right_answer, wrong_answers in DEFAULT_POLL_QUESTIONS:
        question_id = bind.execute(
            sa.text(
                """
                INSERT INTO poll_questions (chat_id, question, right_answer_id)
                VALUES (NULL, :question, NULL)
                RETURNING id
                """
            ),
            {"question": question_text},
        ).scalar_one()

        all_answers = [right_answer] + list(wrong_answers)
        right_answer_id = None
        for idx, answer in enumerate(all_answers):
            answer_id = bind.execute(
                sa.text(
                    """
                    INSERT INTO poll_answers (question_id, answer)
                    VALUES (:question_id, :answer)
                    RETURNING id
                    """
                ),
                {"question_id": question_id, "answer": answer},
            ).scalar_one()
            if idx == 0:
                right_answer_id = answer_id

        bind.execute(
            sa.text(
                """
                UPDATE poll_questions
                SET right_answer_id = :right_answer_id
                WHERE id = :question_id
                """
            ),
            {"right_answer_id": right_answer_id, "question_id": question_id},
        )


def upgrade() -> None:
    op.create_table(
        "moderated_chats",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "poll_questions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("right_answer_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["chat_id"], ["moderated_chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_poll_questions_chat_id", "poll_questions", ["chat_id"], unique=False)
    op.create_index("ix_poll_questions_chat_id_id", "poll_questions", ["chat_id", "id"], unique=False)

    op.create_table(
        "poll_answers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("question_id", sa.BigInteger(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["poll_questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_id", "answer", name="uq_poll_answers_question_answer"),
    )
    op.create_index("ix_poll_answers_question_id", "poll_answers", ["question_id"], unique=False)

    op.create_foreign_key(
        "fk_poll_questions_right_answer_id",
        "poll_questions",
        "poll_answers",
        ["right_answer_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "chat_member_states",
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("passed_poll", sa.Boolean(), nullable=False),
        sa.Column("whitelist", sa.Boolean(), nullable=False),
        sa.Column("muted_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("times_muted", sa.BigInteger(), nullable=False),
        sa.Column("banned_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("times_banned", sa.BigInteger(), nullable=False),
        sa.Column("messages_sent", sa.BigInteger(), nullable=False),
        sa.Column("times_reported", sa.BigInteger(), nullable=False),
        sa.Column("accused_spam", sa.Boolean(), nullable=False),
        sa.Column("last_accused_text", sa.String(), nullable=True),
        sa.Column("poll_attempts", sa.BigInteger(), nullable=False),
        sa.Column("poll_active", sa.Boolean(), nullable=False),
        sa.Column("poll_message_id", sa.BigInteger(), nullable=True),
        sa.Column("poll_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("poll_thread_id", sa.BigInteger(), nullable=True),
        sa.Column("poll_id", sa.String(), nullable=True),
        sa.Column("poll_correct_option_id", sa.BigInteger(), nullable=True),
        sa.Column("poll_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["chat_id"], ["moderated_chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chat_id", "user_id"),
    )
    op.create_index("ix_chat_member_states_user_id", "chat_member_states", ["user_id"], unique=False)
    op.create_index(
        "ix_chat_member_states_chat_id_poll_id",
        "chat_member_states",
        ["chat_id", "poll_id"],
        unique=False,
    )

    from alembic import context

    if context.is_offline_mode():
        return

    _seed_default_poll_questions()


def downgrade() -> None:
    op.drop_index("ix_chat_member_states_chat_id_poll_id", table_name="chat_member_states")
    op.drop_index("ix_chat_member_states_user_id", table_name="chat_member_states")
    op.drop_table("chat_member_states")

    op.drop_constraint("fk_poll_questions_right_answer_id", "poll_questions", type_="foreignkey")
    op.drop_index("ix_poll_answers_question_id", table_name="poll_answers")
    op.drop_table("poll_answers")

    op.drop_index("ix_poll_questions_chat_id_id", table_name="poll_questions")
    op.drop_index("ix_poll_questions_chat_id", table_name="poll_questions")
    op.drop_table("poll_questions")

    op.drop_table("moderated_chats")
