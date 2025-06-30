# bot/middlewares/owner_only_middleware.py
"""
Middleware для блокировки всех пользователей кроме владельца
Исправлено для aiogram 3.x
"""

from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from utils.logger import log

# ВАШ TELEGRAM ID - ТОЛЬКО ВЫ МОЖЕТЕ ИСПОЛЬЗОВАТЬ БОТА
OWNER_ID = 1487757625


class OwnerOnlyMiddleware(BaseMiddleware):
    """
    Блокирует доступ всем кроме владельца
    """
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Получаем пользователя из разных типов событий
        user = None
        
        # Для сообщений
        if isinstance(event, Message):
            user = event.from_user
            
        # Для callback запросов  
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            
        # Для других типов событий пробуем получить из data
        elif 'event_from_user' in data:
            user = data['event_from_user']
            
        # Если нашли пользователя - проверяем доступ
        if user:
            if user.id != OWNER_ID:
                # ЛОГИРУЕМ ПОПЫТКУ ДОСТУПА
                log.warning(
                    f"🚫 BLOCKED ACCESS ATTEMPT:\n"
                    f"   User ID: {user.id}\n"
                    f"   Username: {user.username or 'No username'}\n"
                    f"   Full name: {user.full_name}\n"
                    f"   Event type: {type(event).__name__}"
                )
                
                # Отвечаем пользователю
                if isinstance(event, Message):
                    await event.answer(
                        "🚫 Access Denied\n\n"
                        "This bot is private and only available to the owner.\n"
                        "Your access attempt has been logged."
                    )
                    return  # Блокируем обработку
                    
                elif isinstance(event, CallbackQuery):
                    await event.answer(
                        "🚫 Access denied. Private bot.",
                        show_alert=True
                    )
                    return  # Блокируем обработку
                    
                # Для остальных типов просто блокируем
                return
        
        # Если это владелец или не удалось определить пользователя - пропускаем
        return await handler(event, data)