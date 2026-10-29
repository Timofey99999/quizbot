from aiogram.filters.callback_data import CallbackData


class Nav(CallbackData, prefix="nav"):
    to: str


class Open(CallbackData, prefix="quiz"):
    action: str
    id: int


class Pick(CallbackData, prefix="pick"):
    attempt: int
    question: int
    option: int


class Flow(CallbackData, prefix="flow"):
    action: str
    attempt: int
    position: int = 0


class Adm(CallbackData, prefix="adm"):
    action: str
    quiz: int = 0
    question: int = 0
    value: int = 0
