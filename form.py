from aiogram.fsm.state import State, StatesGroup


class Form(StatesGroup):
    collecting_values = State()