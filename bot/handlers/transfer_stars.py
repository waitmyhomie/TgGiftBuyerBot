# bot/handlers/transfer_stars.py

from aiogram import types, Router
from aiogram.filters import Command, CommandObject
from datetime import datetime

from utils.logger import log
from db.models import User, Transaction

router = Router()

# ⚠️ ВАЖНО: Замените на ваш Telegram ID
# Узнать свой ID можно у @userinfobot
OWNER_ID = 1487757625   # <-- ИЗМЕНИТЕ ЭТО!


@router.message(Command(commands=["transfer"]))
async def transfer_stars_command(message: types.Message, command: CommandObject, db_session):
    """
    Transfer stars from bot to user.
    Admin only command.
    
    Usage: /transfer <user_id> <amount>
    Example: /transfer 123456789 100
    """
    try:
        # Проверяем права администратора
        with db_session as db:
            admin_user = db.query(User).filter(
                User.user_id == message.from_user.id
            ).first()
            
            if not admin_user or admin_user.status != "admin":
                await message.reply("❌ You don't have permission to use this command.")
                return
        
        # Парсим аргументы команды
        if not command.args:
            await message.reply(
                "❌ Please specify user ID and amount.\n"
                "Usage: /transfer <user_id> <amount>\n"
                "Example: /transfer 123456789 100"
            )
            return
        
        args = command.args.split()
        if len(args) != 2:
            await message.reply(
                "❌ Invalid format.\n"
                "Usage: /transfer <user_id> <amount>"
            )
            return
        
        try:
            target_user_id = int(args[0])
            amount = int(args[1])
            
            if amount <= 0:
                await message.reply("❌ Amount must be positive.")
                return
                
        except ValueError:
            await message.reply("❌ User ID and amount must be numbers.")
            return
        
        # Выполняем перевод
        with db_session as db:
            # Находим пользователя
            target_user = db.query(User).filter(
                User.user_id == target_user_id
            ).first()
            
            if not target_user:
                await message.reply(f"❌ User with ID {target_user_id} not found.")
                return
            
            # Увеличиваем баланс пользователя
            old_balance = target_user.balance
            target_user.balance += amount
            
            # Создаем транзакцию
            transaction = Transaction(
                user_id=target_user_id,
                amount=amount,
                telegram_payment_charge_id=f"admin_transfer_{message.from_user.id}_{datetime.now().timestamp()}",
                status="completed",
                time=datetime.now().isoformat(),
                payload=f"admin_transfer_from_{message.from_user.id}"
            )
            db.add(transaction)
            db.commit()
            
            # Отправляем подтверждение
            await message.reply(
                f"✅ Successfully transferred {amount}⭐ to user ID: {target_user_id}\n"
                f"• Username: {target_user.username}\n"
                f"• Old balance: {old_balance}⭐\n"
                f"• New balance: {target_user.balance}⭐"
            )
            
            # Уведомляем пользователя о получении звезд
            try:
                await message.bot.send_message(
                    target_user_id,
                    f"🎁 You received {amount}⭐ from administrator!\n"
                    f"Your new balance: {target_user.balance}⭐"
                )
            except Exception as e:
                log.warning(f"Could not notify user {target_user_id}: {e}")
                await message.reply(
                    "⚠️ Transfer successful, but could not notify the user."
                )
                
    except Exception as e:
        log.error(f"Error in transfer_stars_command: {e}")
        await message.reply(f"❌ Error: {str(e)}")


@router.message(Command(commands=["give_admin"]))
async def give_admin_command(message: types.Message, command: CommandObject, db_session):
    """
    Give admin rights to a user.
    Only owner can use this command.
    
    Usage: /give_admin <user_id>
    """
    if message.from_user.id != OWNER_ID:
        await message.reply("❌ Only bot owner can use this command.")
        return
    
    if not command.args:
        await message.reply(
            "❌ Please specify user ID.\n"
            "Usage: /give_admin <user_id>"
        )
        return
    
    try:
        target_user_id = int(command.args)
    except ValueError:
        await message.reply("❌ User ID must be a number.")
        return
    
    with db_session as db:
        user = db.query(User).filter(User.user_id == target_user_id).first()
        
        if not user:
            await message.reply(f"❌ User with ID {target_user_id} not found.")
            return
        
        if user.status == "admin":
            await message.reply(f"ℹ️ User ID {target_user_id} is already an admin.")
            return
        
        user.status = "admin"
        db.commit()
        
        await message.reply(
            f"✅ Successfully granted admin rights to user ID: {target_user_id}\n"
            f"Username: {user.username}"
        )
        
        # Уведомляем пользователя
        try:
            await message.bot.send_message(
                target_user_id,
                "🎉 You have been granted administrator privileges!"
            )
        except:
            pass


@router.message(Command(commands=["admins"]))
async def list_admins_command(message: types.Message, db_session):
    """
    List all administrators.
    Admin only command.
    """
    with db_session as db:
        # Проверяем права
        user = db.query(User).filter(
            User.user_id == message.from_user.id
        ).first()
        
        if not user or user.status != "admin":
            await message.reply("❌ You don't have permission to use this command.")
            return
        
        # Получаем список админов
        admins = db.query(User).filter(User.status == "admin").all()
        
        if not admins:
            await message.reply("📋 No administrators found.")
            return
        
        admin_list = "👥 Administrators:\n\n"
        for admin in admins:
            # Используем ID вместо username для избежания проблем с форматированием
            admin_list += f"• ID: {admin.user_id} (@{admin.username})\n"
        
        await message.reply(admin_list)