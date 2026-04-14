from sqlalchemy import BigInteger, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class PollQuestion(Base):
    __tablename__ = "poll_questions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, nullable=False, autoincrement=True)
    chat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("moderated_chats.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    right: Mapped[str] = mapped_column(Text, nullable=False)
    wrong1: Mapped[str] = mapped_column(Text, nullable=False)
    wrong2: Mapped[str] = mapped_column(Text, nullable=False)
    wrong3: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("ix_poll_questions_chat_id_id", "chat_id", "id"),
    )
