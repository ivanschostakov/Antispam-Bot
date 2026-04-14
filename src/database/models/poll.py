from sqlalchemy import BigInteger, Column, ForeignKey, Index, Text, UniqueConstraint

from src.database import Base


class PollQuestion(Base):
    __tablename__ = "poll_questions"

    id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True)
    chat_id = Column(
        BigInteger,
        ForeignKey("moderated_chats.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    question = Column(Text, nullable=False)
    right_answer_id = Column(
        BigInteger,
        ForeignKey(
            "poll_answers.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_poll_questions_right_answer_id",
        ),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_poll_questions_chat_id_id", "chat_id", "id"),
    )


class PollAnswer(Base):
    __tablename__ = "poll_answers"

    id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True)
    question_id = Column(
        BigInteger,
        ForeignKey("poll_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    answer = Column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("question_id", "answer", name="uq_poll_answers_question_answer"),
    )
