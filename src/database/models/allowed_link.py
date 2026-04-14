from sqlalchemy import BigInteger, Column, ForeignKey, String

from src.database import Base


class AllowedLink(Base):
    __tablename__ = "allowed_links"

    chat_id = Column(
        BigInteger,
        ForeignKey("moderated_chats.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
        autoincrement=False,
    )
    url = Column(String, primary_key=True, nullable=False)
