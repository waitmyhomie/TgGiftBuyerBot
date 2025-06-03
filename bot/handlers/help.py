# bot/handlers/help.py

from aiogram import types, Router
from aiogram.filters import Command
from db.models import User

router = Router()


@router.message(Command(commands=["help"]))
async def help_command(message: types.Message, db_session):
    """
    Handles the /help command to provide user assistance.
    Shows different commands based on user status.
    """
    help_text = "🤖 **Gift Auto Buyer Bot Help**\n\n"
    
    # Basic commands for all users
    help_text += "**Basic Commands:**\n"
    help_text += "/start - Start the bot\n"
    help_text += "/balance - Check your balance\n"
    help_text += "/deposit - Add funds to your account\n"
    help_text += "/buy_gift - Buy limited gifts\n"
    help_text += "/buy_gift_all - View all gifts\n"
    help_text += "/auto_buy - Configure auto-purchase\n"
    help_text += "/gift_stats - View gift statistics\n"
    help_text += "/transactions - View your transactions\n"
    help_text += "/help - Show this help message\n"
    
    # Check if user is admin
    with db_session as db:
        user = db.query(User).filter(
            User.user_id == message.from_user.id
        ).first()
        
        if user and user.status == "admin":
            help_text += "\n**Admin Commands:**\n"
            help_text += "/transfer <user_id> <amount> - Transfer stars to user\n"
            help_text += "/refund <transaction_id> - Refund transaction by ID\n"
            help_text += "/transactions <user_id> - View user's transactions\n"
            help_text += "/find_transaction <payment_id or amount> - Find transactions\n"
            help_text += "/admins - List all administrators\n"
            help_text += "/give_admin <user_id> - Grant admin rights (owner only)\n"
            help_text += "/check_autobuy - Debug autobuy status\n"
            help_text += "/debug_gifts - Export gifts data\n"
            help_text += "/raw_api - View raw API response\n"
    
    help_text += "\n**Support:** @neverbeentoxic"
    
    await message.reply(help_text, parse_mode="Markdown")