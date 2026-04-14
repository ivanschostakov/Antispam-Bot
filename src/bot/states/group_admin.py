from aiogram.fsm.state import State, StatesGroup


class GroupAdminStates(StatesGroup):
    waiting_for_poll_csv = State()
