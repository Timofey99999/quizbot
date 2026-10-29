from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database import Database
from handlers.user import show_home

router = Router(name="fallback")


@router.callback_query()
async def stale_button(callback: CallbackQuery, state: FSMContext, db: Database, is_admin: bool):
    await state.clear()
    await callback.answer("Эта кнопка устарела — открываю меню")
    await show_home(callback, db, is_admin)


@router.message(F.chat.type == "private")
async def lost_message(message: Message, state: FSMContext, db: Database, is_admin: bool):
    await state.clear()
    await show_home(message, db, is_admin, fresh=True)
