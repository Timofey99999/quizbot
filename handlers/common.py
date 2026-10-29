from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

from database import Database
from handlers.admin.views import admin_home
from handlers.user import open_quiz, show_home
from states import AdminForm
from ui import drop, show, wipe

router = Router(name="common")
router.message.filter(F.chat.type == "private")


async def reset(message: Message, state: FSMContext) -> bool:
    current = await state.get_state()
    if current is None:
        return False
    panel = (await state.get_data()).get("panel")
    await state.clear()
    await drop(message.bot, message.chat.id, panel)
    if current == AdminForm.user.state:
        cleaner = await message.answer("↩️", reply_markup=ReplyKeyboardRemove())
        await wipe(cleaner)
    return True


@router.message(CommandStart())
async def start(message: Message, command: CommandObject, state: FSMContext, db: Database, is_admin: bool):
    await reset(message, state)
    payload = (command.args or "").strip()
    if payload.startswith("q") and payload[1:].isdigit():
        if await open_quiz(message, db, int(payload[1:]), is_admin, fresh=True):
            return
    await show_home(message, db, is_admin, fresh=True)


@router.message(Command("id"))
async def my_id(message: Message):
    await message.answer(
        f"🪪 Твой Telegram ID: <code>{message.from_user.id}</code>\n\n"
        "<i>Нажми на число, чтобы скопировать. Его можно отправить админу, чтобы тебе выдали доступ к панели.</i>"
    )


@router.message(Command("help"))
async def help_command(message: Message, is_admin: bool):
    lines = [
        "🤖 <b>Как здесь всё устроено</b>",
        "",
        "• /start — главное меню со всеми квизами",
        "• Отвечай кнопками или текстом — бот подскажет, как именно",
        "• Если выйти посреди квиза, прогресс сохранится",
        "• /id — узнать свой Telegram ID",
    ]
    if is_admin:
        lines += ["", "⚙️ /admin — админ-панель", "↩️ /cancel — прервать любое действие в панели"]
    await message.answer("\n".join(lines))


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext, db: Database, is_admin: bool):
    was_busy = await reset(message, state)
    if is_admin and was_busy:
        text, markup, image = await admin_home(db, "↩️ Действие отменено")
        await show(message, text, markup, image, state=state, fresh=True)
        return
    await show_home(message, db, is_admin, fresh=True)

