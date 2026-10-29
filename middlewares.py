from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.filters import Filter
from aiogram.types import TelegramObject, User

from database import Database


class UserMiddleware(BaseMiddleware):
    def __init__(self, db: Database, owners: frozenset[int]):
        self.db = db
        self.owners = owners

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        data["is_admin"] = False
        data["is_owner"] = False
        if user and not user.is_bot:
            await self.db.upsert_user(user.id, user.username, user.full_name)
            data["is_owner"] = user.id in self.owners
            data["is_admin"] = data["is_owner"] or await self.db.is_admin(user.id)
        return await handler(event, data)


class IsAdmin(Filter):
    async def __call__(self, event: TelegramObject, is_admin: bool = False) -> bool:
        return is_admin
