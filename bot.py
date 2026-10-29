import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from commands import setup_commands
from config import load_config
from database import Database
from demo import seed_demo
from handlers import common, fallback, user
from handlers.admin import build_router
from middlewares import UserMiddleware

log = logging.getLogger("quizbot")


async def on_error(event: ErrorEvent) -> None:
    log.exception("Ошибка при обработке апдейта", exc_info=event.exception)
    update = event.update
    with suppress(TelegramAPIError):
        if update.callback_query:
            await update.callback_query.answer("Что-то пошло не так 😔 Попробуй ещё раз", show_alert=True)
        elif update.message:
            await update.message.answer("Что-то пошло не так 😔 Нажми /start, чтобы начать заново")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s")
    config = load_config()

    db = Database(config.db_path)
    await db.connect()
    if await seed_demo(db):
        log.info("Добавлены демо-квиз и демо-опрос")

    bot = Bot(
        config.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    dp = Dispatcher(storage=MemoryStorage(), db=db, owners=config.owners)
    dp.update.outer_middleware(UserMiddleware(db, config.owners))
    dp.errors.register(on_error)
    dp.include_routers(common.router, build_router(), user.router, fallback.router)

    admins = set(config.owners) | {row["id"] for row in await db.admins()}
    with suppress(TelegramAPIError):
        await setup_commands(bot, sorted(admins))

    me = await bot.me()
    log.info("Бот @%s запущен", me.username)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        asyncio.run(main())
