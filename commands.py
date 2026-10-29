from contextlib import suppress

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

USER_COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="help", description="Как пользоваться ботом"),
    BotCommand(command="id", description="Узнать свой Telegram ID"),
]

ADMIN_COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="admin", description="Админ-панель"),
    BotCommand(command="cancel", description="Отменить действие"),
    BotCommand(command="id", description="Узнать свой Telegram ID"),
]


async def grant_commands(bot: Bot, user_id: int) -> None:
    with suppress(TelegramAPIError):
        await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=user_id))


async def revoke_commands(bot: Bot, user_id: int) -> None:
    with suppress(TelegramAPIError):
        await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=user_id))


async def setup_commands(bot: Bot, admin_ids: list[int]) -> None:
    await bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeDefault())
    for user_id in admin_ids:
        await grant_commands(bot, user_id)
