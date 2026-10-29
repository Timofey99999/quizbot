from aiogram.fsm.state import State, StatesGroup


class QuizForm(StatesGroup):
    title = State()
    description = State()
    cover = State()


class QuestionForm(StatesGroup):
    text = State()
    kind = State()
    options = State()
    correct = State()
    answers = State()
    image = State()
    explanation = State()


class Edit(StatesGroup):
    quiz_title = State()
    quiz_description = State()
    quiz_cover = State()
    question_text = State()
    question_image = State()
    question_explanation = State()
    welcome_text = State()
    welcome_image = State()


class AdminForm(StatesGroup):
    user = State()
