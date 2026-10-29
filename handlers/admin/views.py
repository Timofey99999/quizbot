from datetime import datetime

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from callbacks import Adm, Nav, Open
from database import Database, Question
from handlers.user import DEFAULT_WELCOME
from ui import bar, cut, esc, keycap, percent, plain, plural

Screen = tuple[str, InlineKeyboardMarkup, str | None]

KIND_ICON = {"choice": "🔘", "text": "✍️"}


def back(action: str, quiz: int = 0, question: int = 0, label: str = "← Назад") -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text=label, callback_data=Adm(action=action, quiz=quiz, question=question))
    return builder


def cancel_markup(action: str, quiz: int = 0, question: int = 0, extra: list[tuple[str, Adm]] | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for text, data in extra or []:
        builder.button(text=text, callback_data=data)
    builder.button(text="✖️ Отмена", callback_data=Adm(action="cancel", quiz=quiz, question=question, value=0))
    builder.adjust(1)
    return builder.as_markup()


def with_notice(notice: str, text: str) -> str:
    return f"{notice}\n\n{text}" if notice else text


async def admin_home(db: Database, notice: str = "") -> Screen:
    stats = await db.overview()
    text = "\n".join(
        [
            "⚙️ <b>Админ-панель</b>",
            "",
            f"👥 Пользователей: <b>{stats['users']}</b>",
            f"🧩 Квизов: <b>{stats['quizzes']}</b> · опубликовано <b>{stats['published']}</b>",
            f"🏁 Прохождений: <b>{stats['finished']}</b> · сегодня <b>{stats['today']}</b>",
            "",
            "<i>Выбери раздел 👇</i>",
        ]
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="🧩 Квизы и опросы", callback_data=Adm(action="quizzes"))
    builder.button(text="🎨 Оформление", callback_data=Adm(action="settings"))
    builder.button(text="👥 Админы", callback_data=Adm(action="admins"))
    builder.button(text="🏠 Выйти в меню", callback_data=Nav(to="home"))
    builder.adjust(1, 2, 1)
    return with_notice(notice, text), builder.as_markup(), None


async def quizzes_screen(db: Database, notice: str = "") -> Screen:
    quizzes = await db.quizzes()
    lines = ["🧩 <b>Квизы и опросы</b>", ""]
    if quizzes:
        lines.append("🟢 опубликован · ⚪️ черновик — его видят только админы")
    else:
        lines.append("Пока ни одного квиза. Создай первый — это займёт пару минут ✨")

    builder = InlineKeyboardBuilder()
    for quiz in quizzes:
        dot = "🟢" if quiz.published else "⚪️"
        builder.button(
            text=f"{dot} {cut(quiz.title, 40)} · {quiz.questions}",
            callback_data=Adm(action="quiz", quiz=quiz.id),
        )
    builder.button(text="➕ Создать квиз", callback_data=Adm(action="quiz_new"))
    builder.button(text="← Назад", callback_data=Adm(action="home"))
    builder.adjust(1)
    return with_notice(notice, "\n".join(lines)), builder.as_markup(), None


async def quiz_screen(db: Database, bot: Bot, quiz_id: int, notice: str = "") -> Screen | None:
    quiz = await db.get_quiz(quiz_id)
    if quiz is None:
        return None
    summary = await db.quiz_summary(quiz.id)
    passed = await db.passed_count(quiz)
    me = await bot.me()

    lines = [f"🧩 <b>{esc(quiz.title)}</b>"]
    if quiz.description:
        lines += ["", quiz.description]
    lines += [
        "",
        f"Статус: {'🟢 опубликован' if quiz.published else '⚪️ черновик'}",
        f"Вопросов: <b>{quiz.questions}</b> · прохождений: <b>{summary['runs']}</b>",
        f"Попытки: {'🔒 одна на человека' if quiz.single else '🔁 без ограничений'}",
    ]
    if quiz.single:
        lines.append(f"Уже прошли: <b>{plural(passed, ('человек', 'человека', 'человек'))}</b>")
    lines += [
        f"Обложка: {'есть' if quiz.image else 'нет'}",
        "",
        f"🔗 Прямая ссылка:\nhttps://t.me/{me.username}?start=q{quiz.id}",
    ]
    if not quiz.questions:
        lines += ["", "💡 <i>Добавь вопросы, а потом опубликуй квиз — тогда его увидят все.</i>"]

    builder = InlineKeyboardBuilder()
    builder.button(text=f"📋 Вопросы ({quiz.questions})", callback_data=Adm(action="questions", quiz=quiz.id))
    builder.button(text="✏️ Название", callback_data=Adm(action="quiz_title", quiz=quiz.id))
    builder.button(text="📝 Описание", callback_data=Adm(action="quiz_desc", quiz=quiz.id))
    builder.button(text="🖼 Обложка", callback_data=Adm(action="quiz_cover", quiz=quiz.id))
    builder.button(text="▶️ Пройти", callback_data=Open(action="view", id=quiz.id))
    builder.button(text="📊 Статистика", callback_data=Adm(action="stats", quiz=quiz.id))
    builder.button(text="📥 Ответы в CSV", callback_data=Adm(action="export", quiz=quiz.id))
    builder.button(
        text="🔒 Одна попытка" if quiz.single else "🔁 Без ограничений",
        callback_data=Adm(action="single", quiz=quiz.id),
    )
    builder.button(text="♻️ Сбросить прохождения", callback_data=Adm(action="reset", quiz=quiz.id))
    builder.button(
        text="⚪️ Скрыть" if quiz.published else "🟢 Опубликовать",
        callback_data=Adm(action="publish", quiz=quiz.id),
    )
    builder.button(text="🗑 Удалить", callback_data=Adm(action="quiz_del", quiz=quiz.id))
    builder.button(text="← К списку квизов", callback_data=Adm(action="quizzes"))
    builder.adjust(1, 2, 2, 2, 2, 2, 1)
    return with_notice(notice, "\n".join(lines)), builder.as_markup(), quiz.image


async def questions_screen(db: Database, quiz_id: int, notice: str = "") -> Screen | None:
    quiz = await db.get_quiz(quiz_id)
    if quiz is None:
        return None
    questions = await db.questions(quiz.id)

    lines = [f"📋 <b>Вопросы</b> · {esc(quiz.title)}", ""]
    if questions:
        lines.append("🔘 — выбор из вариантов · ✍️ — ответ текстом")
        lines.append("<i>Нажми на вопрос, чтобы изменить его, поменять местами или удалить.</i>")
    else:
        lines.append("Здесь пока пусто. Добавь первый вопрос 👇")

    builder = InlineKeyboardBuilder()
    for number, question in enumerate(questions, 1):
        builder.button(
            text=f"{number}. {KIND_ICON[question.kind]} {cut(plain(question.text), 45)}",
            callback_data=Adm(action="question", quiz=quiz.id, question=question.id),
        )
    if len(questions) < 50:
        builder.button(text="➕ Добавить вопрос", callback_data=Adm(action="q_new", quiz=quiz.id))
    builder.button(text="← К квизу", callback_data=Adm(action="quiz", quiz=quiz.id))
    builder.adjust(1)
    return with_notice(notice, "\n".join(lines)), builder.as_markup(), None


def answers_block(question: Question) -> list[str]:
    if question.is_choice:
        lines = []
        for i, option in enumerate(question.options):
            mark = " ✅" if i == question.correct else ""
            lines.append(f"{keycap(i)} {esc(option)}{mark}")
        if question.correct is None:
            lines.append("<i>Без правильного ответа — просто собираем мнения</i>")
        return lines
    if question.answers:
        return ["Засчитываются ответы:"] + [f"• <code>{esc(answer)}</code>" for answer in question.answers]
    return ["<i>Свободный ответ без проверки — просто собираем ответы</i>"]


async def question_screen(db: Database, question_id: int, notice: str = "") -> Screen | None:
    question = await db.get_question(question_id)
    if question is None:
        return None
    quiz = await db.get_quiz(question.quiz_id)
    questions = await db.questions(question.quiz_id)
    number = next(i for i, q in enumerate(questions, 1) if q.id == question.id)

    kind = "🔘 варианты ответа" if question.is_choice else "✍️ ответ текстом"
    lines = [f"<b>Вопрос {number}</b> из {len(questions)} · {kind}", "", question.text, ""]
    lines += answers_block(question)
    if question.explanation:
        lines += ["", f"<blockquote>💡 {question.explanation}</blockquote>"]
    lines += ["", f"🖼 {'своя картинка' if question.image else 'картинки нет — покажется обложка квиза' if quiz.image else 'без картинки'}"]

    q, z = question.id, question.quiz_id
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Текст", callback_data=Adm(action="q_text", quiz=z, question=q))
    builder.button(text="🧩 Ответы", callback_data=Adm(action="q_answers", quiz=z, question=q))
    builder.button(text="🖼 Картинка", callback_data=Adm(action="q_image", quiz=z, question=q))
    builder.button(text="💡 Пояснение", callback_data=Adm(action="q_expl", quiz=z, question=q))
    builder.button(text="⬆️ Выше", callback_data=Adm(action="q_move", quiz=z, question=q, value=0))
    builder.button(text="⬇️ Ниже", callback_data=Adm(action="q_move", quiz=z, question=q, value=1))
    builder.button(text="🗑 Удалить вопрос", callback_data=Adm(action="q_del", quiz=z, question=q))
    builder.button(text="← К вопросам", callback_data=Adm(action="questions", quiz=z))
    builder.adjust(2, 2, 2, 1, 1)
    return with_notice(notice, "\n".join(lines)), builder.as_markup(), question.image or quiz.image


async def stats_screen(db: Database, quiz_id: int) -> Screen | None:
    quiz = await db.get_quiz(quiz_id)
    if quiz is None:
        return None
    summary = await db.quiz_summary(quiz.id)
    breakdown = await db.question_breakdown(quiz.id)
    questions = await db.questions(quiz.id)

    lines = [
        f"📊 <b>Статистика</b> · {esc(quiz.title)}",
        "",
        f"🏁 Прохождений: <b>{summary['runs']}</b> · участников: <b>{summary['people']}</b>",
    ]
    if summary["average"] is not None:
        lines.append(f"🎯 Средний результат: <b>{percent(summary['average'])}</b>")

    for number, question in enumerate(questions, 1):
        item = breakdown.get(question.id)
        lines += ["", f"<b>{number}.</b> {esc(cut(plain(question.text), 70))}"]
        if not item:
            lines.append("<i>ещё нет ответов</i>")
            continue
        if question.is_choice:
            for i, option in enumerate(question.options):
                amount = item["options"].get(i, 0)
                share = amount / item["total"]
                mark = "✅ " if i == question.correct else ""
                lines.append(f"{bar(share, 8)} {percent(share)} · {mark}{esc(cut(option, 30))} ({amount})")
        elif item["checked"]:
            share = item["right"] / item["checked"]
            lines.append(f"{bar(share, 8)} {percent(share)} ответили верно · всего {item['total']}")
        else:
            lines.append(f"✍️ {plural(item['total'], ('ответ', 'ответа', 'ответов'))} — все тексты в CSV")

    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3900].rsplit("\n", 1)[0] + "\n\n<i>…полная картина — в CSV</i>"

    builder = InlineKeyboardBuilder()
    builder.button(text="📥 Скачать CSV", callback_data=Adm(action="export", quiz=quiz.id))
    builder.button(text="🔄 Обновить", callback_data=Adm(action="stats", quiz=quiz.id))
    builder.button(text="← К квизу", callback_data=Adm(action="quiz", quiz=quiz.id))
    builder.adjust(2, 1)
    return text, builder.as_markup(), None


async def settings_screen(db: Database, notice: str = "") -> Screen:
    welcome = await db.get_setting("welcome_text") or DEFAULT_WELCOME
    image = await db.get_setting("welcome_image")
    lines = [
        "🎨 <b>Оформление</b>",
        "",
        "Так выглядит приветствие, которое видит пользователь при /start:",
        "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈",
        welcome.replace("{name}", "Имя"),
        "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈",
        f"🖼 Картинка: {'есть' if image else 'нет'}",
    ]
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Текст приветствия", callback_data=Adm(action="welcome_text"))
    builder.button(text="🖼 Картинка", callback_data=Adm(action="welcome_image"))
    if await db.get_setting("welcome_text"):
        builder.button(text="♻️ Вернуть стандартный текст", callback_data=Adm(action="welcome_reset"))
    builder.button(text="← Назад", callback_data=Adm(action="home"))
    builder.adjust(2, 1, 1)
    return with_notice(notice, "\n".join(lines)), builder.as_markup(), image


def person(user_id: int, username: str | None, name: str | None) -> str:
    title = esc(name) if name else "ещё не заходил в бота"
    handle = f" · @{esc(username)}" if username else ""
    return f"{title}{handle} · <code>{user_id}</code>"


async def admins_screen(db: Database, owners: frozenset[int], notice: str = "") -> Screen:
    lines = ["👥 <b>Админы</b>", ""]
    for owner in sorted(owners):
        user = await db.get_user(owner)
        lines.append(f"👑 {person(owner, user['username'] if user else None, user['name'] if user else None)}")

    builder = InlineKeyboardBuilder()
    admins = [row for row in await db.admins() if row["id"] not in owners]
    for row in admins:
        since = datetime.fromtimestamp(row["created_at"]).strftime("%d.%m.%Y")
        lines.append(f"👤 {person(row['id'], row['username'], row['name'])} · с {since}")
        builder.button(
            text=f"✖️ {cut(row['name'] or str(row['id']), 30)}",
            callback_data=Adm(action="admin_del", value=row["id"]),
        )

    lines += [
        "",
        "👑 — владельцы из файла .env, их нельзя снять из панели.",
        "Нажми ✖️ рядом с именем, чтобы забрать доступ.",
    ]
    builder.button(text="➕ Выдать доступ", callback_data=Adm(action="admin_add"))
    builder.button(text="← Назад", callback_data=Adm(action="home"))
    builder.adjust(1)
    return with_notice(notice, "\n".join(lines)), builder.as_markup(), None


def confirm_markup(yes: Adm, no: Adm, yes_text: str = "🗑 Да, удалить") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=yes_text, callback_data=yes)
    builder.button(text="← Нет, оставить", callback_data=no)
    builder.adjust(1)
    return builder.as_markup()


async def screen_for(db: Database, bot: Bot, owners: frozenset[int], target: dict, notice: str = "") -> Screen:
    view = target.get("view", "home")
    quiz = target.get("quiz", 0)
    question = target.get("question", 0)

    result = None
    if view == "quiz":
        result = await quiz_screen(db, bot, quiz, notice)
    elif view == "questions":
        result = await questions_screen(db, quiz, notice)
    elif view == "question":
        result = await question_screen(db, question, notice) or await questions_screen(db, quiz, notice)
    elif view == "settings":
        result = await settings_screen(db, notice)
    elif view == "admins":
        result = await admins_screen(db, owners, notice)
    elif view == "quizzes":
        result = await quizzes_screen(db, notice)
    return result or await admin_home(db, notice)
