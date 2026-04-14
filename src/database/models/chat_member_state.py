from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, String

from src.database import Base


class ChatMemberState(Base):
    __tablename__ = "chat_member_states"

    chat_id = Column(
        BigInteger,
        ForeignKey("moderated_chats.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
        autoincrement=False,
    )
    user_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=False)

    full_name = Column(String, nullable=False)
    username = Column(String, nullable=True, default=None)

    passed_poll = Column(Boolean, nullable=False, default=True)
    whitelist = Column(Boolean, nullable=False, default=False)

    muted_until = Column(DateTime(timezone=True), nullable=True, default=None)
    times_muted = Column(BigInteger, nullable=False, default=0)

    banned_until = Column(DateTime(timezone=True), nullable=True, default=None)
    times_banned = Column(BigInteger, nullable=False, default=0)

    messages_sent = Column(BigInteger, nullable=False, default=0)
    times_reported = Column(BigInteger, nullable=False, default=0)
    accused_spam = Column(Boolean, nullable=False, default=False)
    last_accused_text = Column(String, nullable=True, default=None)

    poll_attempts = Column(BigInteger, nullable=False, default=0)
    poll_active = Column(Boolean, nullable=False, default=False)
    poll_message_id = Column(BigInteger, nullable=True, default=None)
    poll_chat_id = Column(BigInteger, nullable=True, default=None)
    poll_thread_id = Column(BigInteger, nullable=True, default=None)
    poll_id = Column(String, nullable=True, default=None)
    poll_correct_option_id = Column(BigInteger, nullable=True, default=None)
    poll_started_at = Column(DateTime(timezone=True), nullable=True, default=None)

    __table_args__ = (
        Index("ix_chat_member_states_user_id", "user_id"),
        Index("ix_chat_member_states_chat_id_poll_id", "chat_id", "poll_id"),
    )
