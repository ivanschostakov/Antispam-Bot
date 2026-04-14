"""allowed links per chat and greetings message

Revision ID: 9d1b4c3a7f21
Revises: 0f6a8bd9be12
Create Date: 2026-04-14 16:05:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9d1b4c3a7f21"
down_revision: Union[str, Sequence[str], None] = "0f6a8bd9be12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "moderated_chats",
        sa.Column("greetings_message", sa.String(), nullable=True),
    )

    op.create_table(
        "allowed_links",
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["moderated_chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chat_id", "url"),
    )
    op.create_index("ix_allowed_links_chat_id", "allowed_links", ["chat_id"], unique=False)

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "blocked_links" in inspector.get_table_names():
        op.drop_table("blocked_links")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "blocked_links" not in inspector.get_table_names():
        op.create_table(
            "blocked_links",
            sa.Column("url", sa.String(), nullable=False),
            sa.PrimaryKeyConstraint("url"),
        )

    op.drop_index("ix_allowed_links_chat_id", table_name="allowed_links")
    op.drop_table("allowed_links")

    op.drop_column("moderated_chats", "greetings_message")
