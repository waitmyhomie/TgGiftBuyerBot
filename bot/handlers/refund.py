# bot/handlers/refund.py
# Этот модуль обрабатывает возврат звезд пользователям по ID транзакции

from aiogram import types, Router
from aiogram.filters import Command, CommandObject
from datetime import datetime

from utils.logger import log
from db.models import User, Transaction
from aiogram.methods import RefundStarPayment

router = Router()


@router.message(Command(commands=["refund"]))
async def refund_stars_command(message: types.Message, command: CommandObject, db_session):
    """
    Возврат звезд пользователю по ID транзакции.
    Только для администраторов.
    
    Использование: /refund <transaction_id>
    Пример: /refund 123
    
    Процесс:
    1. Проверяет права администратора
    2. Находит транзакцию по ID
    3. Проверяет, что транзакция не была уже возвращена
    4. Возвращает звезды через Telegram API (для депозитов) или на баланс (для покупок)
    5. Создает запись о возврате
    """
    try:
        # Проверяем права администратора
        with db_session as db:
            admin_user = db.query(User).filter(
                User.user_id == message.from_user.id
            ).first()
            
            if not admin_user or admin_user.status != "admin":
                await message.reply("❌ У вас нет прав для выполнения этой команды.")
                return
        
        # Проверяем наличие ID транзакции
        if not command.args:
            await message.reply(
                "❌ Укажите ID транзакции для возврата.\n"
                "Использование: /refund <transaction_id>\n"
                "Пример: /refund 123"
            )
            return
        
        try:
            transaction_id = int(command.args.strip())
        except ValueError:
            await message.reply("❌ ID транзакции должен быть числом.")
            return
        
        # Выполняем возврат
        with db_session as db:
            # Находим транзакцию
            transaction = db.query(Transaction).filter(
                Transaction.id == transaction_id
            ).first()
            
            if not transaction:
                await message.reply(f"❌ Транзакция с ID {transaction_id} не найдена.")
                return
            
            # Проверяем статус транзакции
            if transaction.status == "refunded":
                await message.reply(
                    f"⚠️ Транзакция #{transaction_id} уже была возвращена ранее."
                )
                return
            
            # Проверяем, что это не транзакция возврата
            if transaction.payload and "refund" in transaction.payload.lower():
                await message.reply(
                    f"❌ Транзакция #{transaction_id} является транзакцией возврата. "
                    "Нельзя сделать возврат возврата."
                )
                return
            
            # Находим пользователя
            user = db.query(User).filter(
                User.user_id == transaction.user_id
            ).first()
            
            if not user:
                await message.reply(
                    f"❌ Пользователь с ID {transaction.user_id} не найден в базе данных."
                )
                return
            
            # Определяем сумму возврата
            refund_amount = abs(transaction.amount)  # Берем абсолютное значение

            # Сохраняем старые значения для отчета
            old_balance = user.balance
            old_transaction_status = transaction.status

            # ИСПРАВЛЕНИЕ: Обрабатываем возврат правильно
            refund_success = False
            refund_method = "Telegram API"
            
            # Проверяем тип транзакции
            is_deposit = transaction.payload and "deposit" in transaction.payload.lower()
            is_purchase = transaction.amount < 0  # Покупки имеют отрицательную сумму
            
            try:
                # Пробуем вернуть через Telegram API (только для депозитов)
                if is_deposit:
                    await message.bot(RefundStarPayment(
                        user_id=user.user_id,
                        telegram_payment_charge_id=transaction.telegram_payment_charge_id
                    ))
                    # При успешном возврате через API уменьшаем баланс
                    user.balance -= refund_amount
                    refund_success = True
                    log.info(f"✅ Refund via Telegram API successful for transaction {transaction_id}")
                else:
                    # Для покупок просто возвращаем на внутренний баланс
                    user.balance += refund_amount
                    refund_success = True
                    refund_method = "Internal balance"
                    log.info(f"✅ Purchase refunded to internal balance for transaction {transaction_id}")
                    
            except Exception as e:
                log.error(f"❌ Failed to refund via Telegram API for transaction {transaction_id}: {e}")
                
                # FALLBACK: Если не удалось через API, НЕ меняем баланс для депозитов
                # (так как звезды не вернулись пользователю)
                if is_deposit:
                    refund_success = False
                    await message.reply(
                        "❌ Не удалось выполнить возврат через Telegram. "
                        "Возможно, прошло слишком много времени с момента платежа. "
                        "Обратитесь к разработчику."
                    )
                    return

            if not refund_success:
                await message.reply("❌ Не удалось выполнить возврат. Обратитесь к разработчику.")
                return

            # Меняем статус транзакции
            transaction.status = "refunded"

            # Создаем новую транзакцию для записи возврата
            # Для депозитов - отрицательная сумма (т.к. уменьшаем баланс)
            # Для покупок - положительная (т.к. увеличиваем баланс)
            if refund_method == "Telegram API":
                refund_transaction_amount = -refund_amount  # Отрицательная для депозитов
            else:
                refund_transaction_amount = refund_amount   # Положительная для покупок
                
            refund_transaction = Transaction(
                user_id=user.user_id,
                amount=refund_transaction_amount,
                telegram_payment_charge_id=f"refund_{transaction_id}_{datetime.now().timestamp()}",
                status="completed",
                time=datetime.now().isoformat(),
                payload=f"refund_for_transaction_{transaction_id}_by_admin_{admin_user.user_id}_method_{refund_method.replace(' ', '_')}"
            )
            db.add(refund_transaction)
            
            # Сохраняем изменения
            db.commit()
            db.refresh(refund_transaction)
            
            # Формируем отчет
            report = (
                f"✅ Возврат успешно выполнен!\n\n"
                f"📋 **Детали возврата:**\n"
                f"• ID транзакции: #{transaction_id}\n"
                f"• Сумма возврата: {refund_amount}⭐\n"
                f"• Получатель: {user.username} (ID: {user.user_id})\n"
                f"• Метод возврата: {refund_method}\n"
                f"• Старый баланс: {old_balance}⭐\n"
                f"• Новый баланс: {user.balance}⭐\n"
            )
            
            if refund_method == "Telegram API":
                report += f"• ℹ️ Звезды возвращены в Telegram\n"
            
            report += (
                f"• ID транзакции возврата: #{refund_transaction.id}\n"
                f"• Время возврата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            await message.reply(report, parse_mode="Markdown")
            
            # Пытаемся уведомить пользователя о возврате
            try:
                user_notification = (
                    f"💰 Вам был выполнен возврат средств!\n\n"
                    f"• Сумма: {refund_amount}⭐\n"
                    f"• Метод: {refund_method}\n"
                )
                
                if refund_method == "Telegram API":
                    user_notification += (
                        f"• ✅ Звезды возвращены в ваш Telegram\n"
                        f"• Баланс в боте уменьшен на {refund_amount}⭐\n"
                        f"• Текущий баланс в боте: {user.balance}⭐\n"
                    )
                else:
                    user_notification += (
                        f"• ✅ Звезды добавлены на внутренний баланс\n"
                        f"• Новый баланс: {user.balance}⭐\n"
                    )
                
                user_notification += (
                    f"• Причина: возврат транзакции #{transaction_id}\n"
                    f"• Администратор: {admin_user.username}"
                )
                
                await message.bot.send_message(
                    user.user_id,
                    user_notification
                )
                log.info(f"User {user.user_id} notified about refund")
            except Exception as e:
                log.warning(f"Could not notify user {user.user_id} about refund: {e}")
                await message.reply(
                    "⚠️ Возврат выполнен успешно, но не удалось отправить уведомление пользователю."
                )
        
    except Exception as e:
        log.error(f"Error in refund_stars_command: {e}")
        await message.reply(f"❌ Ошибка при выполнении возврата: {str(e)}")


@router.message(Command(commands=["transactions"]))
async def list_transactions_command(message: types.Message, command: CommandObject, db_session):
    """
    Показать список транзакций пользователя.
    Админы могут просматривать транзакции любого пользователя.
    
    Использование:
    - /transactions - показать свои транзакции
    - /transactions <user_id> - показать транзакции пользователя (только для админов)
    """
    try:
        with db_session as db:
            # Проверяем, является ли пользователь админом
            requesting_user = db.query(User).filter(
                User.user_id == message.from_user.id
            ).first()
            
            is_admin = requesting_user and requesting_user.status == "admin"
            
            # Определяем, чьи транзакции показывать
            if command.args and is_admin:
                try:
                    target_user_id = int(command.args.strip())
                except ValueError:
                    await message.reply("❌ ID пользователя должен быть числом.")
                    return
            else:
                target_user_id = message.from_user.id
            
            # Получаем пользователя
            target_user = db.query(User).filter(
                User.user_id == target_user_id
            ).first()
            
            if not target_user:
                await message.reply(f"❌ Пользователь с ID {target_user_id} не найден.")
                return
            
            # Получаем транзакции
            transactions = db.query(Transaction).filter(
                Transaction.user_id == target_user_id
            ).order_by(Transaction.id.desc()).limit(20).all()
            
            if not transactions:
                await message.reply(
                    f"📋 У {'вас' if target_user_id == message.from_user.id else f'пользователя {target_user.username}'} "
                    f"пока нет транзакций."
                )
                return
            
            # Формируем отчет
            report = (
                f"📊 **Транзакции {'ваши' if target_user_id == message.from_user.id else f'пользователя {target_user.username}'}** "
                f"(последние {len(transactions)}):\n\n"
            )
            
            for trans in transactions:
                # Определяем тип транзакции
                if trans.amount > 0:
                    trans_type = "➕ Пополнение"
                    amount_str = f"+{trans.amount}⭐"
                else:
                    trans_type = "➖ Покупка"
                    amount_str = f"{trans.amount}⭐"
                
                if trans.payload and "refund" in trans.payload:
                    trans_type = "💰 Возврат"
                    # Показываем корректно для разных типов возвратов
                    if trans.amount < 0:
                        amount_str = f"{trans.amount}⭐ (вычтено из баланса)"
                    else:
                        amount_str = f"+{abs(trans.amount)}⭐"
                
                # Форматируем время
                try:
                    trans_time = datetime.fromisoformat(trans.time).strftime("%d.%m.%Y %H:%M")
                except:
                    trans_time = trans.time or "Неизвестно"
                
                # Добавляем информацию о транзакции
                report += (
                    f"**#{trans.id}** {trans_type}\n"
                    f"• Сумма: {amount_str}\n"
                    f"• Статус: {'✅ Завершена' if trans.status == 'completed' else '🔄 Возвращена'}\n"
                    f"• Время: {trans_time}\n"
                )
                
                # Для админов показываем дополнительную информацию
                if is_admin:
                    report += f"• ID платежа: `{trans.telegram_payment_charge_id}`\n"
                    if trans.payload:
                        report += f"• Payload: `{trans.payload[:50]}{'...' if len(trans.payload) > 50 else ''}`\n"
                
                report += "\n"
            
            # Добавляем информацию о текущем балансе
            report += f"💰 Текущий баланс: {target_user.balance}⭐"
            
            await message.reply(report, parse_mode="Markdown")
            
    except Exception as e:
        log.error(f"Error in list_transactions_command: {e}")
        await message.reply(f"❌ Ошибка при получении транзакций: {str(e)}")


@router.message(Command(commands=["find_transaction"]))
async def find_transaction_command(message: types.Message, command: CommandObject, db_session):
    """
    Найти транзакцию по различным критериям.
    Только для администраторов.
    
    Использование: /find_transaction <payment_charge_id или сумма>
    """
    if not command.args:
        await message.reply(
            "❌ Укажите ID платежа или сумму для поиска.\n"
            "Пример: /find_transaction 500"
        )
        return
    
    with db_session as db:
        # Проверяем права
        admin_user = db.query(User).filter(
            User.user_id == message.from_user.id
        ).first()
        
        if not admin_user or admin_user.status != "admin":
            await message.reply("❌ У вас нет прав для выполнения этой команды.")
            return
        
        search_term = command.args.strip()
        
        # Пробуем найти по charge_id
        transactions = db.query(Transaction).filter(
            Transaction.telegram_payment_charge_id.contains(search_term)
        ).all()
        
        # Если не нашли, пробуем по сумме
        if not transactions:
            try:
                amount = int(search_term)
                transactions = db.query(Transaction).filter(
                    Transaction.amount == amount
                ).order_by(Transaction.id.desc()).limit(10).all()
            except ValueError:
                pass
        
        if not transactions:
            await message.reply(f"❌ Транзакции по запросу '{search_term}' не найдены.")
            return
        
        report = f"🔍 Найдено транзакций: {len(transactions)}\n\n"
        
        for trans in transactions[:10]:  # Показываем максимум 10
            user = db.query(User).filter(User.user_id == trans.user_id).first()
            username = user.username if user else "Unknown"
            
            report += (
                f"**#{trans.id}**\n"
                f"• Пользователь: {username} (ID: {trans.user_id})\n"
                f"• Сумма: {trans.amount}⭐\n"
                f"• Статус: {trans.status}\n"
                f"• ID платежа: `{trans.telegram_payment_charge_id}`\n"
                f"• Время: {trans.time}\n\n"
            )
        
        if len(transactions) > 10:
            report += f"... и еще {len(transactions) - 10} транзакций"
        
        await message.reply(report, parse_mode="Markdown")