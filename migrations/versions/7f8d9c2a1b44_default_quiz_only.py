"""keep only default quiz questions

Revision ID: 7f8d9c2a1b44
Revises: 3b2a1d4f9c6e
Create Date: 2026-04-16 13:30:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7f8d9c2a1b44"
down_revision: Union[str, Sequence[str], None] = "3b2a1d4f9c6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def _drop_poll_questions_chat_fk(inspector: sa.Inspector) -> None:
    for fk in inspector.get_foreign_keys("poll_questions"):
        columns = fk.get("constrained_columns") or []
        name = fk.get("name")
        if "chat_id" in columns and name:
            op.drop_constraint(name, "poll_questions", type_="foreignkey")
            return


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "poll_questions") and _has_column(inspector, "poll_questions", "chat_id"):
        bind.execute(sa.text("DELETE FROM poll_questions WHERE chat_id IS NOT NULL"))
        _drop_poll_questions_chat_fk(inspector)
        if _has_index(inspector, "poll_questions", "ix_poll_questions_chat_id_id"):
            op.drop_index("ix_poll_questions_chat_id_id", table_name="poll_questions")
        if _has_index(inspector, "poll_questions", "ix_poll_questions_chat_id"):
            op.drop_index("ix_poll_questions_chat_id", table_name="poll_questions")
        op.drop_column("poll_questions", "chat_id")

    if _has_table(inspector, "chat_member_states") and _has_column(inspector, "chat_member_states", "poll_question_order"):
        op.drop_column("chat_member_states", "poll_question_order")

    if _has_table(inspector, "chat_member_states") and _has_column(inspector, "chat_member_states", "poll_question_index"):
        op.drop_column("chat_member_states", "poll_question_index")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "poll_questions") and not _has_column(inspector, "poll_questions", "chat_id"):
        op.add_column("poll_questions", sa.Column("chat_id", sa.BigInteger(), nullable=True))
        op.create_foreign_key(None, "poll_questions", "moderated_chats", ["chat_id"], ["id"], ondelete="CASCADE")
        op.create_index("ix_poll_questions_chat_id", "poll_questions", ["chat_id"], unique=False)
        op.create_index("ix_poll_questions_chat_id_id", "poll_questions", ["chat_id", "id"], unique=False)

    if _has_table(inspector, "chat_member_states") and not _has_column(inspector, "chat_member_states", "poll_question_order"):
        op.add_column("chat_member_states", sa.Column("poll_question_order", sa.Text(), nullable=True))

    if _has_table(inspector, "chat_member_states") and not _has_column(inspector, "chat_member_states", "poll_question_index"):
        op.add_column(
            "chat_member_states",
            sa.Column("poll_question_index", sa.BigInteger(), nullable=False, server_default="0"),
        )
        op.alter_column("chat_member_states", "poll_question_index", server_default=None)
