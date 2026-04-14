from sqlalchemy import BigInteger, Column, String

from src.database import Base


class ModeratedChat(Base):
    __tablename__ = "moderated_chats"

    id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=False)
    greetings_message = Column(String, nullable=True, default=None)
