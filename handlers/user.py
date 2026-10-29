import random
import re

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, User
from aiogram.utils.keyboard import InlineKeyboardBuilder

from callbacks import Flow, Nav, Open, Pick
from database import Attempt, Database, Question, Quiz
from ui import (
    bar,
    close_enough,
    cut,
    drop,
    esc,
    flash,
    keycap,
    percent,
    plural,
    questions_word,
    render,
    show,
    wipe,
)

router = Router(name="user")

DEFAULT_WELCOME = (
    "👋 Привет, <b>{name}</b>!\n\n"
    "Здесь живут квизы и опросы. Выбирай тему, отвечай на вопросы "
    "и смотри, насколько хорошо в ней разбираешься.\n\n"
    "Поехали? Жми на квиз ниже 👇"
)

PRAISE = ("Верно!", "Точно!", "В яблочко!", "Именно так!", "Так держать!")
MISS = ("Мимо.", "Не совсем.", "Увы, нет.", "Почти, но нет.")

GRADES = (
    (1.0, "🏆", "Идеально! Ни одной ошибки."),
    (0.8, "🔥", "Отличный результат — ты явно в теме."),
    (0.5, "👍", "Хорошо! Ещё чуть-чуть — и будет идеально."),
    (0.0, "🌱", "Не беда — зато теперь ты знаешь больше 😉"),
)

LONG_OPTION = 28


def normalize(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def grade(share: float) -> tuple[str, str]:
    for threshold, icon, verdict in GRADES:
        if share >= threshold:
            return icon, verdict
    return GRADES[-1][1:]


def share_of(attempt: Attempt) -> float:
    return attempt.correct / attempt.scored if attempt.scored else 0.0


def best_of(attempts: list[Attempt]) -> Attempt | None:
    if not attempts:
        return None
    return max(attempts, key=lambda a: (share_of(a), a.correct, a.finished_at or 0))


def single_column(builder: InlineKeyboardBuilder) -> InlineKeyboardMarkup:
    builder.adjust(1)
    return builder.as_markup()


async def home_screen(db: Database, user: User, is_admin: bool) -> tuple[str, InlineKeyboardMarkup, str | None]:
    welcome = await db.get_setting("welcome_text") or DEFAULT_WELCOME
    text = welcome.replace("{name}", esc(user.first_name))

    quizzes = [quiz for quiz in await db.quizzes(published_only=True) if quiz.questions]
    builder = InlineKeyboardBuilder()
    for quiz in quizzes:
        label = f"{quiz.title} · {questions_word(quiz.questions)}"
        done = best_of(await db.passed(user.id, quiz)) if quiz.single else None
        if done:
            label = f"✅ {quiz.title}" + (f" · {done.correct}/{done.scored}" if done.scored else "")
        builder.button(text=label, callback_data=Open(action="view", id=quiz.id))
    if not quizzes:
        text += "\n\n<i>Пока здесь пусто — новые квизы скоро появятся.</i>"

    builder.button(text="🏅 Мои результаты", callback_data=Nav(to="results"))
    if is_admin:
        builder.button(text="⚙️ Админ-панель", callback_data=Nav(to="admin"))
    return text, single_column(builder), await db.get_setting("welcome_image")


def locked(quiz: Quiz, passed: list[Attempt], is_admin: bool) -> bool:
    return quiz.single and bool(passed) and not is_admin


def score_line(attempt: Attempt) -> str:
    return f"<b>{attempt.correct} из {attempt.scored}</b> · {percent(share_of(attempt))}"


async def intro_screen(
    db: Database, quiz: Quiz, user_id: int, is_admin: bool = False
) -> tuple[str, InlineKeyboardMarkup, str | None]:
    lines = [f"<b>{esc(quiz.title)}</b>"]
    if quiz.description:
        lines += ["", quiz.description]

    minutes = max(1, round(quiz.questions * 20 / 60))
    lines += ["", f"📋 {questions_word(quiz.questions)} · ⏱ около {plural(minutes, ('минуты', 'минут', 'минут'))}"]

    finished = await db.finished_attempts(user_id, quiz.id)
    passed = await db.passed(user_id, quiz) if quiz.single else []
    best = best_of(passed or finished)

    if passed:
        lines += ["", "✅ <b>Ты уже прошёл этот квиз</b>"]
        if best.scored:
            lines.append(f"Твой результат: {score_line(best)}")
        if is_admin:
            lines.append("🔓 <i>Ты админ — можешь пройти ещё раз для проверки</i>")
        else:
            lines.append("<i>Его можно пройти только один раз.</i>")
    elif quiz.single:
        lines.append("🔒 Пройти можно только один раз")
        if best and best.scored:
            lines.append(f"🏅 В прошлый раз: {score_line(best)}")
    elif best and best.scored:
        lines.append(f"🏅 Твой рекорд: {score_line(best)}")
    elif best:
        lines.append("✔️ Ты уже проходил его — можно ещё раз")

    if not quiz.published:
        lines += ["", "👁 <i>Черновик — его видят только админы</i>"]

    active = await db.active_attempt(user_id, quiz.id)
    builder = InlineKeyboardBuilder()
    if active:
        lines += ["", f"⏸ Ты остановился на вопросе {active.position + 1} из {len(active.sequence)}"]
        builder.button(text="▶️ Продолжить", callback_data=Open(action="resume", id=quiz.id))
        if not quiz.single or is_admin:
            builder.button(text="🔄 Заново", callback_data=Open(action="start", id=quiz.id))
        builder.button(text="← Ко всем квизам", callback_data=Nav(to="home"))
        builder.adjust(2 if not quiz.single or is_admin else 1, 1)
    else:
        if not locked(quiz, passed, is_admin):
            builder.button(
                text="🔄 Пройти ещё раз" if finished and not (quiz.single and not passed) else "🚀 Начать",
                callback_data=Open(action="start", id=quiz.id),
            )
        builder.button(text="← Ко всем квизам", callback_data=Nav(to="home"))
        builder.adjust(1)
    return "\n".join(lines), builder.as_markup(), quiz.image


def header(attempt: Attempt) -> str:
    number = attempt.position + 1
    total = max(len(attempt.sequence), number)
    return f"<b>Вопрос {number}</b> из {total}\n{bar(number / total)}"


def question_screen(attempt: Attempt, question: Question) -> tuple[str, InlineKeyboardMarkup]:
    lines = [header(attempt), "", question.text]
    builder = InlineKeyboardBuilder()

    if question.is_choice:
        count = len(question.options)
        detailed = any(len(option) > LONG_OPTION for option in question.options)
        if detailed:
            lines.append("")
            lines += [f"{keycap(i)} {esc(option)}" for i, option in enumerate(question.options)]
        for i, option in enumerate(question.options):
            builder.button(
                text=keycap(i) if detailed else f"{keycap(i)} {option}",
                callback_data=Pick(attempt=attempt.id, question=question.id, option=i),
            )
        if detailed:
            per_row = -(-count // -(-count // 4))
            rows = [per_row] * (count // per_row) + ([count % per_row] if count % per_row else [])
        else:
            rows = [1] * count
    else:
        lines += ["", "✍️ <i>Напиши ответ одним сообщением</i>"]
        builder.button(text="⏭ Пропустить", callback_data=Flow(action="skip", attempt=attempt.id, position=attempt.position))
        rows = [1]

    builder.button(text="✖️ Выйти", callback_data=Flow(action="stop", attempt=attempt.id))
    builder.adjust(*rows, 1, 1)
    return "\n".join(lines), builder.as_markup()


def feedback_screen(attempt: Attempt, question: Question, response) -> tuple[str, InlineKeyboardMarkup]:
    lines = [header(attempt), "", question.text, ""]
    is_correct = response["is_correct"]
    chosen = response["option"]

    if question.is_choice:
        for i, option in enumerate(question.options):
            if question.correct is None:
                mark = "🔘" if i == chosen else "▫️"
            elif i == question.correct:
                mark = "✅"
            elif i == chosen:
                mark = "❌"
            else:
                mark = "▫️"
            text = f"<b>{esc(option)}</b>" if i in (chosen, question.correct) else esc(option)
            lines.append(f"{mark} {text}")
        lines.append("")
    elif response["answer"]:
        lines += [f"Твой ответ: <i>{esc(cut(response['answer'], 200))}</i>", ""]

    luck = random.Random(f"{attempt.id}:{question.id}")
    skipped = not question.is_choice and not response["answer"]
    if skipped and is_correct is None:
        lines.append("⏭ <b>Пропущено</b>")
    elif skipped:
        lines.append(f"⏭ <b>Пропущено.</b> Правильный ответ — <b>{esc(question.right_answer)}</b>")
    elif is_correct is None:
        lines.append("📝 <b>Ответ записан, спасибо!</b>")
    elif is_correct:
        lines.append(f"✅ <b>{luck.choice(PRAISE)}</b>")
    else:
        lines.append(f"❌ <b>{luck.choice(MISS)}</b> Правильный ответ — <b>{esc(question.right_answer)}</b>")

    if question.explanation:
        lines += ["", f"<blockquote>💡 {question.explanation}</blockquote>"]

    last = attempt.position + 1 >= len(attempt.sequence)
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🏁 Узнать результат" if last else "Дальше →",
        callback_data=Flow(action="next", attempt=attempt.id, position=attempt.position),
    )
    return "\n".join(lines), builder.as_markup()


async def result_screen(
    db: Database, quiz: Quiz, attempt: Attempt, is_admin: bool = False
) -> tuple[str, InlineKeyboardMarkup, str | None]:
    lines = ["🏁 <b>Готово!</b>", esc(quiz.title), ""]

    if attempt.scored:
        share = share_of(attempt)
        icon, verdict = grade(share)
        lines += [
            f"Правильных ответов: <b>{attempt.correct} из {attempt.scored}</b>",
            f"{bar(share)} {percent(share)}",
            "",
            f"{icon} {verdict}",
        ]
        history = [a for a in await db.finished_attempts(attempt.user_id, quiz.id) if a.id != attempt.id and a.scored]
        record = best_of(history)
        if record and share_of(record) > share:
            lines += ["", f"🏅 Твой рекорд: {record.correct} из {record.scored}"]
        elif record and share > share_of(record):
            lines += ["", "🎉 Это новый личный рекорд!"]
    else:
        lines += ["🙏 <b>Спасибо за ответы!</b>", "Мы всё записали — это правда помогает делать бота лучше."]

    builder = InlineKeyboardBuilder()
    if quiz.single and not is_admin:
        lines += ["", "🔒 <i>Этот квиз проходится один раз — результат засчитан.</i>"]
    else:
        builder.button(text="🔄 Пройти ещё раз", callback_data=Open(action="start", id=quiz.id))
    builder.button(text="🏠 В меню", callback_data=Nav(to="home"))
    builder.adjust(2)
    return "\n".join(lines), builder.as_markup(), quiz.image


async def results_screen(db: Database, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    attempts = await db.finished_attempts(user_id)
    grouped: dict[int, list[Attempt]] = {}
    for attempt in attempts:
        grouped.setdefault(attempt.quiz_id, []).append(attempt)

    blocks = []
    for quiz in await db.quizzes():
        runs = grouped.get(quiz.id)
        if not runs:
            continue
        best = best_of(runs)
        tries = plural(len(runs), ("попытка", "попытки", "попыток"))
        if best.scored:
            share = share_of(best)
            blocks.append(
                f"<b>{esc(quiz.title)}</b>\n{bar(share)} {best.correct}/{best.scored} · {percent(share)}\n<i>{tries}</i>"
            )
        else:
            blocks.append(f"<b>{esc(quiz.title)}</b>\n✔️ пройден · <i>{tries}</i>")

    text = "🏅 <b>Мои результаты</b>\n\n"
    text += "\n\n".join(blocks) if blocks else "Здесь пока пусто. Пройди любой квиз — и результат появится тут 😉"

    builder = InlineKeyboardBuilder()
    builder.button(text="← В меню", callback_data=Nav(to="home"))
    return text, builder.as_markup()


async def present(
    bot: Bot, db: Database, chat_id: int, attempt: Attempt, message_id: int | None, is_admin: bool = False
) -> None:
    quiz = await db.get_quiz(attempt.quiz_id)
    if quiz is None:
        return

    while True:
        question_id = attempt.current
        if question_id is None:
            await db.finish_attempt(attempt.id)
            attempt = await db.get_attempt(attempt.id)
            text, markup, image = await result_screen(db, quiz, attempt, is_admin)
            await render(bot, chat_id, text, markup, image, message_id)
            return
        question = await db.get_question(question_id)
        if question and question.quiz_id == quiz.id:
            break
        await db.advance(attempt.id, attempt.position)
        attempt.position += 1
        attempt.stage = "question"

    response = await db.response(attempt.id, question.id) if attempt.stage == "feedback" else None
    if response:
        text, markup = feedback_screen(attempt, question, response)
    else:
        text, markup = question_screen(attempt, question)

    new_id = await render(bot, chat_id, text, markup, question.image or quiz.image, message_id)
    await db.set_attempt_message(attempt.id, new_id)


async def owned_attempt(callback: CallbackQuery, db: Database, attempt_id: int, is_admin: bool) -> Attempt | None:
    attempt = await db.get_attempt(attempt_id)
    if attempt and attempt.user_id == callback.from_user.id and attempt.active:
        return attempt
    if attempt is None:
        await callback.answer("Этот квиз больше недоступен", show_alert=True)
        await show_home(callback, db, is_admin)
    else:
        await callback.answer("Этот вопрос уже позади 🙂")
    return None


async def show_home(event: Message | CallbackQuery, db: Database, is_admin: bool, fresh: bool = False) -> None:
    text, markup, image = await home_screen(db, event.from_user, is_admin)
    await show(event, text, markup, image, fresh=fresh)


async def open_quiz(event: Message | CallbackQuery, db: Database, quiz_id: int, is_admin: bool, fresh: bool = False) -> bool:
    quiz = await db.get_quiz(quiz_id)
    if quiz is None or (not quiz.published and not is_admin):
        return False
    text, markup, image = await intro_screen(db, quiz, event.from_user.id, is_admin)
    await show(event, text, markup, image, fresh=fresh)
    return True


@router.callback_query(Nav.filter(F.to == "home"))
async def nav_home(callback: CallbackQuery, db: Database, is_admin: bool):
    await show_home(callback, db, is_admin)
    await callback.answer()


@router.callback_query(Nav.filter(F.to == "results"))
async def nav_results(callback: CallbackQuery, db: Database):
    text, markup = await results_screen(db, callback.from_user.id)
    await show(callback, text, markup)
    await callback.answer()


@router.callback_query(Open.filter(F.action == "view"))
async def view_quiz(callback: CallbackQuery, callback_data: Open, db: Database, is_admin: bool):
    if await open_quiz(callback, db, callback_data.id, is_admin):
        return await callback.answer()
    await callback.answer("Этот квиз сейчас недоступен", show_alert=True)
    await show_home(callback, db, is_admin)


@router.callback_query(Open.filter(F.action.in_({"start", "resume"})))
async def start_quiz(callback: CallbackQuery, callback_data: Open, db: Database, bot: Bot, is_admin: bool):
    quiz = await db.get_quiz(callback_data.id)
    if quiz is None or (not quiz.published and not is_admin):
        await callback.answer("Этот квиз сейчас недоступен", show_alert=True)
        return await show_home(callback, db, is_admin)

    user_id = callback.from_user.id
    strict = quiz.single and not is_admin
    if strict and await db.passed(user_id, quiz):
        await callback.answer("Этот квиз можно пройти только один раз 🔒", show_alert=True)
        return await open_quiz(callback, db, quiz.id, is_admin)

    attempt = None
    if callback_data.action == "resume" or strict:
        attempt = await db.active_attempt(user_id, quiz.id)
    if attempt is None:
        questions = await db.questions(quiz.id)
        if not questions:
            return await callback.answer("В этом квизе пока нет вопросов", show_alert=True)
        attempt = await db.start_attempt(user_id, quiz, [q.id for q in questions])

    await callback.answer()
    await present(bot, db, callback.message.chat.id, attempt, callback.message.message_id, is_admin)


@router.callback_query(Pick.filter())
async def pick_option(callback: CallbackQuery, callback_data: Pick, db: Database, bot: Bot, is_admin: bool):
    attempt = await owned_attempt(callback, db, callback_data.attempt, is_admin)
    if attempt is None:
        return
    if attempt.stage != "question" or attempt.current != callback_data.question:
        return await callback.answer("Этот вопрос уже позади 🙂")

    question = await db.get_question(callback_data.question)
    if question is None or not question.is_choice or not 0 <= callback_data.option < len(question.options):
        await callback.answer("Вопрос только что обновили — показываю свежую версию")
        return await present(bot, db, callback.message.chat.id, attempt, callback.message.message_id, is_admin)

    if not await db.claim(attempt.id, attempt.position):
        return await callback.answer()

    is_correct = None if question.correct is None else callback_data.option == question.correct
    await db.save_response(attempt, question, question.options[callback_data.option], callback_data.option, is_correct)
    await callback.answer()

    attempt.stage = "feedback"
    await present(bot, db, callback.message.chat.id, attempt, callback.message.message_id, is_admin)


@router.callback_query(Flow.filter(F.action == "skip"))
async def skip_question(callback: CallbackQuery, callback_data: Flow, db: Database, bot: Bot, is_admin: bool):
    attempt = await owned_attempt(callback, db, callback_data.attempt, is_admin)
    if attempt is None:
        return
    question = await db.get_question(attempt.current) if attempt.current else None
    if question is None or attempt.position != callback_data.position or not await db.claim(attempt.id, attempt.position):
        return await callback.answer("Этот вопрос уже позади 🙂")

    await db.save_response(attempt, question, "", None, False if question.scored else None)
    await callback.answer()
    attempt.stage = "feedback"
    await present(bot, db, callback.message.chat.id, attempt, callback.message.message_id, is_admin)


@router.callback_query(Flow.filter(F.action == "next"))
async def next_question(callback: CallbackQuery, callback_data: Flow, db: Database, bot: Bot, is_admin: bool):
    attempt = await owned_attempt(callback, db, callback_data.attempt, is_admin)
    if attempt is None:
        return
    if attempt.stage != "feedback" or not await db.advance(attempt.id, callback_data.position):
        return await callback.answer()

    await callback.answer()
    attempt = await db.get_attempt(attempt.id)
    await present(bot, db, callback.message.chat.id, attempt, callback.message.message_id, is_admin)


@router.callback_query(Flow.filter(F.action == "stop"))
async def stop_quiz(callback: CallbackQuery, callback_data: Flow, db: Database, is_admin: bool):
    attempt = await db.get_attempt(callback_data.attempt)
    if attempt and await open_quiz(callback, db, attempt.quiz_id, is_admin):
        return await callback.answer("Прогресс сохранён — можно вернуться в любой момент")
    await callback.answer()
    await show_home(callback, db, is_admin)


async def answer_text(
    message: Message, db: Database, bot: Bot, attempt: Attempt, question: Question, is_admin: bool
) -> None:
    answer = cut(message.text.strip(), 300)
    if not answer:
        return await flash(message, "Пустой ответ не засчитать 🙂 Напиши что-нибудь")
    if not await db.claim(attempt.id, attempt.position):
        return await wipe(message)

    is_correct = None
    if question.answers:
        is_correct = normalize(answer) in {normalize(variant) for variant in question.answers}
    await db.save_response(attempt, question, answer, None, is_correct)

    anchor = attempt.message_id if close_enough(attempt.message_id, message.message_id) else None
    if anchor is None:
        await drop(bot, message.chat.id, attempt.message_id)
    await wipe(message)

    attempt.stage = "feedback"
    await present(bot, db, message.chat.id, attempt, anchor, is_admin)


@router.message(StateFilter(None), F.chat.type == "private")
async def any_message(message: Message, db: Database, bot: Bot, is_admin: bool):
    attempt = await db.active_attempt(message.from_user.id)

    if attempt and attempt.stage == "question" and attempt.current:
        question = await db.get_question(attempt.current)
        if question and not question.is_choice:
            if message.text and not message.text.startswith("/"):
                return await answer_text(message, db, bot, attempt, question, is_admin)
            return await flash(message, "✍️ Ответ нужен текстом — просто напиши его сообщением")

    if attempt and close_enough(attempt.message_id, message.message_id):
        hint = "👆 Выбери вариант кнопкой под вопросом" if attempt.stage == "question" else "👆 Жми «Дальше» под вопросом"
        return await flash(message, hint)

    if attempt:
        await drop(bot, message.chat.id, attempt.message_id)
        await wipe(message)
        return await present(bot, db, message.chat.id, attempt, None, is_admin)

    if message.text and message.text.startswith("/"):
        return await flash(message, "Такой команды нет 🤔 Нажми /start, чтобы открыть меню", keep_source=True)

    await show_home(message, db, is_admin, fresh=True)
