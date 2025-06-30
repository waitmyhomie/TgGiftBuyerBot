import asyncio
import aiohttp
from datetime import datetime

from utils.logger import log
from api.gifts import GiftsApi
from db.models import Gift, AutoBuySettings, User, Transaction
from db.session import get_db_session


async def process_autobuy_for_user(db, gifts_api, user, settings, new_gifts):
    """
    Скупает подарки примерно поровну с приоритетом на редкие.
    """
    # ИСКЛЮЧЕННЫЕ ПОДАРКИ
    EXCLUDED_GIFTS = ["5782984811920491178"]
    
    # Фильтруем подходящие подарки
    eligible_gifts = []
    
    for gift in new_gifts:
        # Пропускаем исключенные
        if gift.gift_id in EXCLUDED_GIFTS:
            log.info(f"⛔ Пропускаем исключенный подарок: {gift.gift_id}")
            continue
            
        # Пропускаем unlimited
        if gift.total_count is None or gift.remaining_count is None:
            continue
            
        # Пропускаем распроданные
        if gift.remaining_count == 0:
            continue
            
        # Проверяем условия
        if (gift.price is not None and
            settings.price_limit_from <= gift.price <= settings.price_limit_to and
            (settings.supply_limit is None or gift.total_count <= settings.supply_limit)):
            
            eligible_gifts.append(gift)
    
    if not eligible_gifts:
        log.info(f"❌ Нет подходящих подарков для пользователя {user.user_id}")
        return 0
    
    # СОРТИРУЕМ ПО РЕДКОСТИ (меньше total_count = выше приоритет)
    eligible_gifts.sort(key=lambda x: x.total_count)
    
    log.info(f"🎁 Найдено {len(eligible_gifts)} подарков для скупки. Баланс: {user.balance}⭐")
    
    # НОВАЯ ЛОГИКА РАСПРЕДЕЛЕНИЯ
    total_balance = user.balance
    num_gifts = len(eligible_gifts)
    
    # Базовое распределение - делим баланс поровну
    base_budget_per_gift = total_balance // num_gifts
    
    # Рассчитываем бюджет для каждого подарка с учетом редкости
    gift_budgets = []
    for i, gift in enumerate(eligible_gifts):
        # Коэффициент редкости (чем меньше порядковый номер, тем редче)
        # Первый (самый редкий) получает 1.5x, последний 0.8x
        rarity_coefficient = 1.5 - (i * 0.7 / (num_gifts - 1)) if num_gifts > 1 else 1.0
        
        # Бюджет с учетом редкости
        adjusted_budget = int(base_budget_per_gift * rarity_coefficient)
        
        # Сколько можем купить
        max_can_buy = min(
            adjusted_budget // gift.price,
            gift.remaining_count,
            total_balance // gift.price  # На случай если это последний подарок
        )
        
        gift_budgets.append({
            'gift': gift,
            'budget': adjusted_budget,
            'max_can_buy': max_can_buy,
            'actual_spend': max_can_buy * gift.price
        })
        
        log.info(f"📊 План для {gift.gift_id} (редкость {gift.total_count}): "
                f"бюджет {adjusted_budget}⭐, купим {max_can_buy} шт.")
    
    # ПОКУПАЕМ ПОДАРКИ
    total_purchased = 0
    purchases_log = {}
    
    for plan in gift_budgets:
        gift = plan['gift']
        to_buy = plan['max_can_buy']
        
        if to_buy == 0 or user.balance < gift.price:
            continue
        
        purchased_this_gift = 0
        
        # Покупаем партию
        for _ in range(to_buy):
            if user.balance < gift.price:
                break
                
            success = await gifts_api.send_gift(
                user_id=user.user_id,
                gift_id=gift.gift_id,
                pay_for_upgrade=False
            )
            
            if success:
                user.balance -= gift.price
                gift.remaining_count -= 1
                purchased_this_gift += 1
                total_purchased += 1
                
                # Записываем транзакцию
                transaction = Transaction(
                    user_id=user.user_id,
                    amount=-gift.price,
                    telegram_payment_charge_id="autobuy_bulk_transaction",
                    payload=f"Autobuy_gift_{gift.gift_id}_rarity_{gift.total_count}",
                    status="completed",
                    time=datetime.utcnow().isoformat(),
                )
                db.add(transaction)
            else:
                log.warning(f"❌ Не удалось купить подарок {gift.gift_id}")
                break
        
        if purchased_this_gift > 0:
            purchases_log[gift.gift_id] = {
                'count': purchased_this_gift,
                'price': gift.price,
                'rarity': gift.total_count,
                'total_spent': purchased_this_gift * gift.price
            }
            
            log.info(f"✅ Куплено {purchased_this_gift} шт. подарка {gift.gift_id} "
                    f"(редкость: {gift.total_count}) по {gift.price}⭐ каждый")
    
    # Финальный отчет
    if purchases_log:
        total_spent = sum(p['total_spent'] for p in purchases_log.values())
        
        log.info(f"\n📊 ИТОГИ СКУПКИ для пользователя {user.user_id}:")
        log.info(f"Начальный баланс: {total_balance}⭐")
        log.info(f"Потрачено: {total_spent}⭐")
        log.info(f"Куплено типов подарков: {len(purchases_log)}")
        log.info(f"Куплено подарков всего: {total_purchased} шт.")
        log.info(f"Остаток баланса: {user.balance}⭐")
        
        # Детали по каждому подарку
        log.info("\nДетализация:")
        for gift_id, details in sorted(purchases_log.items(), key=lambda x: x[1]['rarity']):
            log.info(f"  • {gift_id}: {details['count']} шт. "
                    f"(редкость {details['rarity']}) = {details['total_spent']}⭐")
    
    # Сохраняем изменения
    db.commit()
    
    return total_purchased


async def start_gift_parsing_loop():
    """
    Gift parsing loop - ONLY FOR OWNER
    """
    OWNER_ID = 1487757625  # Ваш ID
    
    gifts_api = GiftsApi()
    session_timeout = aiohttp.ClientTimeout(total=60)
    
    log.info(f"🔐 Starting gift parser in PRIVATE mode for owner ID: {OWNER_ID}")
    
    async with aiohttp.ClientSession(timeout=session_timeout) as session:
        while True:
            try:
                # Получаем подарки
                gifts = await gifts_api.aio_get_available_gifts(session)
                if not gifts:
                    log.warning("Gift list is empty")
                    await asyncio.sleep(10)
                    continue

                # Статистика
                total_gifts = len(gifts)
                unlimited_gifts = [g for g in gifts if g.get('total_count') is None or g.get('remaining_count') is None]
                limited_gifts = [g for g in gifts if g.get('total_count') is not None and g.get('remaining_count') is not None]
                
                log.info(
                    f"📊 Gifts fetched - Total: {total_gifts}, "
                    f"Limited: {len(limited_gifts)}, "
                    f"Unlimited: {len(unlimited_gifts)} (ignored)"
                )

                with get_db_session() as db:
                    # Обновляем базу подарков (только лимитированные)
                    for gift in gifts:
                        if gift.get('total_count') is None or gift.get('remaining_count') is None:
                            continue
                            
                        existing_gift = db.query(Gift).filter(
                            Gift.gift_id == gift['id']).first()
                            
                        if existing_gift:
                            # Обновляем существующий
                            updated = False
                            if existing_gift.price != gift.get('star_count', 0):
                                existing_gift.price = gift.get('star_count', 0)
                                updated = True
                            if existing_gift.remaining_count != gift.get('remaining_count'):
                                existing_gift.remaining_count = gift.get('remaining_count')
                                updated = True
                            if existing_gift.total_count != gift.get('total_count'):
                                existing_gift.total_count = gift.get('total_count')
                                updated = True

                            if updated:
                                log.debug(f"Updated gift {existing_gift.gift_id}")
                        else:
                            # Добавляем новый
                            new_gift = Gift(
                                gift_id=gift['id'],
                                price=gift.get('star_count', 0),
                                remaining_count=gift.get('remaining_count'),
                                total_count=gift.get('total_count'),
                                is_new=True
                            )
                            db.add(new_gift)
                            log.info(f"🆕 New limited gift: {new_gift.gift_id}")

                    db.commit()

                    # ВАЖНО: Обрабатываем ТОЛЬКО владельца
                    owner_settings = db.query(AutoBuySettings).filter(
                        AutoBuySettings.user_id == OWNER_ID,
                        AutoBuySettings.status == "enabled"
                    ).first()
                    
                    if not owner_settings:
                        log.debug("Owner autobuy is disabled")
                        await asyncio.sleep(3)
                        continue
                    
                    # Получаем владельца
                    owner = db.query(User).filter(User.user_id == OWNER_ID).first()
                    if not owner or owner.balance < 1:
                        log.debug("Owner not found or no balance")
                        await asyncio.sleep(3)
                        continue
                    
                    log.info(f"🤖 Processing autobuy for owner. Balance: {owner.balance}⭐")
                    
                    # Обрабатываем циклы
                    total_purchased = 0
                    
                    for cycle in range(owner_settings.cycles):
                        if owner.balance < 1:
                            break
                            
                        log.info(f"🔄 Cycle {cycle + 1}/{owner_settings.cycles}")
                        
                        # Получаем новые подарки
                        new_gifts = db.query(Gift).filter(Gift.is_new == 1).all()
                        
                        if not new_gifts:
                            break
                            
                        purchased = await process_autobuy_for_user(
                            db, gifts_api, owner, owner_settings, new_gifts
                        )
                        total_purchased += purchased
                        
                        if purchased == 0:
                            break
                    
                    if total_purchased > 0:
                        log.info(f"✅ Owner purchased {total_purchased} gifts")

                    # Сбрасываем флаг новых подарков
                    db.query(Gift).filter(Gift.is_new == 1).update({"is_new": 0})
                    db.commit()

                await asyncio.sleep(3)
                
            except Exception as e:
                log.error(f"❌ Error in gift parsing: {e}")
                await asyncio.sleep(3)