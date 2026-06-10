from aiogram.filters import BaseFilter
from aiogram.types import Message
from database.db import get_or_create_user
from config import FREE_VIEWS, BOT_FREE_MODE


class VipFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        user = get_or_create_user(message.from_user.id)
        return bool(user["vip"])


class FreeViewsLeft(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        user = get_or_create_user(message.from_user.id)
        return BOT_FREE_MODE or user["views"] < FREE_VIEWS or bool(user["vip"])
