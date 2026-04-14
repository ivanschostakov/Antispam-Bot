"""greetings message to text

Revision ID: e2a9a8c4b1d7
Revises: c1f4b0e8d2aa
Create Date: 2026-04-14 20:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2a9a8c4b1d7"
down_revision: Union[str, Sequence[str], None] = "c1f4b0e8d2aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("moderated_chats", "greetings_message", existing_type=sa.String(), type_=sa.Text(), existing_nullable=True)


def downgrade() -> None:
    op.alter_column("moderated_chats", "greetings_message", existing_type=sa.Text(), type_=sa.String(), existing_nullable=True)
