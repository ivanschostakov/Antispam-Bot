from sqlalchemy import BigInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class ModeratedChat(Base):
    __tablename__ = "moderated_chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, nullable=False, autoincrement=False)
    greetings_message: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
