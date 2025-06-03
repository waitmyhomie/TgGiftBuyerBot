from aiogram import types, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

from api.gifts import GiftsApi
from bot.states.auto_buy_state import AutoBuyStates
from bot.keyboards.default import main_menu, auto_buy_keyboard, go_back_menu
from utils.logger import log
from db.models import AutoBuySettings, User

router = Router()
gifts_api = GiftsApi()


def get_or_create_auto_buy_settings(db, user_id) -> AutoBuySettings:
    """
    Retrieve or create auto-purchase settings for a user.

    Args:
        db: Database session
        user_id: Telegram user ID

    Returns:
        AutoBuySettings: Existing or newly created settings object

    Behavior:
        - Checks if settings exist for the user
        - Creates new settings if none exist
        - Commits changes to database
        - Returns the settings object
    """
    settings = db.query(AutoBuySettings).filter(
        AutoBuySettings.user_id == user_id).first()
    if not settings:
        settings = AutoBuySettings(user_id=user_id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.message(Command(commands=["auto_buy"]))
async def auto_buy_command(message: types.Message, state: FSMContext, db_session):
    """
    Command handler for auto-purchase configuration.
    """
    with db_session as db:
        settings = get_or_create_auto_buy_settings(db, message.from_user.id)
        user = db.query(User).filter(
            User.user_id == message.from_user.id).first()

        username = user.username if user else "Unknown User"
        balance = user.balance if user else 0

        await message.answer(
            text=(
                f"{username}! Your balance: {balance} ⭐️\n\n"
                f"⚙️ <b>Auto-Purchase Settings</b>\n"
                f"Status: {'🟢 Enabled' if settings.status == 'enabled' else '🔴 Disabled'}\n\n"
                f"<b>Price Limit:</b>\n"
                f"From {settings.price_limit_from} to {settings.price_limit_to} ⭐️\n\n"
                f"<b>Supply Limit:</b> {settings.supply_limit or 'not set'} ⭐️\n"
                f"<b>Purchase Cycles:</b> {settings.cycles}\n"
                f"<b>Excluded gifts:</b> 5782984811920491178\n\n"
                f"<i>💡 Покупаются все подарки кроме исключенных</i>"
            ),
            reply_markup=auto_buy_keyboard(),
            parse_mode="HTML"
        )
    await state.set_state(AutoBuyStates.menu)


async def display_updated_settings(message: types.Message, db_session, settings: AutoBuySettings) -> None:
    """
    Display updated auto-purchase settings to user.
    """
    # Исправление DetachedInstanceError - получаем свежие данные пользователя в новой сессии
    with db_session as db:
        user = db.query(User).filter(
            User.user_id == message.from_user.id).first()
        username = user.username if user else "Unknown User"
        balance = user.balance if user else 0

        # Используем переданные settings, но для безопасности можно обновить их
        db.refresh(settings)

        await message.answer(
            text=(
                f"{username}! Your balance: {balance} ⭐️\n\n"
                f"⚙️ <b>Auto-Purchase Settings</b>\n"
                f"Status: {'🟢 Enabled' if settings.status == 'enabled' else '🔴 Disabled'}\n\n"
                f"<b>Price Limit:</b>\n"
                f"From {settings.price_limit_from} to {settings.price_limit_to} ⭐️\n\n"
                f"<b>Supply Limit:</b> {settings.supply_limit or 'not set'} ⭐️\n"
                f"<b>Purchase Cycles:</b> {settings.cycles}\n"
                f"<b>Excluded gifts:</b> 5782984811920491178\n\n"
                f"<i>💡 Покупаются все подарки кроме исключенных</i>"
            ),
            reply_markup=auto_buy_keyboard(),
            parse_mode="HTML"
        )


@router.message(StateFilter(AutoBuyStates.menu))
async def auto_buy_menu_handler(message: types.Message, state: FSMContext, db_session):
    """
    Handle user selection in auto-purchase menu.
    """
    with db_session as db:
        settings = get_or_create_auto_buy_settings(db, message.from_user.id)

        if message.text == "🔄 Toggle On/Off":
            settings.status = "enabled" if settings.status == "disabled" else "disabled"
            db.commit()
            # Исправление - сначала коммитим, потом обновляем объект
            db.refresh(settings)
            await message.answer(
                text=f"🔄 Auto-purchase status changed: {'🟢 Enabled' if settings.status == 'enabled' else '🔴 Disabled'}."
            )
            # Передаем db_session вместо db, чтобы создать новую сессию в display_updated_settings
            await display_updated_settings(message, db_session, settings)

        elif message.text == "✏️ Price Limit":
            await message.answer(
                text="Enter price limit in format: `FROM TO` (e.g., 10 100).\nPress '🔙 Back to Main Menu' to cancel.",
                reply_markup=go_back_menu(),
                parse_mode="HTML"
            )
            await state.set_state(AutoBuyStates.set_price)

        elif message.text == "✏️ Supply Limit":
            await message.answer(
                text="Enter gift quantity limit (e.g., 50).\nPress '🔙 Back to Main Menu' to cancel.",
                reply_markup=go_back_menu(),
                parse_mode="HTML"
            )
            await state.set_state(AutoBuyStates.set_supply)

        elif message.text == "✏️ Number of Cycles":
            await message.answer(
                text=(
                    "<b>Enter number of cycles (e.g., 2)</b>\n"
                    "Каждый цикл - это полный проход по всем новым подаркам.\n"
                    "Если после первого цикла появятся новые подарки или останется баланс, "
                    "бот сделает еще один проход.\n\n"
                    "Рекомендуется: 1-3 цикла\n"
                    "Press '🔙 Back to Main Menu' to cancel."
                ),
                reply_markup=go_back_menu(),
                parse_mode="HTML"
            )
            await state.set_state(AutoBuyStates.set_cycles)

        elif message.text == "🔙 Back to Main Menu":
            await message.answer(
                text="Returned to main menu!",
                reply_markup=main_menu()
            )
            await state.clear()


@router.message(StateFilter(AutoBuyStates.set_price))
async def auto_buy_set_price_handler(message: types.Message, state: FSMContext, db_session):
    """
    Handle price limit configuration.
    """
    with db_session as db:
        settings = get_or_create_auto_buy_settings(db, message.from_user.id)

        if message.text == "🔙 Back to Main Menu":
            await message.answer(
                text="Returned to main menu!",
                reply_markup=main_menu()
            )
            await state.clear()
            return

        try:
            price_limits = message.text.split()
            if len(price_limits) != 2:
                raise ValueError("Input format must be: `FROM TO`.")
            price_from, price_to = map(int, price_limits)
            settings.price_limit_from = price_from
            settings.price_limit_to = price_to
            db.commit()
            db.refresh(settings)

            await message.answer(
                text=f"✅ Price limit set: from {price_from} to {price_to} ⭐️."
            )
            await display_updated_settings(message, db_session, settings)
            await state.set_state(AutoBuyStates.menu)
        except ValueError:
            await message.answer(
                text="Input error! Enter price limit in format: `FROM TO` (e.g., 10 100).",
                reply_markup=go_back_menu()
            )


@router.message(StateFilter(AutoBuyStates.set_supply))
async def auto_buy_set_supply_handler(message: types.Message, state: FSMContext, db_session):
    """
    Handle supply limit configuration.
    """
    with db_session as db:
        settings = get_or_create_auto_buy_settings(db, message.from_user.id)

        if message.text == "🔙 Back to Main Menu":
            await message.answer(
                text="Returned to main menu!",
                reply_markup=main_menu()
            )
            await state.clear()
            return

        try:
            supply_limit = int(message.text)
            if supply_limit <= 0:
                raise ValueError("Supply limit must be a positive number.")
            settings.supply_limit = supply_limit
            db.commit()
            db.refresh(settings)

            await message.answer(
                text=f"✅ Supply limit set: {supply_limit}."
            )
            await display_updated_settings(message, db_session, settings)
            await state.set_state(AutoBuyStates.menu)
        except ValueError:
            await message.answer(
                text="Input error! Enter a positive number for supply limit.",
                reply_markup=go_back_menu()
            )


@router.message(StateFilter(AutoBuyStates.set_cycles))
async def auto_buy_set_cycles_handler(message: types.Message, state: FSMContext, db_session):
    """
    Handle purchase cycles configuration.
    """
    with db_session as db:
        settings = get_or_create_auto_buy_settings(db, message.from_user.id)

        if message.text == "🔙 Back to Main Menu":
            await message.answer(
                text="Returned to main menu!",
                reply_markup=main_menu()
            )
            await state.clear()
            return

        try:
            cycles = int(message.text)
            if cycles <= 0:
                raise ValueError("Number of cycles must be positive.")
            settings.cycles = cycles
            db.commit()
            db.refresh(settings)

            await message.answer(
                text=f"✅ Number of purchase cycles set: {cycles}."
            )
            await display_updated_settings(message, db_session, settings)
            await state.set_state(AutoBuyStates.menu)
        except ValueError:
            await message.answer(
                text="Input error! Enter a positive number for cycles.",
                reply_markup=go_back_menu()
            )