from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class ChatMemberState(Base):
    __tablename__ = "chat_member_states"

    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("moderated_chats.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
        autoincrement=False,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, nullable=False, autoincrement=False)

    full_name: Mapped[str] = mapped_column(String, nullable=False)
    username: Mapped[str | None] = mapped_column(String, nullable=True, default=None)

    passed_poll: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    whitelist: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    muted_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    times_muted: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    banned_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    times_banned: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    messages_sent: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    times_reported: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    accused_spam: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_accused_text: Mapped[str | None] = mapped_column(String, nullable=True, default=None)

    poll_attempts: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    poll_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    poll_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, default=None)
    poll_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, default=None)
    poll_thread_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, default=None)
    poll_id: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    poll_correct_option_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, default=None)
    poll_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    poll_question_order: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    poll_question_index: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    __table_args__ = (
        Index("ix_chat_member_states_user_id", "user_id"),
        Index("ix_chat_member_states_chat_id_poll_id", "chat_id", "poll_id"),
    )
