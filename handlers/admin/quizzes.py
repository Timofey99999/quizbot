from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from callbacks import Adm
from database import Database
from handlers.admin.forms import ask, navigate, read_image, read_plain, read_rich
from handlers.admin.views import cancel_markup, confirm_markup, quiz_screen, quizzes_screen
from states import Edit, QuizForm
from ui import esc, plural, questions_word, show, wipe

router = Router(name="admin-quizzes")

TITLE_LIMIT = 60
DESCRIPTION_LIMIT = 600


@router.callback_query(Adm.filter(F.action == "quizzes"))
async def quizzes(callback: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    await show(callback, *await quizzes_screen(db), state=state)
    await callback.answer()


@router.callback_query(Adm.filter(F.action == "quiz"))
async def quiz_card(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database, bot: Bot):
    await state.clear()
    screen = await quiz_screen(db, bot, callback_data.quiz)
    if screen is None:
        await callback.answer("Этот квиз уже удалён", show_alert=True)
        screen = await quizzes_screen(db)
    else:
        await callback.answer()
    await show(callback, *screen, state=state)


def skip_markup(label: str):
    return cancel_markup("cancel", extra=[(label, Adm(action="skip"))])


@router.callback_query(Adm.filter(F.action == "quiz_new"))
async def new_quiz(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(QuizForm.title)
    await state.update_data(back={"view": "quizzes"}, draft={})
    await ask(
        callback,
        state,
        "➕ <b>Новый квиз</b> · шаг 1 из 3\n\n"
        "Как он будет называться? Название появится на кнопке в главном меню.\n\n"
        f"<i>Например: «🚀 Космический квиз». До {TITLE_LIMIT} символов, эмодзи приветствуются.</i>",
        cancel_markup("cancel"),
    )
    await callback.answer()


async def ask_description(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(QuizForm.description)
    draft = (await state.get_data())["draft"]
    await ask(
        event,
        state,
        f"➕ <b>{esc(draft['title'])}</b> · шаг 2 из 3\n\n"
        "Напиши пару строк о квизе — их увидят перед стартом. "
        "Форматирование сохранится.\n\n"
        f"<i>До {DESCRIPTION_LIMIT} символов. Можно пропустить.</i>",
        skip_markup("⏭ Без описания"),
    )


async def ask_cover(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(QuizForm.cover)
    draft = (await state.get_data())["draft"]
    await ask(
        event,
        state,
        f"➕ <b>{esc(draft['title'])}</b> · шаг 3 из 3\n\n"
        "Пришли обложку — она будет над описанием и над вопросами без своей картинки.\n\n"
        "<i>Лучше всего горизонтальная картинка 16:9. Можно пропустить и добавить потом.</i>",
        skip_markup("⏭ Без обложки"),
    )


async def create_from_draft(event: Message | CallbackQuery, state: FSMContext, db: Database, bot: Bot, owners) -> None:
    draft = (await state.get_data())["draft"]
    quiz_id = await db.create_quiz(draft["title"], draft.get("description", ""), draft.get("image"))
    await navigate(
        event, state, db, bot, owners, {"view": "quiz", "quiz": quiz_id},
        "✨ Квиз создан! Теперь добавь вопросы и опубликуй его.",
    )


@router.message(QuizForm.title)
async def title_input(message: Message, state: FSMContext):
    title = await read_plain(message, TITLE_LIMIT)
    if title is None:
        return
    await wipe(message)
    data = await state.get_data()
    await state.update_data(draft={**data["draft"], "title": title})
    await ask_description(message, state)


@router.message(QuizForm.description)
async def description_input(message: Message, state: FSMContext):
    description = await read_rich(message, DESCRIPTION_LIMIT)
    if description is None:
        return
    await wipe(message)
    data = await state.get_data()
    await state.update_data(draft={**data["draft"], "description": description})
    await ask_cover(message, state)


@router.callback_query(QuizForm.description, Adm.filter(F.action == "skip"))
async def description_skip(callback: CallbackQuery, state: FSMContext):
    await ask_cover(callback, state)
    await callback.answer()


@router.message(QuizForm.cover)
async def cover_input(message: Message, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    image = await read_image(message)
    if image is None:
        return
    await wipe(message)
    data = await state.get_data()
    await state.update_data(draft={**data["draft"], "image": image})
    await create_from_draft(message, state, db, bot, owners)


@router.callback_query(QuizForm.cover, Adm.filter(F.action == "skip"))
async def cover_skip(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    await create_from_draft(callback, state, db, bot, owners)
    await callback.answer()


async def start_edit(callback: CallbackQuery, state: FSMContext, edit_state, quiz_id: int) -> None:
    await state.clear()
    await state.set_state(edit_state)
    await state.update_data(quiz=quiz_id, back={"view": "quiz", "quiz": quiz_id})


@router.callback_query(Adm.filter(F.action == "quiz_title"))
async def edit_title(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database):
    quiz = await db.get_quiz(callback_data.quiz)
    if quiz is None:
        return await callback.answer("Этот квиз уже удалён", show_alert=True)
    await start_edit(callback, state, Edit.quiz_title, quiz.id)
    await ask(
        callback,
        state,
        f"✏️ <b>Новое название</b>\n\nСейчас: <code>{esc(quiz.title)}</code>\n\n"
        f"<i>Пришли новое — до {TITLE_LIMIT} символов. Нажми на текущее, чтобы скопировать.</i>",
        cancel_markup("cancel"),
    )
    await callback.answer()


@router.message(Edit.quiz_title)
async def edit_title_input(message: Message, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    title = await read_plain(message, TITLE_LIMIT)
    if title is None:
        return
    await wipe(message)
    quiz_id = (await state.get_data())["quiz"]
    await db.update_quiz(quiz_id, title=title)
    await navigate(message, state, db, bot, owners, {"view": "quiz", "quiz": quiz_id}, "✅ Название обновлено")


@router.callback_query(Adm.filter(F.action == "quiz_desc"))
async def edit_description(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database):
    quiz = await db.get_quiz(callback_data.quiz)
    if quiz is None:
        return await callback.answer("Этот квиз уже удалён", show_alert=True)
    await start_edit(callback, state, Edit.quiz_description, quiz.id)
    extra = [("🗑 Убрать описание", Adm(action="quiz_desc_del", quiz=quiz.id))] if quiz.description else []
    await ask(
        callback,
        state,
        "📝 <b>Описание квиза</b>\n\n"
        "Пришли новый текст — его увидят перед стартом. Форматирование сохранится.\n\n"
        f"<i>До {DESCRIPTION_LIMIT} символов.</i>",
        cancel_markup("cancel", extra=extra),
    )
    await callback.answer()


@router.message(Edit.quiz_description)
async def edit_description_input(message: Message, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    description = await read_rich(message, DESCRIPTION_LIMIT)
    if description is None:
        return
    await wipe(message)
    quiz_id = (await state.get_data())["quiz"]
    await db.update_quiz(quiz_id, description=description)
    await navigate(message, state, db, bot, owners, {"view": "quiz", "quiz": quiz_id}, "✅ Описание обновлено")


@router.callback_query(Adm.filter(F.action == "quiz_desc_del"))
async def delete_description(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    await db.update_quiz(callback_data.quiz, description="")
    await navigate(callback, state, db, bot, owners, {"view": "quiz", "quiz": callback_data.quiz}, "🗑 Описание убрано")
    await callback.answer()


@router.callback_query(Adm.filter(F.action == "quiz_cover"))
async def edit_cover(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database):
    quiz = await db.get_quiz(callback_data.quiz)
    if quiz is None:
        return await callback.answer("Этот квиз уже удалён", show_alert=True)
    await start_edit(callback, state, Edit.quiz_cover, quiz.id)
    extra = [("🗑 Убрать обложку", Adm(action="quiz_cover_del", quiz=quiz.id))] if quiz.image else []
    await ask(
        callback,
        state,
        "🖼 <b>Обложка квиза</b>\n\n"
        "Пришли картинку. Она появится на экране старта, в результатах и у вопросов без своей картинки.\n\n"
        "<i>Лучше всего горизонтальная, примерно 16:9.</i>",
        cancel_markup("cancel", extra=extra),
    )
    await callback.answer()


@router.message(Edit.quiz_cover)
async def edit_cover_input(message: Message, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    image = await read_image(message)
    if image is None:
        return
    await wipe(message)
    quiz_id = (await state.get_data())["quiz"]
    await db.update_quiz(quiz_id, image=image)
    await navigate(message, state, db, bot, owners, {"view": "quiz", "quiz": quiz_id}, "✅ Обложка обновлена")


@router.callback_query(Adm.filter(F.action == "quiz_cover_del"))
async def delete_cover(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    await db.update_quiz(callback_data.quiz, image=None)
    await navigate(callback, state, db, bot, owners, {"view": "quiz", "quiz": callback_data.quiz}, "🗑 Обложка убрана")
    await callback.answer()


@router.callback_query(Adm.filter(F.action == "publish"))
async def toggle_publish(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database, bot: Bot):
    quiz = await db.get_quiz(callback_data.quiz)
    if quiz is None:
        return await callback.answer("Этот квиз уже удалён", show_alert=True)
    if not quiz.published and not quiz.questions:
        return await callback.answer("Сначала добавь хотя бы один вопрос — пустой квиз публиковать нельзя", show_alert=True)

    await db.update_quiz(quiz.id, published=int(not quiz.published))
    await show(callback, *await quiz_screen(db, bot, quiz.id), state=state)
    await callback.answer("🟢 Опубликован — квиз уже в меню" if not quiz.published else "⚪️ Скрыт из меню")


@router.callback_query(Adm.filter(F.action == "quiz_del"))
async def delete_quiz_confirm(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database):
    quiz = await db.get_quiz(callback_data.quiz)
    if quiz is None:
        return await callback.answer("Этот квиз уже удалён", show_alert=True)
    summary = await db.quiz_summary(quiz.id)
    await state.clear()
    await show(
        callback,
        f"⚠️ <b>Удалить «{esc(quiz.title)}»?</b>\n\n"
        f"Вместе с ним пропадут {questions_word(quiz.questions)} и вся статистика "
        f"({plural(summary['runs'], ('прохождение', 'прохождения', 'прохождений'))}).\n\n"
        "<b>Это действие нельзя отменить.</b>\n"
        "<i>Если квиз нужно просто убрать из меню — лучше скрой его.</i>",
        confirm_markup(Adm(action="quiz_del_yes", quiz=quiz.id), Adm(action="quiz", quiz=quiz.id)),
        state=state,
    )
    await callback.answer()


@router.callback_query(Adm.filter(F.action == "quiz_del_yes"))
async def delete_quiz(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database):
    quiz = await db.get_quiz(callback_data.quiz)
    if quiz:
        await db.delete_quiz(quiz.id)
    notice = f"🗑 Квиз «{esc(quiz.title)}» удалён" if quiz else ""
    await show(callback, *await quizzes_screen(db, notice), state=state)
    await callback.answer()


@router.callback_query(Adm.filter(F.action == "single"))
async def toggle_single(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database, bot: Bot):
    quiz = await db.get_quiz(callback_data.quiz)
    if quiz is None:
        return await callback.answer("Этот квиз уже удалён", show_alert=True)
    await db.update_quiz(quiz.id, single=int(not quiz.single))
    await show(callback, *await quiz_screen(db, bot, quiz.id), state=state)
    await callback.answer(
        "🔁 Теперь проходить можно сколько угодно раз" if quiz.single else "🔒 Теперь каждый проходит квиз один раз"
    )


@router.callback_query(Adm.filter(F.action == "reset"))
async def reset_confirm(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database):
    quiz = await db.get_quiz(callback_data.quiz)
    if quiz is None:
        return await callback.answer("Этот квиз уже удалён", show_alert=True)
    passed = await db.passed_count(quiz)
    if not passed:
        return await callback.answer("Сбрасывать нечего — с прошлого сброса квиз ещё никто не прошёл", show_alert=True)
    await state.clear()
    await show(
        callback,
        f"♻️ <b>Сбросить прохождения «{esc(quiz.title)}»?</b>\n\n"
        f"Прошли квиз: <b>{plural(passed, ('человек', 'человека', 'человек'))}</b>.\n\n"
        "После сброса все снова смогут пройти его один раз, а незаконченные попытки начнутся с начала.\n\n"
        "<i>Статистика и ответы в CSV сохранятся.</i>",
        confirm_markup(
            Adm(action="reset_yes", quiz=quiz.id),
            Adm(action="quiz", quiz=quiz.id),
            "♻️ Да, сбросить",
        ),
        state=state,
    )
    await callback.answer()


@router.callback_query(Adm.filter(F.action == "reset_yes"))
async def reset(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database, bot: Bot):
    quiz = await db.get_quiz(callback_data.quiz)
    if quiz is None:
        return await callback.answer("Этот квиз уже удалён", show_alert=True)
    await db.reset_quiz(quiz.id)
    await show(callback, *await quiz_screen(db, bot, quiz.id, "♻️ Прохождения сброшены — квиз снова доступен всем"), state=state)
    await callback.answer()
