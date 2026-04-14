from src.database.schemas import ChatMemberStateUpdate

_POLL_RESET_FIELDS = {
    "poll_active": False,
    "poll_chat_id": None,
    "poll_thread_id": None,
    "poll_message_id": None,
    "poll_id": None,
    "poll_correct_option_id": None,
    "poll_started_at": None,
}


def poll_reset_state(**overrides) -> ChatMemberStateUpdate:
    return ChatMemberStateUpdate(**(_POLL_RESET_FIELDS | overrides))


def reset_after_unmute_state() -> ChatMemberStateUpdate:
    return poll_reset_state(muted_until=None, banned_until=None, passed_poll=True, poll_attempts=0)
