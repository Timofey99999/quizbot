import csv
import io
import re
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    KeyboardButton,
    KeyboardButtonRequestUsers,
    Message,
    MessageOriginUser,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from callbacks import Adm, Nav
from commands import grant_commands, revoke_commands
from database import Database
from handlers.admin.forms import ask, navigate, read_image, read_rich
from handlers.admin.views import (
    admin_home,
    admins_screen,
    cancel_markup,
    confirm_markup,
    settings_screen,
    stats_screen,
)
from states import AdminForm, Edit
from ui import cut, drop, esc, flash, plain, show, wipe

router = Router(name="admin-panel")

CANCEL_WORD = "✖️ Отмена"


@router.message(Command("admin"))
async def admin_command(message: Message, state: FSMContext, db: Database):
    await state.clear()
    text, markup, image = await admin_home(db)
    await show(message, text, markup, image, state=state, fresh=True)


@router.callback_query(Nav.filter(F.to == "admin"))
@router.callback_query(Adm.filter(F.action == "home"))
async def admin_root(callback: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    text, markup, image = await admin_home(db)
    await show(callback, text, markup, image, state=state)
    await callback.answer()


@router.callback_query(Adm.filter(F.action == "cancel"))
async def cancel_input(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    target = (await state.get_data()).get("back") or {"view": "home"}
    await navigate(callback, state, db, bot, owners, target)
    await callback.answer("Отменено")


@router.callback_query(Adm.filter(F.action == "settings"))
async def settings(callback: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    text, markup, image = await settings_screen(db)
    await show(callback, text, markup, image, state=state)
    await callback.answer()


@router.callback_query(Adm.filter(F.action == "welcome_text"))
async def welcome_text_prompt(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Edit.welcome_text)
    await state.update_data(back={"view": "settings"})
    await ask(
        callback,
        state,
        "✏️ <b>Текст приветствия</b>\n\n"
        "Пришли новый текст одним сообщением. Жирный, курсив, ссылки и спойлеры сохранятся.\n\n"
        "Напиши <code>{name}</code> — и бот подставит туда имя пользователя.\n\n"
        "<i>До 900 символов.</i>",
        cancel_markup("cancel"),
    )
    await callback.answer()


@router.message(Edit.welcome_text)
async def welcome_text_input(message: Message, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    value = await read_rich(message, 900)
    if value is None:
        return
    await wipe(message)
    await db.set_setting("welcome_text", value)
    await navigate(message, state, db, bot, owners, {"view": "settings"}, "✅ Приветствие обновлено")


@router.callback_query(Adm.filter(F.action == "welcome_reset"))
async def welcome_reset(callback: CallbackQuery, state: FSMContext, db: Database):
    await db.set_setting("welcome_text", None)
    text, markup, image = await settings_screen(db, "♻️ Вернули стандартный текст")
    await show(callback, text, markup, image, state=state)
    await callback.answer()


@router.callback_query(Adm.filter(F.action == "welcome_image"))
async def welcome_image_prompt(callback: CallbackQuery, state: FSMContext, db: Database):
    await state.set_state(Edit.welcome_image)
    await state.update_data(back={"view": "settings"})
    extra = []
    if await db.get_setting("welcome_image"):
        extra.append(("🗑 Убрать картинку", Adm(action="welcome_image_del")))
    await ask(
        callback,
        state,
        "🖼 <b>Картинка приветствия</b>\n\n"
        "Пришли изображение — оно встанет над текстом в главном меню.\n\n"
        "<i>Лучше всего смотрятся горизонтальные картинки, примерно 16:9.</i>",
        cancel_markup("cancel", extra=extra),
    )
    await callback.answer()


@router.message(Edit.welcome_image)
async def welcome_image_input(message: Message, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    image = await read_image(message)
    if image is None:
        return
    await wipe(message)
    await db.set_setting("welcome_image", image)
    await navigate(message, state, db, bot, owners, {"view": "settings"}, "✅ Картинка обновлена")


@router.callback_query(Adm.filter(F.action == "welcome_image_del"))
async def welcome_image_delete(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    await db.set_setting("welcome_image", None)
    await navigate(callback, state, db, bot, owners, {"view": "settings"}, "🗑 Картинка убрана")
    await callback.answer()


@router.callback_query(Adm.filter(F.action == "admins"))
async def admins(callback: CallbackQuery, state: FSMContext, db: Database, owners: frozenset[int]):
    await state.clear()
    text, markup, image = await admins_screen(db, owners)
    await show(callback, text, markup, image, state=state)
    await callback.answer()


@router.callback_query(Adm.filter(F.action == "admin_add"))
async def admin_add_prompt(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(AdminForm.user)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="👤 Выбрать из контактов",
                    request_users=KeyboardButtonRequestUsers(
                        request_id=1,
                        user_is_bot=False,
                        max_quantity=1,
                        request_name=True,
                        request_username=True,
                    ),
                )
            ],
            [KeyboardButton(text=CANCEL_WORD)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Telegram ID, например 123456789",
    )
    await drop(callback.bot, callback.message.chat.id, callback.message.message_id)
    prompt = await callback.message.answer(
        "➕ <b>Выдать доступ к админ-панели</b>\n\n"
        "Как удобнее:\n"
        "• пришли <b>Telegram ID</b> числом\n"
        "• или перешли сюда любое сообщение этого человека\n"
        "• или нажми «Выбрать из контактов» внизу\n\n"
        "<i>Свой ID человек может узнать командой /id в этом боте.</i>",
        reply_markup=keyboard,
    )
    await state.update_data(panel=prompt.message_id)
    await callback.answer()


def extract_user(message: Message) -> tuple[int | None, str | None]:
    if message.users_shared and message.users_shared.users:
        shared = message.users_shared.users[0]
        name = " ".join(filter(None, [shared.first_name, shared.last_name])) or None
        return shared.user_id, name
    if isinstance(message.forward_origin, MessageOriginUser):
        user = message.forward_origin.sender_user
        return user.id, user.full_name
    if message.text:
        digits = re.sub(r"[\s\-]", "", message.text)
        if digits.isdigit() and 4 <= len(digits) <= 15:
            return int(digits), None
    return None, None


async def close_admin_form(message: Message, state: FSMContext) -> None:
    panel = (await state.get_data()).get("panel")
    await state.clear()
    await drop(message.bot, message.chat.id, panel)
    await wipe(message)
    cleaner = await message.answer("⏳", reply_markup=ReplyKeyboardRemove())
    await wipe(cleaner)


@router.message(AdminForm.user)
async def admin_add_input(message: Message, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    if message.text == CANCEL_WORD:
        await close_admin_form(message, state)
        text, markup, image = await admins_screen(db, owners, "↩️ Отменено")
        await show(message, text, markup, image, state=state, fresh=True)
        return

    if message.forward_origin and not isinstance(message.forward_origin, MessageOriginUser):
        return await flash(
            message,
            "🔒 У этого человека скрыт профиль при пересылке. Попроси его прислать ID через /id или выбери из контактов.",
            delay=7,
        )

    user_id, name = extract_user(message)
    if user_id is None:
        return await flash(message, "🤔 Не похоже на Telegram ID. Нужно число вроде <code>123456789</code>", delay=6)
    if user_id == bot.id:
        return await flash(message, "😅 Это ID самого бота. Нужен ID человека")

    await close_admin_form(message, state)

    if user_id in owners or await db.is_admin(user_id):
        notice = "ℹ️ У этого человека уже есть доступ"
    else:
        await db.add_admin(user_id, message.from_user.id)
        known = await db.get_user(user_id)
        label = esc(name or (known["name"] if known else None) or str(user_id))
        notice = f"✅ Доступ выдан: <b>{label}</b>"
        try:
            await bot.send_message(
                user_id,
                "🎉 Тебе выдали доступ к админ-панели!\n\nОткрыть её можно командой /admin или кнопкой в главном меню.",
            )
            await grant_commands(bot, user_id)
        except TelegramAPIError:
            notice += "\n<i>Он ещё не запускал бота — пусть нажмёт /start, и панель появится.</i>"

    text, markup, image = await admins_screen(db, owners, notice)
    await show(message, text, markup, image, state=state, fresh=True)


@router.callback_query(Adm.filter(F.action == "admin_del"))
async def admin_remove_confirm(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database):
    if callback_data.value == callback.from_user.id:
        return await callback.answer("Себя снять нельзя — попроси другого админа", show_alert=True)
    user = await db.get_user(callback_data.value)
    label = esc(user["name"]) if user else f"<code>{callback_data.value}</code>"
    await show(
        callback,
        f"⚠️ Забрать доступ к панели у <b>{label}</b>?",
        confirm_markup(
            Adm(action="admin_del_yes", value=callback_data.value),
            Adm(action="admins"),
            "✖️ Да, забрать доступ",
        ),
        state=state,
    )
    await callback.answer()


@router.callback_query(Adm.filter(F.action == "admin_del_yes"))
async def admin_remove(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    if callback_data.value in owners:
        return await callback.answer("Владельца из .env снять нельзя", show_alert=True)
    await db.remove_admin(callback_data.value)
    await revoke_commands(bot, callback_data.value)
    text, markup, image = await admins_screen(db, owners, "✖️ Доступ забран")
    await show(callback, text, markup, image, state=state)
    await callback.answer()


@router.callback_query(Adm.filter(F.action == "stats"))
async def stats(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database):
    screen = await stats_screen(db, callback_data.quiz)
    if screen is None:
        return await callback.answer("Квиз уже удалён", show_alert=True)
    await show(callback, *screen, state=state)
    await callback.answer()


def file_name(title: str) -> str:
    slug = re.sub(r"[^\w\-]+", "_", plain(title)).strip("_") or "quiz"
    return f"{slug[:40]}_{datetime.now():%Y-%m-%d}.csv"


@router.callback_query(Adm.filter(F.action == "export"))
async def export(callback: CallbackQuery, callback_data: Adm, db: Database):
    quiz = await db.get_quiz(callback_data.quiz)
    if quiz is None:
        return await callback.answer("Квиз уже удалён", show_alert=True)

    questions, rows = await db.export_rows(quiz.id)
    if not rows:
        return await callback.answer("Пока никто не отвечал — выгружать нечего", show_alert=True)

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        ["Дата", "Имя", "Username", "Telegram ID", "Статус", "Результат"]
        + [f"{i}. {cut(plain(q.text), 80)}" for i, q in enumerate(questions, 1)]
    )
    statuses = {"done": "завершил", "dropped": "бросил"}
    for row, answers in rows:
        cells = [
            datetime.fromtimestamp(row["started_at"]).strftime("%d.%m.%Y %H:%M"),
            row["name"] or "",
            f"@{row['username']}" if row["username"] else "",
            row["user_id"],
            statuses.get(row["stage"], "в процессе"),
            f"{row['correct']}/{row['scored']}" if row["scored"] else "",
        ]
        for question in questions:
            if question.id not in answers:
                cells.append("")
                continue
            answer, is_correct = answers[question.id]
            mark = "" if is_correct is None else (" ✓" if is_correct else " ✗")
            cells.append((answer or "(пропустил)") + mark)
        writer.writerow(cells)

    document = BufferedInputFile(buffer.getvalue().encode("utf-8-sig"), filename=file_name(quiz.title))
    await callback.message.answer_document(
        document,
        caption=f"📥 <b>{esc(quiz.title)}</b>\nСтрок: {len(rows)} · открывается в Excel и Google Таблицах",
    )
    await callback.answer("Файл отправлен 👇")
