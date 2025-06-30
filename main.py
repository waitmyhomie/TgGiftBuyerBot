# ПРАВИЛЬНЫЙ main.py с работающей защитой

import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import load_config
from bot.handlers import register_handlers
from bot.middlewares.db_session_middleware import DBSessionMiddleware
from bot.middlewares.owner_only_middleware import OwnerOnlyMiddleware  # ВАЖНО!
from db import init_db
from utils.logger import log
from utils.gift_parser import start_gift_parsing_loop

# Load configuration
config = load_config()

# Initialize bot
bot = Bot(token=config["bot_token"])
dp = Dispatcher(storage=MemoryStorage())


async def on_startup():
    """
    Actions to perform when the bot starts
    """
    log.info("Initializing database...")
    init_db()
    log.info("Database initialized successfully")
    
    # ВАЖНО: Логируем режим работы
    log.info("🔐 Bot configured for OWNER ONLY mode")
    log.info("🔐 Owner ID: 1487757625")
    log.info("🔐 All other users will be BLOCKED!")
    
    # Запускаем парсер подарков
    log.info("Starting gift parsing loop...")
    asyncio.create_task(start_gift_parsing_loop())


async def main():
    """
    Main entry point for starting the bot
    """
    log.info("Starting bot in PRIVATE mode...")
    os.makedirs('logs', exist_ok=True)

    await on_startup()

    # КРИТИЧЕСКИ ВАЖНО: Правильный порядок middleware!
    # 1. Сначала OwnerOnlyMiddleware - проверяет доступ
    # 2. Потом DBSessionMiddleware - дает доступ к БД
    
    # Регистрируем middleware для ВСЕХ типов обновлений
    dp.message.middleware(OwnerOnlyMiddleware())
    dp.callback_query.middleware(OwnerOnlyMiddleware())
    dp.inline_query.middleware(OwnerOnlyMiddleware())
    dp.pre_checkout_query.middleware(OwnerOnlyMiddleware())
    
    # DBSessionMiddleware регистрируем после
    dp.update.middleware(DBSessionMiddleware())

    # Register handlers
    register_handlers(dp)

    # Start polling
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        log.exception(f"Bot stopped due to an error: {e}")