from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update
from typing import Callable, Dict, Any, Awaitable
from utils.logger import log

# ВАШ ID - ТОЛЬКО ВЫ МОЖЕТЕ ИСПОЛЬЗОВАТЬ БОТА
OWNER_ID = 1487757625

class OwnerOnlyMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        
        user_id = None
        
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None
        
        # Блокируем всех кроме владельца
        if user_id and user_id != OWNER_ID:
            log.warning(f"🚫 Blocked access from user_id: {user_id}")
            
            if isinstance(event, Message):
                await event.answer("🚫 This bot is private. Access denied.")
            elif isinstance(event, CallbackQuery):
                await event.answer("🚫 Access denied.", show_alert=True)
            
            return  # Останавливаем обработку
        
        return await handler(event, data)