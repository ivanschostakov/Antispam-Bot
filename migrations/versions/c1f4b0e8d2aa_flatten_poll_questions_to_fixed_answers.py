"""flatten poll questions to fixed answers

Revision ID: c1f4b0e8d2aa
Revises: 9d1b4c3a7f21
Create Date: 2026-04-14 19:15:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1f4b0e8d2aa"
down_revision: Union[str, Sequence[str], None] = "9d1b4c3a7f21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalize_options(raw_options: list[str | None]) -> tuple[str, str, str, str]:
    used: set[str] = set()
    out: list[str] = []

    for idx, raw in enumerate(raw_options, start=1):
        base = (raw or "").strip() or f"Вариант {idx}"
        candidate, suffix = base, 2
        while candidate.casefold() in used:
            candidate = f"{base} ({suffix})"
            suffix += 1
        used.add(candidate.casefold())
        out.append(candidate)

    return out[0], out[1], out[2], out[3]


def upgrade() -> None:
    op.add_column("poll_questions", sa.Column("right", sa.Text(), nullable=True))
    op.add_column("poll_questions", sa.Column("wrong1", sa.Text(), nullable=True))
    op.add_column("poll_questions", sa.Column("wrong2", sa.Text(), nullable=True))
    op.add_column("poll_questions", sa.Column("wrong3", sa.Text(), nullable=True))

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    has_poll_answers = "poll_answers" in table_names
    poll_question_columns = {col["name"] for col in inspector.get_columns("poll_questions")}
    has_right_answer_id = "right_answer_id" in poll_question_columns

    if has_right_answer_id:
        question_rows = bind.execute(sa.text("SELECT id, right_answer_id FROM poll_questions")).mappings().all()
    else:
        question_rows = bind.execute(sa.text("SELECT id FROM poll_questions")).mappings().all()

    for row in question_rows:
        qid = int(row["id"])
        right_answer_id = row.get("right_answer_id") if has_right_answer_id else None
        answer_rows = []
        if has_poll_answers:
            answer_rows = bind.execute(
                sa.text("SELECT id, answer FROM poll_answers WHERE question_id = :qid ORDER BY id"),
                {"qid": qid},
            ).mappings().all()

        right = None
        if right_answer_id is not None:
            right = next((a["answer"] for a in answer_rows if a["id"] == right_answer_id), None)
        if right is None and answer_rows:
            right = answer_rows[0]["answer"]

        if right_answer_id is not None:
            wrongs = [a["answer"] for a in answer_rows if a["id"] != right_answer_id]
        else:
            wrongs = [a["answer"] for a in answer_rows[1:]]

        raw_options = [right, *wrongs[:3]]
        while len(raw_options) < 4:
            raw_options.append(None)
        right_text, wrong1_text, wrong2_text, wrong3_text = _normalize_options(raw_options[:4])

        bind.execute(
            sa.text(
                """
                UPDATE poll_questions
                SET "right" = :right, wrong1 = :wrong1, wrong2 = :wrong2, wrong3 = :wrong3
                WHERE id = :qid
                """
            ),
            {
                "qid": qid,
                "right": right_text,
                "wrong1": wrong1_text,
                "wrong2": wrong2_text,
                "wrong3": wrong3_text,
            },
        )

    op.alter_column("poll_questions", "right", nullable=False)
    op.alter_column("poll_questions", "wrong1", nullable=False)
    op.alter_column("poll_questions", "wrong2", nullable=False)
    op.alter_column("poll_questions", "wrong3", nullable=False)

    if has_right_answer_id:
        fk_names = {fk.get("name") for fk in inspector.get_foreign_keys("poll_questions") if fk.get("name")}
        if "fk_poll_questions_right_answer_id" in fk_names:
            op.drop_constraint("fk_poll_questions_right_answer_id", "poll_questions", type_="foreignkey")
        op.drop_column("poll_questions", "right_answer_id")

    if has_poll_answers:
        poll_answer_indexes = {idx.get("name") for idx in inspector.get_indexes("poll_answers") if idx.get("name")}
        if "ix_poll_answers_question_id" in poll_answer_indexes:
            op.drop_index("ix_poll_answers_question_id", table_name="poll_answers")
        op.drop_table("poll_answers")


def downgrade() -> None:
    op.add_column("poll_questions", sa.Column("right_answer_id", sa.BigInteger(), nullable=True))

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

    bind = op.get_bind()
    rows = bind.execute(sa.text('SELECT id, "right", wrong1, wrong2, wrong3 FROM poll_questions')).mappings().all()
    for row in rows:
        qid = int(row["id"])
        right_id = bind.execute(
            sa.text("INSERT INTO poll_answers (question_id, answer) VALUES (:question_id, :answer) RETURNING id"),
            {"question_id": qid, "answer": row["right"]},
        ).scalar_one()
        for wrong_key in ("wrong1", "wrong2", "wrong3"):
            bind.execute(
                sa.text("INSERT INTO poll_answers (question_id, answer) VALUES (:question_id, :answer)"),
                {"question_id": qid, "answer": row[wrong_key]},
            )
        bind.execute(
            sa.text("UPDATE poll_questions SET right_answer_id = :right_answer_id WHERE id = :qid"),
            {"right_answer_id": right_id, "qid": qid},
        )

    op.drop_column("poll_questions", "wrong3")
    op.drop_column("poll_questions", "wrong2")
    op.drop_column("poll_questions", "wrong1")
    op.drop_column("poll_questions", "right")
