from aiogram import F, Router

from handlers.admin import panel, questions, quizzes
from middlewares import IsAdmin


def build_router() -> Router:
    router = Router(name="admin")
    router.message.filter(F.chat.type == "private", IsAdmin())
    router.callback_query.filter(IsAdmin())
    router.include_routers(panel.router, quizzes.router, questions.router)
    return router
