import asyncio
import html
import re
from contextlib import suppress

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

from config import ASSETS_DIR

CAPTION_LIMIT = 1000
KEYCAPS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
TAGS = re.compile(r"<[^>]+>")

_uploaded: dict[str, str] = {}
_background: set[asyncio.Task] = set()


class ImageError(Exception):
    pass


def esc(text: str | None) -> str:
    return html.escape(text or "", quote=False)


def plain(text: str) -> str:
    return html.unescape(TAGS.sub("", text or "")).strip()


def visible_len(text: str) -> int:
    return len(plain(text))


def cut(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def bar(share: float, width: int = 10) -> str:
    share = max(0.0, min(1.0, share))
    filled = round(share * width)
    return "▰" * filled + "▱" * (width - filled)


def percent(share: float) -> str:
    return f"{round(share * 100)}%"


def plural(n: int, forms: tuple[str, str, str]) -> str:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        word = forms[0]
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        word = forms[1]
    else:
        word = forms[2]
    return f"{n} {word}"


def questions_word(n: int) -> str:
    return plural(n, ("вопрос", "вопроса", "вопросов"))


def keycap(index: int) -> str:
    return KEYCAPS[index] if index < len(KEYCAPS) else f"{index + 1}."


def media(image: str | None):
    if not image:
        return None
    if image.startswith("asset:"):
        name = image.removeprefix("asset:")
        if name in _uploaded:
            return _uploaded[name]
        path = ASSETS_DIR / name
        return FSInputFile(path) if path.exists() else None
    return image


def remember(image: str | None, sent) -> None:
    if image and image.startswith("asset:") and isinstance(sent, Message) and sent.photo:
        _uploaded[image.removeprefix("asset:")] = sent.photo[-1].file_id


async def render(
    bot: Bot,
    chat_id: int,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
    image: str | None = None,
    message_id: int | None = None,
) -> int:
    photo = media(image)
    if photo is not None and visible_len(text) > CAPTION_LIMIT:
        photo = None

    if message_id:
        try:
            if photo is not None:
                sent = await bot.edit_message_media(
                    chat_id=chat_id,
                    message_id=message_id,
                    media=InputMediaPhoto(media=photo, caption=text),
                    reply_markup=markup,
                )
                remember(image, sent)
            else:
                await bot.edit_message_text(text=text, chat_id=chat_id, message_id=message_id, reply_markup=markup)
            return message_id
        except TelegramBadRequest as error:
            if "not modified" in error.message:
                if photo is not None:
                    with suppress(TelegramBadRequest):
                        await bot.edit_message_caption(
                            chat_id=chat_id, message_id=message_id, caption=text, reply_markup=markup
                        )
                return message_id
        with suppress(TelegramAPIError):
            await bot.delete_message(chat_id, message_id)

    if photo is not None:
        try:
            sent = await bot.send_photo(chat_id, photo, caption=text, reply_markup=markup)
            remember(image, sent)
            return sent.message_id
        except TelegramBadRequest:
            pass
    sent = await bot.send_message(chat_id, text, reply_markup=markup)
    return sent.message_id


def close_enough(anchor: int | None, message_id: int, gap: int = 5) -> bool:
    return bool(anchor) and 0 < message_id - anchor <= gap


async def show(
    event: Message | CallbackQuery,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
    image: str | None = None,
    *,
    state: FSMContext | None = None,
    fresh: bool = False,
) -> int:
    if isinstance(event, CallbackQuery):
        chat_id = event.from_user.id if event.message is None else event.message.chat.id
        anchor = None if fresh or event.message is None else event.message.message_id
    else:
        chat_id = event.chat.id
        anchor = None
        if state is not None and not fresh:
            panel = (await state.get_data()).get("panel")
            if close_enough(panel, event.message_id):
                anchor = panel
            elif panel:
                await drop(event.bot, chat_id, panel)

    message_id = await render(event.bot, chat_id, text, markup, image, anchor)
    if state is not None:
        await state.update_data(panel=message_id)
    return message_id


async def drop(bot: Bot, chat_id: int, message_id: int | None) -> None:
    if message_id:
        with suppress(TelegramAPIError):
            await bot.delete_message(chat_id, message_id)


async def wipe(message: Message) -> None:
    with suppress(TelegramAPIError):
        await message.delete()


def later(coro) -> None:
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


async def _remove_after(message: Message, delay: float) -> None:
    await asyncio.sleep(delay)
    await wipe(message)


async def flash(message: Message, text: str, delay: float = 4.0, keep_source: bool = False) -> None:
    if not keep_source:
        await wipe(message)
    sent = await message.answer(text)
    later(_remove_after(sent, delay))


async def grab_image(message: Message) -> str | None:
    if message.photo:
        return message.photo[-1].file_id

    document = message.document
    if document is None or not (document.mime_type or "").startswith("image/"):
        return None
    if document.file_size and document.file_size > 10 * 1024 * 1024:
        raise ImageError("Картинка тяжелее 10 МБ — Telegram такую не примет. Сожми её или пришли фото обычным способом.")

    try:
        buffer = await message.bot.download(document)
        sent = await message.bot.send_photo(
            message.chat.id,
            BufferedInputFile(buffer.read(), filename=document.file_name or "image.jpg"),
            disable_notification=True,
        )
    except TelegramAPIError:
        raise ImageError("Не получилось открыть этот файл. Пришли картинку в формате JPG или PNG.")

    await wipe(sent)
    return sent.photo[-1].file_id
