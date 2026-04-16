"""add poll progress fields for deep-link captcha flow

Revision ID: 3b2a1d4f9c6e
Revises: e2a9a8c4b1d7
Create Date: 2026-04-16 11:40:00.000000

"""

from __future__ import annotations
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3b2a1d4f9c6e"
down_revision: Union[str, Sequence[str], None] = "e2a9a8c4b1d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chat_member_states", sa.Column("poll_question_order", sa.Text(), nullable=True))
    op.add_column("chat_member_states", sa.Column("poll_question_index", sa.BigInteger(), nullable=False, server_default="0"))
    op.alter_column("chat_member_states", "poll_question_index", server_default=None)


def downgrade() -> None:
    op.drop_column("chat_member_states", "poll_question_index")
    op.drop_column("chat_member_states", "poll_question_order")
