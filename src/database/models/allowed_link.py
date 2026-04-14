from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class AllowedLink(Base):
    __tablename__ = "allowed_links"

    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("moderated_chats.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
        autoincrement=False,
    )
    url: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
