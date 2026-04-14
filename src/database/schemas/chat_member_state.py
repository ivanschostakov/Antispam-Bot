from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ChatMemberStateBase(BaseModel):
    full_name: str
    username: Optional[str] = None

    passed_poll: bool = True
    whitelist: bool = False

    muted_until: Optional[datetime] = None
    times_muted: int = 0

    banned_until: Optional[datetime] = None
    times_banned: int = 0

    messages_sent: int = 0
    times_reported: int = 0
    accused_spam: bool = False
    last_accused_text: Optional[str] = None

    poll_attempts: int = 0
    poll_active: bool = False
    poll_message_id: Optional[int] = None
    poll_chat_id: Optional[int] = None
    poll_thread_id: Optional[int] = None
    poll_id: Optional[str] = None
    poll_correct_option_id: Optional[int] = None
    poll_started_at: Optional[datetime] = None


class ChatMemberStateCreate(ChatMemberStateBase):
    chat_id: int
    user_id: int


class ChatMemberStateUpdate(BaseModel):
    full_name: Optional[str] = None
    username: Optional[str] = None

    passed_poll: Optional[bool] = None
    whitelist: Optional[bool] = None

    muted_until: Optional[datetime] = None
    times_muted: Optional[int] = None

    banned_until: Optional[datetime] = None
    times_banned: Optional[int] = None

    messages_sent: Optional[int] = None
    times_reported: Optional[int] = None
    accused_spam: Optional[bool] = None
    last_accused_text: Optional[str] = None

    poll_attempts: Optional[int] = None
    poll_active: Optional[bool] = None
    poll_message_id: Optional[int] = None
    poll_chat_id: Optional[int] = None
    poll_thread_id: Optional[int] = None
    poll_id: Optional[str] = None
    poll_correct_option_id: Optional[int] = None
    poll_started_at: Optional[datetime] = None


class ChatMemberStateOut(ChatMemberStateBase):
    chat_id: int
    user_id: int

    class Config:
        orm_mode = True
