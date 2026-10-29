import re

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database import Database
from handlers.admin.views import screen_for
from ui import ImageError, flash, grab_image, show, visible_len

QUOTES = re.compile(r"</?(?:blockquote|expandable_blockquote)[^>]*>")


async def read_rich(message: Message, limit: int) -> str | None:
    if not (message.text or message.caption):
        await flash(message, "✍️ Здесь нужен текст — просто напиши его сообщением")
        return None
    value = QUOTES.sub("", message.html_text).strip()
    length = visible_len(value)
    if not length:
        await flash(message, "Пустой текст не подойдёт 🙂")
        return None
    if length > limit:
        await flash(message, f"✂️ Слишком длинно: {length} символов при лимите {limit}. Сократи, пожалуйста.", delay=6)
        return None
    return value


async def read_plain(message: Message, limit: int) -> str | None:
    if not message.text:
        await flash(message, "✍️ Здесь нужен текст — просто напиши его сообщением")
        return None
    value = " ".join(message.text.split())
    if not value:
        await flash(message, "Пустой текст не подойдёт 🙂")
        return None
    if len(value) > limit:
        await flash(message, f"✂️ Слишком длинно: {len(value)} символов при лимите {limit}.", delay=6)
        return None
    return value


async def read_lines(message: Message) -> list[str] | None:
    if not message.text:
        await flash(message, "✍️ Пришли текстом — каждый вариант с новой строки")
        return None
    lines = [" ".join(line.split()) for line in message.text.splitlines()]
    lines = [line.lstrip("•-–—*· ").strip() for line in lines]
    return [line for line in lines if line]


async def read_image(message: Message) -> str | None:
    try:
        image = await grab_image(message)
    except ImageError as error:
        await flash(message, f"⚠️ {error}", delay=6)
        return None
    if image is None:
        await flash(message, "🖼 Здесь нужна картинка — пришли фото или файл JPG/PNG")
    return image


async def navigate(
    event: Message | CallbackQuery,
    state: FSMContext,
    db: Database,
    bot: Bot,
    owners: frozenset[int],
    target: dict,
    notice: str = "",
) -> None:
    text, markup, image = await screen_for(db, bot, owners, target, notice)
    await show(event, text, markup, image, state=state)
    await state.set_state(None)
    data = await state.get_data()
    await state.set_data({"panel": data.get("panel")})


async def ask(event: Message | CallbackQuery, state: FSMContext, text: str, markup, image: str | None = None) -> None:
    await show(event, text, markup, image, state=state)
