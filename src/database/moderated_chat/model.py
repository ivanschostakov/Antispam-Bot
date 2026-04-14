from sqlalchemy import BigInteger, Column

from src.database import Base


class ModeratedChat(Base):
    __tablename__ = "moderated_chats"

    id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=False)
