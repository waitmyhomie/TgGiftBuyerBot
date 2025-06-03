from aiogram import Dispatcher

from .start import router as start_router
from .help import router as help_router
from .buy_gift import router as buy_gift_router
from .balance import router as balance_router
from .payment_handler import router as payment_router
from .auto_buy import router as auto_buy_router
from .debug_gifts import router as debug_gifts_router
from .transfer_stars import router as transfer_stars_router
from .refund import router as refund_router  # Новый роутер для возвратов


def register_handlers(dp: Dispatcher):
    dp.include_router(start_router)
    dp.include_router(help_router)
    dp.include_router(buy_gift_router)
    dp.include_router(balance_router)
    dp.include_router(payment_router)
    dp.include_router(auto_buy_router)
    dp.include_router(debug_gifts_router)
    dp.include_router(transfer_stars_router)
    dp.include_router(refund_router)  # Регистрируем новый роутер