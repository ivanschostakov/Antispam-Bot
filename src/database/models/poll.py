from sqlalchemy import BigInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class PollQuestion(Base):
    __tablename__ = "poll_questions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, nullable=False, autoincrement=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    right: Mapped[str] = mapped_column(Text, nullable=False)
    wrong1: Mapped[str] = mapped_column(Text, nullable=False)
    wrong2: Mapped[str] = mapped_column(Text, nullable=False)
    wrong3: Mapped[str] = mapped_column(Text, nullable=False)
