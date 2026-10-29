from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from callbacks import Adm
from database import Database
from handlers.admin.forms import ask, navigate, read_image, read_lines, read_rich
from handlers.admin.views import cancel_markup, confirm_markup, question_screen, questions_screen
from handlers.user import normalize
from states import Edit, QuestionForm
from ui import cut, esc, flash, keycap, plain, show, wipe

router = Router(name="admin-questions")

TEXT_LIMIT = 700
OPTION_LIMIT = 60
OPTIONS_MAX = 8
ANSWER_LIMIT = 100
ANSWERS_MAX = 10
EXPLANATION_LIMIT = 300
QUESTIONS_MAX = 50


def heading(data: dict, step: int, name: str) -> str:
    if data.get("edit"):
        return f"🧩 <b>{name}</b>"
    return f"➕ <b>Новый вопрос</b> · шаг {step} из 5\n<b>{name}</b>"


def preview(draft: dict) -> str:
    return f"<blockquote>{esc(cut(plain(draft.get('text', '')), 200))}</blockquote>"


def cancel_row(builder: InlineKeyboardBuilder) -> None:
    builder.button(text="✖️ Отмена", callback_data=Adm(action="cancel"))


async def update_draft(state: FSMContext, **changes) -> dict:
    data = await state.get_data()
    draft = {**data.get("draft", {}), **changes}
    await state.update_data(draft=draft)
    return draft


@router.callback_query(Adm.filter(F.action == "questions"))
async def questions(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database):
    await state.clear()
    screen = await questions_screen(db, callback_data.quiz)
    if screen is None:
        return await callback.answer("Этот квиз уже удалён", show_alert=True)
    await show(callback, *screen, state=state)
    await callback.answer()


@router.callback_query(Adm.filter(F.action == "question"))
async def question_card(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database):
    await state.clear()
    screen = await question_screen(db, callback_data.question)
    if screen is None:
        await callback.answer("Этот вопрос уже удалён")
        screen = await questions_screen(db, callback_data.quiz)
        if screen is None:
            return
    else:
        await callback.answer()
    await show(callback, *screen, state=state)


@router.callback_query(Adm.filter(F.action == "q_new"))
async def new_question(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database):
    quiz = await db.get_quiz(callback_data.quiz)
    if quiz is None:
        return await callback.answer("Этот квиз уже удалён", show_alert=True)
    if quiz.questions >= QUESTIONS_MAX:
        return await callback.answer(f"В квизе уже {QUESTIONS_MAX} вопросов — это максимум", show_alert=True)

    await state.clear()
    await state.set_state(QuestionForm.text)
    await state.update_data(quiz=quiz.id, edit=0, draft={}, back={"view": "questions", "quiz": quiz.id})
    await ask(
        callback,
        state,
        "➕ <b>Новый вопрос</b> · шаг 1 из 5\n<b>Текст вопроса</b>\n\n"
        "Напиши сам вопрос. Жирный, курсив и ссылки сохранятся.\n\n"
        "💡 <i>Можно сразу прислать картинку с подписью — подпись станет вопросом, а картинка — иллюстрацией к нему.</i>\n\n"
        f"<i>До {TEXT_LIMIT} символов.</i>",
        cancel_markup("cancel"),
    )
    await callback.answer()


@router.message(QuestionForm.text)
async def text_input(message: Message, state: FSMContext):
    if (message.photo or message.document) and not message.caption:
        image = await read_image(message)
        if image:
            await update_draft(state, image=image)
            await flash(message, "🖼 Картинку запомнил! Теперь пришли текст вопроса")
        return

    text = await read_rich(message, TEXT_LIMIT)
    if text is None:
        return
    image = await read_image(message) if message.photo or message.document else None
    await wipe(message)
    changes = {"text": text}
    if image:
        changes["image"] = image
    await update_draft(state, **changes)
    await ask_kind(message, state)


async def ask_kind(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(QuestionForm.kind)
    data = await state.get_data()
    draft = data["draft"]
    current = ""
    if data.get("edit"):
        current = "\n\nСейчас: " + ("🔘 варианты ответа" if draft.get("kind") == "choice" else "✍️ ответ текстом")

    builder = InlineKeyboardBuilder()
    builder.button(text="🔘 Варианты ответа", callback_data=Adm(action="kind", value=0))
    builder.button(text="✍️ Ответ текстом", callback_data=Adm(action="kind", value=1))
    cancel_row(builder)
    builder.adjust(1)
    await ask(
        event,
        state,
        f"{heading(data, 2, 'Как будут отвечать?')}\n\n{preview(draft)}\n\n"
        "🔘 <b>Варианты</b> — человек выбирает один из кнопок\n"
        "✍️ <b>Текстом</b> — пишет ответ сам, а бот сверяет его с правильным"
        f"{current}",
        builder.as_markup(),
    )


@router.callback_query(QuestionForm.kind, Adm.filter(F.action == "kind"))
async def kind_chosen(callback: CallbackQuery, callback_data: Adm, state: FSMContext):
    kind = "choice" if callback_data.value == 0 else "text"
    draft = (await state.get_data())["draft"]
    if draft.get("kind") != kind:
        await update_draft(state, kind=kind, options=[], correct=None, answers=[])
    else:
        await update_draft(state, kind=kind)

    if kind == "choice":
        await ask_options(callback, state)
    else:
        await ask_answers(callback, state)
    await callback.answer()


async def ask_options(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(QuestionForm.options)
    data = await state.get_data()
    draft = data["draft"]
    options = draft.get("options", [])

    lines = [
        heading(data, 3, "Варианты ответа"),
        "",
        preview(draft),
        "",
        "Отправь варианты — по одному сообщению или сразу списком, каждый с новой строки.",
        "",
    ]
    if options:
        lines += [f"{keycap(i)} {esc(option)}" for i, option in enumerate(options)]
        lines += ["", f"<i>Добавлено {len(options)} из {OPTIONS_MAX} · до {OPTION_LIMIT} символов в варианте</i>"]
    else:
        lines.append(f"<i>Пока пусто. Нужно от 2 до {OPTIONS_MAX} вариантов, каждый до {OPTION_LIMIT} символов.</i>")

    builder = InlineKeyboardBuilder()
    sizes = []
    if len(options) >= 2:
        builder.button(text="✅ Готово — выбрать верный", callback_data=Adm(action="opt_done"))
        sizes.append(1)
    if options:
        builder.button(text="↩️ Убрать последний", callback_data=Adm(action="opt_undo"))
        builder.button(text="🧹 Очистить", callback_data=Adm(action="opt_clear"))
        sizes.append(2)
    cancel_row(builder)
    builder.adjust(*sizes, 1)
    await ask(event, state, "\n".join(lines), builder.as_markup())


@router.message(QuestionForm.options)
async def options_input(message: Message, state: FSMContext):
    lines = await read_lines(message)
    if lines is None:
        return
    too_long = [line for line in lines if len(line) > OPTION_LIMIT]
    if too_long:
        return await flash(
            message,
            f"✂️ Вариант «{esc(cut(too_long[0], 30))}» длиннее {OPTION_LIMIT} символов. Сократи и пришли ещё раз.",
            delay=6,
        )

    options = list((await state.get_data())["draft"].get("options", []))
    known = {normalize(option) for option in options}
    duplicates = overflow = 0
    for line in lines:
        if normalize(line) in known:
            duplicates += 1
        elif len(options) >= OPTIONS_MAX:
            overflow += 1
        else:
            options.append(line)
            known.add(normalize(line))

    await update_draft(state, options=options)
    await wipe(message)
    await ask_options(message, state)

    if overflow:
        await flash(message, f"Больше {OPTIONS_MAX} вариантов не влезет — лишние не добавил", keep_source=True)
    elif duplicates:
        await flash(message, "Повторы пропустил — такие варианты уже есть", keep_source=True)


@router.callback_query(QuestionForm.options, Adm.filter(F.action == "opt_undo"))
async def options_undo(callback: CallbackQuery, state: FSMContext):
    options = (await state.get_data())["draft"].get("options", [])
    await update_draft(state, options=options[:-1])
    await ask_options(callback, state)
    await callback.answer()


@router.callback_query(QuestionForm.options, Adm.filter(F.action == "opt_clear"))
async def options_clear(callback: CallbackQuery, state: FSMContext):
    await update_draft(state, options=[])
    await ask_options(callback, state)
    await callback.answer()


@router.callback_query(QuestionForm.options, Adm.filter(F.action == "opt_done"))
async def options_done(callback: CallbackQuery, state: FSMContext):
    options = (await state.get_data())["draft"].get("options", [])
    if len(options) < 2:
        return await callback.answer("Нужно хотя бы 2 варианта", show_alert=True)
    await ask_correct(callback, state)
    await callback.answer()


@router.callback_query(QuestionForm.correct, Adm.filter(F.action == "opt_back"))
async def options_back(callback: CallbackQuery, state: FSMContext):
    await ask_options(callback, state)
    await callback.answer()


async def ask_correct(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(QuestionForm.correct)
    data = await state.get_data()
    draft = data["draft"]

    builder = InlineKeyboardBuilder()
    for i, option in enumerate(draft["options"]):
        builder.button(text=f"{keycap(i)} {option}", callback_data=Adm(action="correct", value=i))
    builder.button(text="🗳 Верного нет — это опрос", callback_data=Adm(action="correct", value=-1))
    builder.button(text="↩️ Изменить варианты", callback_data=Adm(action="opt_back"))
    cancel_row(builder)
    builder.adjust(1)
    await ask(
        event,
        state,
        f"{heading(data, 3, 'Правильный ответ')}\n\n{preview(draft)}\n\n"
        "Какой вариант верный? Нажми на него 👇\n\n"
        "<i>Если это вопрос-мнение без правильного ответа — выбери «Верного нет». "
        "Тогда он не повлияет на счёт, а ответы попадут в статистику.</i>",
        builder.as_markup(),
    )


@router.callback_query(QuestionForm.correct, Adm.filter(F.action == "correct"))
async def correct_chosen(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    options = (await state.get_data())["draft"]["options"]
    if callback_data.value >= len(options):
        return await callback.answer("Такого варианта уже нет", show_alert=True)
    await update_draft(state, correct=None if callback_data.value < 0 else callback_data.value, answers=[])
    await callback.answer()
    await after_answers(callback, state, db, bot, owners)


async def ask_answers(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(QuestionForm.answers)
    data = await state.get_data()
    draft = data["draft"]

    current = ""
    if draft.get("answers"):
        current = "\n\nСейчас засчитываются: " + ", ".join(f"<code>{esc(a)}</code>" for a in draft["answers"])

    builder = InlineKeyboardBuilder()
    builder.button(text="🗳 Без проверки — просто собрать ответы", callback_data=Adm(action="no_check"))
    cancel_row(builder)
    builder.adjust(1)
    await ask(
        event,
        state,
        f"{heading(data, 3, 'Правильный ответ')}\n\n{preview(draft)}\n\n"
        "Напиши правильный ответ. Если подходят разные формулировки — пришли их списком, каждую с новой строки.\n\n"
        "<i>Регистр, буква «ё» и знаки препинания не важны: «Гагарин», «гагарин» и «ГАГАРИН!» засчитаются одинаково.</i>"
        f"{current}",
        builder.as_markup(),
    )


@router.message(QuestionForm.answers)
async def answers_input(message: Message, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    lines = await read_lines(message)
    if lines is None:
        return
    too_long = [line for line in lines if len(line) > ANSWER_LIMIT]
    if too_long:
        return await flash(message, f"✂️ Ответ длиннее {ANSWER_LIMIT} символов — так его никто не угадает 🙂", delay=6)

    answers, seen = [], set()
    for line in lines:
        key = normalize(line)
        if key and key not in seen:
            seen.add(key)
            answers.append(line)
    if not answers:
        return await flash(message, "Не нашёл в сообщении ни одного ответа — пришли текстом")

    await wipe(message)
    await update_draft(state, answers=answers[:ANSWERS_MAX], options=[], correct=None)
    if len(answers) > ANSWERS_MAX:
        await flash(message, f"Оставил первые {ANSWERS_MAX} формулировок", keep_source=True)
    await after_answers(message, state, db, bot, owners)


@router.callback_query(QuestionForm.answers, Adm.filter(F.action == "no_check"))
async def answers_skip(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    await update_draft(state, answers=[], options=[], correct=None)
    await callback.answer()
    await after_answers(callback, state, db, bot, owners)


async def after_answers(event: Message | CallbackQuery, state: FSMContext, db: Database, bot: Bot, owners) -> None:
    data = await state.get_data()
    draft = data["draft"]
    if data.get("edit"):
        await db.update_question(
            data["edit"],
            kind=draft["kind"],
            options=draft.get("options", []),
            correct=draft.get("correct"),
            answers=draft.get("answers", []),
        )
        target = {"view": "question", "quiz": data["quiz"], "question": data["edit"]}
        return await navigate(event, state, db, bot, owners, target, "✅ Ответы обновлены")
    if draft.get("image"):
        return await ask_explanation(event, state)
    await ask_image(event, state)


async def ask_image(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(QuestionForm.image)
    data = await state.get_data()
    await ask(
        event,
        state,
        f"{heading(data, 4, 'Картинка')}\n\n{preview(data['draft'])}\n\n"
        "Пришли картинку к вопросу — схему, фото, что угодно.\n\n"
        "<i>Если пропустить, у вопроса будет обложка квиза (если она есть).</i>",
        cancel_markup("cancel", extra=[("⏭ Без картинки", Adm(action="skip"))]),
    )


@router.message(QuestionForm.image)
async def image_input(message: Message, state: FSMContext):
    image = await read_image(message)
    if image is None:
        return
    await wipe(message)
    await update_draft(state, image=image)
    await ask_explanation(message, state)


@router.callback_query(QuestionForm.image, Adm.filter(F.action == "skip"))
async def image_skip(callback: CallbackQuery, state: FSMContext):
    await ask_explanation(callback, state)
    await callback.answer()


async def ask_explanation(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(QuestionForm.explanation)
    data = await state.get_data()
    await ask(
        event,
        state,
        f"{heading(data, 5, 'Пояснение')}\n\n{preview(data['draft'])}\n\n"
        "Что показать человеку после ответа? Интересный факт или пара слов о том, почему ответ именно такой.\n\n"
        f"<i>До {EXPLANATION_LIMIT} символов. Можно пропустить.</i>",
        cancel_markup("cancel", extra=[("⏭ Без пояснения — сохранить", Adm(action="skip"))]),
    )


@router.message(QuestionForm.explanation)
async def explanation_input(message: Message, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    explanation = await read_rich(message, EXPLANATION_LIMIT)
    if explanation is None:
        return
    await wipe(message)
    await update_draft(state, explanation=explanation)
    await save_question(message, state, db, bot, owners)


@router.callback_query(QuestionForm.explanation, Adm.filter(F.action == "skip"))
async def explanation_skip(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    await callback.answer()
    await save_question(callback, state, db, bot, owners)


async def save_question(event: Message | CallbackQuery, state: FSMContext, db: Database, bot: Bot, owners) -> None:
    data = await state.get_data()
    draft = data["draft"]
    if await db.get_quiz(data["quiz"]) is None:
        return await navigate(event, state, db, bot, owners, {"view": "quizzes"}, "⚠️ Квиз удалили, пока ты добавлял вопрос")

    question_id = await db.add_question(
        data["quiz"],
        kind=draft["kind"],
        text=draft["text"],
        image=draft.get("image"),
        options=draft.get("options", []),
        correct=draft.get("correct"),
        answers=draft.get("answers", []),
        explanation=draft.get("explanation", ""),
    )
    target = {"view": "question", "quiz": data["quiz"], "question": question_id}
    await navigate(event, state, db, bot, owners, target, "✅ Вопрос сохранён — вот как он выглядит")


async def load_for_edit(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database, edit_state):
    question = await db.get_question(callback_data.question)
    if question is None:
        await callback.answer("Этот вопрос уже удалён", show_alert=True)
        return None
    await state.clear()
    await state.set_state(edit_state)
    await state.update_data(
        quiz=question.quiz_id,
        edit=question.id,
        back={"view": "question", "quiz": question.quiz_id, "question": question.id},
        draft={
            "text": question.text,
            "kind": question.kind,
            "options": question.options,
            "correct": question.correct,
            "answers": question.answers,
        },
    )
    return question


async def finish_edit(message: Message | CallbackQuery, state: FSMContext, db: Database, bot: Bot, owners, notice: str) -> None:
    data = await state.get_data()
    target = {"view": "question", "quiz": data["quiz"], "question": data["edit"]}
    await navigate(message, state, db, bot, owners, target, notice)


@router.callback_query(Adm.filter(F.action == "q_answers"))
async def edit_answers(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database):
    if await load_for_edit(callback, callback_data, state, db, QuestionForm.kind) is None:
        return
    await ask_kind(callback, state)
    await callback.answer()


@router.callback_query(Adm.filter(F.action == "q_text"))
async def edit_text(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database):
    question = await load_for_edit(callback, callback_data, state, db, Edit.question_text)
    if question is None:
        return
    await ask(
        callback,
        state,
        "✏️ <b>Текст вопроса</b>\n\nСейчас:\n"
        f"{preview({'text': question.text})}\n\n"
        f"Пришли новый текст. Форматирование сохранится.\n\n<i>До {TEXT_LIMIT} символов.</i>",
        cancel_markup("cancel"),
    )
    await callback.answer()


@router.message(Edit.question_text)
async def edit_text_input(message: Message, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    text = await read_rich(message, TEXT_LIMIT)
    if text is None:
        return
    await wipe(message)
    await db.update_question((await state.get_data())["edit"], text=text)
    await finish_edit(message, state, db, bot, owners, "✅ Текст обновлён")


@router.callback_query(Adm.filter(F.action == "q_image"))
async def edit_image(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database):
    question = await load_for_edit(callback, callback_data, state, db, Edit.question_image)
    if question is None:
        return
    extra = [("🗑 Убрать картинку", Adm(action="q_image_del", quiz=question.quiz_id, question=question.id))] if question.image else []
    await ask(
        callback,
        state,
        "🖼 <b>Картинка вопроса</b>\n\nПришли новую картинку.\n\n"
        "<i>Без своей картинки у вопроса будет обложка квиза.</i>",
        cancel_markup("cancel", extra=extra),
    )
    await callback.answer()


@router.message(Edit.question_image)
async def edit_image_input(message: Message, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    image = await read_image(message)
    if image is None:
        return
    await wipe(message)
    await db.update_question((await state.get_data())["edit"], image=image)
    await finish_edit(message, state, db, bot, owners, "✅ Картинка обновлена")


@router.callback_query(Adm.filter(F.action == "q_image_del"))
async def delete_image(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    await db.update_question(callback_data.question, image=None)
    target = {"view": "question", "quiz": callback_data.quiz, "question": callback_data.question}
    await navigate(callback, state, db, bot, owners, target, "🗑 Картинка убрана")
    await callback.answer()


@router.callback_query(Adm.filter(F.action == "q_expl"))
async def edit_explanation(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database):
    question = await load_for_edit(callback, callback_data, state, db, Edit.question_explanation)
    if question is None:
        return
    extra = [("🗑 Убрать пояснение", Adm(action="q_expl_del", quiz=question.quiz_id, question=question.id))] if question.explanation else []
    await ask(
        callback,
        state,
        "💡 <b>Пояснение</b>\n\nЕго покажем сразу после ответа. Пришли новый текст.\n\n"
        f"<i>До {EXPLANATION_LIMIT} символов.</i>",
        cancel_markup("cancel", extra=extra),
    )
    await callback.answer()


@router.message(Edit.question_explanation)
async def edit_explanation_input(message: Message, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    explanation = await read_rich(message, EXPLANATION_LIMIT)
    if explanation is None:
        return
    await wipe(message)
    await db.update_question((await state.get_data())["edit"], explanation=explanation)
    await finish_edit(message, state, db, bot, owners, "✅ Пояснение обновлено")


@router.callback_query(Adm.filter(F.action == "q_expl_del"))
async def delete_explanation(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database, bot: Bot, owners: frozenset[int]):
    await db.update_question(callback_data.question, explanation="")
    target = {"view": "question", "quiz": callback_data.quiz, "question": callback_data.question}
    await navigate(callback, state, db, bot, owners, target, "🗑 Пояснение убрано")
    await callback.answer()


@router.callback_query(Adm.filter(F.action == "q_move"))
async def move(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database):
    moved = await db.move_question(callback_data.question, -1 if callback_data.value == 0 else 1)
    if not moved:
        edge = "первый" if callback_data.value == 0 else "последний"
        return await callback.answer(f"Это и так {edge} вопрос")
    screen = await question_screen(db, callback_data.question)
    if screen:
        await show(callback, *screen, state=state)
    await callback.answer("⬆️ Поднял выше" if callback_data.value == 0 else "⬇️ Опустил ниже")


@router.callback_query(Adm.filter(F.action == "q_del"))
async def delete_confirm(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database):
    question = await db.get_question(callback_data.question)
    if question is None:
        return await callback.answer("Этот вопрос уже удалён", show_alert=True)
    await state.clear()
    await show(
        callback,
        f"⚠️ <b>Удалить вопрос?</b>\n\n{preview({'text': question.text})}\n\n"
        "Ответы на него тоже пропадут из статистики. Отменить это нельзя.",
        confirm_markup(
            Adm(action="q_del_yes", quiz=question.quiz_id, question=question.id),
            Adm(action="question", quiz=question.quiz_id, question=question.id),
        ),
        state=state,
    )
    await callback.answer()


@router.callback_query(Adm.filter(F.action == "q_del_yes"))
async def delete(callback: CallbackQuery, callback_data: Adm, state: FSMContext, db: Database):
    await db.delete_question(callback_data.question)
    quiz = await db.get_quiz(callback_data.quiz)
    notice = "🗑 Вопрос удалён"
    if quiz and quiz.published and not quiz.questions:
        await db.update_quiz(quiz.id, published=0)
        notice += "\n⚪️ Вопросов не осталось, поэтому квиз скрыт из меню"
    screen = await questions_screen(db, callback_data.quiz, notice)
    if screen:
        await show(callback, *screen, state=state)
    await callback.answer()


@router.message(StateFilter(QuestionForm.kind, QuestionForm.correct))
async def buttons_expected(message: Message):
    await flash(message, "👆 Здесь нужно нажать одну из кнопок выше")
