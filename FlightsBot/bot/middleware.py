"""
Rate limiting middleware — max 8 requests per 10 seconds per user.
"""
import time
from collections import defaultdict
from typing import Callable, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, requests: int = 8, window: int = 10):
        self.requests = requests
        self.window = window
        self._buckets: dict[int, list[float]] = defaultdict(list)

    def _get_user_id(self, event: TelegramObject) -> int | None:
        if isinstance(event, (Message, CallbackQuery)):
            return event.from_user.id if event.from_user else None
        return None

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        uid = self._get_user_id(event)
        if uid is None:
            return await handler(event, data)

        now = time.time()
        bucket = self._buckets[uid]
        # Remove old timestamps outside window
        self._buckets[uid] = [t for t in bucket if now - t < self.window]

        if len(self._buckets[uid]) >= self.requests:
            if isinstance(event, CallbackQuery):
                await event.answer("⏳ Слишком много запросов. Подожди секунду.", show_alert=False)
            elif isinstance(event, Message):
                await event.answer("⏳ Слишком много запросов. Подожди секунду.")
            return

        self._buckets[uid].append(now)
        return await handler(event, data)
