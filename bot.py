"""TNC Telegram bot — shared account, wallet and game-token administration."""
import asyncio
import html
import logging
from decimal import Decimal, InvalidOperation

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo,
    InlineKeyboardMarkup, InlineKeyboardButton, PreCheckoutQuery,
    LabeledPrice, CallbackQuery,
)

from app.core.config import settings
from app.database.connection import init_database, SessionLocal
from app.database.models import User
from app.services.accounts import get_or_create_user
from app.services.wallet import balance, fmt, history, send, deposit, withdraw
from app.services.game_tokens import (
    init_game_tables, get_balance as gt_balance,
    admin_adjust_tokens, set_game_ban, get_admin_log,
    create_stars_order, complete_stars_payment, is_game_banned,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tnc.bot")
dp = Dispatcher(storage=MemoryStorage())

WALLET="💎 Кошелёк"; TRANSFER="💸 Перевести TNC"; HISTORY="📊 История"
ACCOUNT="👤 Аккаунт"; GAMES="🎮 TNC Games"; CRYPTO="₿ TNC Crypto"
COMMUNITY="👥 Community"; SETTINGS="⚙️ Настройки"; MINI_APP="🌐 Открыть Mini App"
CANCEL="❌ Отмена"

class TransferFlow(StatesGroup):
    receiver=State(); amount=State()


def main_keyboard():
    url=(settings.WEBAPP_URL or "").strip()
    rows=[]
    if url.startswith("https://"):
        rows.append([KeyboardButton(text=MINI_APP, web_app=WebAppInfo(url=url))])
    rows += [
        [KeyboardButton(text=WALLET),KeyboardButton(text=TRANSFER)],
        [KeyboardButton(text=HISTORY),KeyboardButton(text=ACCOUNT)],
        [KeyboardButton(text=GAMES),KeyboardButton(text=CRYPTO)],
        [KeyboardButton(text=COMMUNITY),KeyboardButton(text=SETTINGS)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows,resize_keyboard=True,is_persistent=True)


def is_admin(uid:int)->bool:
    return int(uid) in settings.ADMIN_IDS


def ensure_user(tg):
    with SessionLocal() as db:
        user=get_or_create_user(db,{"id":tg.id,"username":tg.username,"first_name":tg.first_name or "TNC User"})
        db.commit()
        return user.telegram_id


def esc(value): return html.escape(str(value or ""))


@dp.message(CommandStart())
async def start(message:Message,state:FSMContext):
    await state.clear()
    try: ensure_user(message.from_user)
    except ValueError as e:
        await message.answer(esc(e)); return
    name=esc(message.from_user.first_name or "друг")
    await message.answer(
        f"💎 <b>Добро пожаловать в TNC, {name}!</b>\n\n"
        "Единый аккаунт TNC Wallet и TNC Games.\n"
        "Открой Mini App или выбери действие в меню.",
        reply_markup=main_keyboard(),parse_mode="HTML")

@dp.message(Command("menu"))
async def menu(message:Message,state:FSMContext):
    await state.clear(); await message.answer("💎 <b>TNC ECOSYSTEM</b>",reply_markup=main_keyboard(),parse_mode="HTML")

@dp.message(Command("help"))
async def help_cmd(message:Message):
    await message.answer(
        "<b>TNC — команды</b>\n/start /menu /help\n"
        "/wallet — баланс\n/gt — баланс GT\n"
        "Администратор: /credit /debit /gt_add /gt_take /gt_balance /gameban /gameunban /gt_admin_log",
        parse_mode="HTML",reply_markup=main_keyboard())

@dp.message(F.text==WALLET)
@dp.message(Command("wallet"))
async def wallet(message:Message):
    try:
        ensure_user(message.from_user)
        with SessionLocal() as db: amount=fmt(balance(db,message.from_user.id))
        await message.answer(f"💎 <b>TNC WALLET</b>\nБаланс: <b>{amount} TNC</b>\n\nTNC Coin — внутренняя учётная валюта экосистемы.",parse_mode="HTML",reply_markup=main_keyboard())
    except Exception:
        log.exception("wallet command failed"); await message.answer("Не удалось загрузить кошелёк.")

@dp.message(F.text==TRANSFER)
async def transfer_begin(message:Message,state:FSMContext):
    ensure_user(message.from_user); await state.set_state(TransferFlow.receiver)
    await message.answer("Введи Telegram ID получателя. Он должен хотя бы один раз запустить TNC.",reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=CANCEL)]],resize_keyboard=True))

@dp.message(TransferFlow.receiver)
async def transfer_receiver(message:Message,state:FSMContext):
    if message.text==CANCEL: await state.clear(); await message.answer("Отменено.",reply_markup=main_keyboard()); return
    try: uid=int((message.text or "").strip()); assert uid>0 and uid!=message.from_user.id
    except Exception: await message.answer("Нужен корректный Telegram ID другого пользователя."); return
    await state.update_data(receiver=uid); await state.set_state(TransferFlow.amount)
    await message.answer("Введи сумму TNC (до 6 знаков после запятой).")

@dp.message(TransferFlow.amount)
async def transfer_amount(message:Message,state:FSMContext):
    if message.text==CANCEL: await state.clear(); await message.answer("Отменено.",reply_markup=main_keyboard()); return
    data=await state.get_data()
    try:
        with SessionLocal() as db: tx=send(db,message.from_user.id,int(data['receiver']),(message.text or '').strip())
        await message.answer(f"✅ Перевод выполнен.\nСумма: <b>{fmt(tx.amount_units)} TNC</b>\nID: <code>{tx.operation_id}</code>",parse_mode="HTML",reply_markup=main_keyboard())
    except ValueError as e: await message.answer(esc(e))
    except Exception: log.exception("transfer failed"); await message.answer("Перевод не выполнен. Средства не должны быть списаны.")
    finally: await state.clear()

@dp.message(F.text==HISTORY)
async def history_cmd(message:Message):
    try:
        with SessionLocal() as db: rows=history(db,message.from_user.id,20)
        if not rows: await message.answer("📊 История пока пуста.",reply_markup=main_keyboard()); return
        lines=["📊 <b>Последние операции</b>"]
        for tx in rows:
            incoming=tx.receiver_id==message.from_user.id
            lines.append(f"{'↙️ Получено' if incoming else '↗️ Отправлено'} <b>{fmt(tx.amount_units)} TNC</b> · {esc(tx.kind)} · {tx.created_at}")
        await message.answer("\n".join(lines),parse_mode="HTML",reply_markup=main_keyboard())
    except Exception: log.exception("history failed"); await message.answer("Не удалось загрузить историю.")

@dp.message(F.text==ACCOUNT)
async def account(message:Message):
    ensure_user(message.from_user)
    with SessionLocal() as db:
        u=db.get(User,message.from_user.id); bal=fmt(balance(db,message.from_user.id))
    await message.answer(f"👤 <b>TNC ACCOUNT</b>\nИмя: {esc(u.first_name)}\nUsername: @{esc(u.username) if u.username else '—'}\nID: <code>{u.telegram_id}</code>\nTNC: <b>{bal}</b>\nGT: <b>{gt_balance(u.telegram_id):,}</b>",parse_mode="HTML",reply_markup=main_keyboard())

@dp.message(F.text==GAMES)
async def games(message:Message):
    ensure_user(message.from_user)
    if is_game_banned(message.from_user.id):
        await message.answer("Доступ к TNC Games ограничен. TNC Wallet продолжает работать.",reply_markup=main_keyboard()); return
    await message.answer(f"🎮 <b>TNC GAMES</b>\nИгровой баланс: <b>{gt_balance(message.from_user.id):,} GT</b>\nКурс покупки: 1 ⭐ = 5 000 GT.\nGT не конвертируются в TNC Coin.\n\nИгры открываются в Mini App.",parse_mode="HTML",reply_markup=main_keyboard())

@dp.message(Command("gt"))
async def gt_cmd(message:Message):
    ensure_user(message.from_user)
    await message.answer(f"🎮 Твой баланс: <b>{gt_balance(message.from_user.id):,} GT</b>",parse_mode="HTML")

@dp.message(F.text==CRYPTO)
async def crypto(message:Message): await message.answer("₿ <b>TNC Crypto</b>\nВнешние криптовалютные операции пока не подключены.",parse_mode="HTML",reply_markup=main_keyboard())
@dp.message(F.text==COMMUNITY)
async def community(message:Message):
    me=await message.bot.get_me(); await message.answer(f"👥 TNC Community\nТвоя ссылка: https://t.me/{me.username}?start=ref_{message.from_user.id}",reply_markup=main_keyboard())
@dp.message(F.text==SETTINGS)
async def settings_cmd(message:Message): await message.answer("⚙️ Настройки аккаунта TNC. Управление профилем доступно в Mini App.",reply_markup=main_keyboard())

# Telegram Stars: пользователь выбирает число Stars, начисление GT строго после successful_payment.
@dp.message(Command("buygt"))
async def buy_gt(message:Message):
    parts=(message.text or "").split()
    if len(parts)!=2 or not parts[1].isdigit() or not 1<=int(parts[1])<=10000:
        await message.answer("Формат: /buygt КОЛИЧЕСТВО_STARS (1–10000)"); return
    stars=int(parts[1]); payload=f"tncgt:{message.from_user.id}:{stars}:{__import__('uuid').uuid4().hex}"
    create_stars_order(message.from_user.id,stars,payload)
    await message.answer_invoice(
        title="TNC Game Tokens",description=f"Покупка {stars*5000:,} GT за {stars} Telegram Stars",
        payload=payload, currency="XTR", prices=[LabeledPrice(label=f"{stars*5000:,} GT",amount=stars)])

@dp.pre_checkout_query()
async def pre_checkout(q:PreCheckoutQuery):
    try:
        from app.services.game_tokens import validate_stars_payload
        validate_stars_payload(q.invoice_payload,q.from_user.id,q.total_amount)
        await q.answer(ok=True)
    except Exception as e:
        log.warning("Stars pre-checkout rejected: %s",e); await q.answer(ok=False,error_message="Заказ не найден или не соответствует оплате.")

@dp.message(F.successful_payment)
async def successful_payment(message:Message):
    p=message.successful_payment
    try:
        from app.services.game_tokens import complete_stars_payment
        added=complete_stars_payment(p.invoice_payload,message.from_user.id,p.total_amount,p.telegram_payment_charge_id)
        await message.answer(f"⭐ Оплата получена. Начислено <b>{added:,} GT</b>.",parse_mode="HTML")
    except Exception:
        log.exception("Stars fulfilment failed"); await message.answer("Оплата получена, но автоматическое начисление требует проверки поддержки. Сохрани ID платежа: "+esc(p.telegram_payment_charge_id))

# Admin commands
async def admin_only(message):
    if not is_admin(message.from_user.id): await message.answer("⛔ Нет доступа."); return False
    return True

@dp.message(Command("credit"))
async def credit(message:Message):
    if not await admin_only(message): return
    p=(message.text or '').split(maxsplit=2)
    if len(p)<3: await message.answer("Формат: /credit USER_ID AMOUNT"); return
    try:
        with SessionLocal() as db: tx=deposit(db,int(p[1]),p[2],description=f"Admin credit {message.from_user.id}")
        await message.answer(f"Зачислено {fmt(tx.amount_units)} TNC пользователю {p[1]}.")
    except Exception as e: await message.answer("Ошибка зачисления: "+esc(e))

@dp.message(Command("debit"))
async def debit(message:Message):
    if not await admin_only(message): return
    p=(message.text or '').split(maxsplit=2)
    if len(p)<3: await message.answer("Формат: /debit USER_ID AMOUNT"); return
    try:
        with SessionLocal() as db: tx=withdraw(db,int(p[1]),p[2],description=f"Admin debit {message.from_user.id}")
        await message.answer(f"Списано {fmt(tx.amount_units)} TNC у пользователя {p[1]}.")
    except Exception as e: await message.answer("Ошибка списания: "+esc(e))

@dp.message(Command("gt_add"))
async def gt_add(message:Message):
    if not await admin_only(message): return
    p=(message.text or '').split(maxsplit=3)
    if len(p)<3: await message.answer("Формат: /gt_add USER_ID AMOUNT [причина]"); return
    try:
        new=admin_adjust_tokens(message.from_user.id,int(p[1]),int(p[2]),"admin_add",p[3] if len(p)>3 else "Admin credit")
        await message.answer(f"Начислено {int(p[2]):,} GT. Новый баланс: {new:,} GT.")
    except Exception as e: await message.answer("Ошибка: "+esc(e))

@dp.message(Command("gt_take"))
async def gt_take(message:Message):
    if not await admin_only(message): return
    p=(message.text or '').split(maxsplit=3)
    if len(p)<3: await message.answer("Формат: /gt_take USER_ID AMOUNT [причина]"); return
    try:
        new=admin_adjust_tokens(message.from_user.id,int(p[1]),-int(p[2]),"admin_take",p[3] if len(p)>3 else "Admin debit")
        await message.answer(f"Списано {int(p[2]):,} GT. Новый баланс: {new:,} GT.")
    except Exception as e: await message.answer("Ошибка: "+esc(e))

@dp.message(Command("gt_balance"))
async def gt_balance_cmd(message:Message):
    if not await admin_only(message): return
    p=(message.text or '').split()
    if len(p)!=2: await message.answer("Формат: /gt_balance USER_ID"); return
    try: await message.answer(f"Баланс {p[1]}: <b>{gt_balance(int(p[1])):,} GT</b>",parse_mode="HTML")
    except Exception as e: await message.answer("Ошибка: "+esc(e))

@dp.message(Command("gameban"))
async def gameban(message:Message):
    if not await admin_only(message): return
    p=(message.text or '').split(maxsplit=2)
    if len(p)<2: await message.answer("Формат: /gameban USER_ID [причина]"); return
    try: set_game_ban(message.from_user.id,int(p[1]),True,p[2] if len(p)>2 else "Admin ban"); await message.answer("Пользователь заблокирован только в TNC Games.")
    except Exception as e: await message.answer("Ошибка: "+esc(e))

@dp.message(Command("gameunban"))
async def gameunban(message:Message):
    if not await admin_only(message): return
    p=(message.text or '').split(maxsplit=2)
    if len(p)<2: await message.answer("Формат: /gameunban USER_ID [причина]"); return
    try: set_game_ban(message.from_user.id,int(p[1]),False,p[2] if len(p)>2 else "Admin unban"); await message.answer("Доступ к TNC Games восстановлен.")
    except Exception as e: await message.answer("Ошибка: "+esc(e))

@dp.message(Command("gt_admin_log"))
async def gt_log(message:Message):
    if not await admin_only(message): return
    rows=get_admin_log(20)
    if not rows: await message.answer("Журнал пуст."); return
    lines=["<b>Журнал TNC Games</b>"]
    for r in rows: lines.append(f"{esc(r['action'])}: admin <code>{r['admin_id']}</code> → user <code>{r['user_id']}</code>, {r['amount']} GT, {esc(r['reason'])}")
    await message.answer("\n".join(lines),parse_mode="HTML")

@dp.message()
async def unknown(message:Message): await message.answer("Не понял сообщение. Используй меню или /help.",reply_markup=main_keyboard())

async def main():
    if not settings.BOT_TOKEN: raise RuntimeError("BOT_TOKEN не задан в переменных окружения.")
    init_database(); init_game_tables()
    bot=Bot(settings.BOT_TOKEN)
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        log.info("TNC bot polling started")
        await dp.start_polling(bot,allowed_updates=dp.resolve_used_update_types())
    finally: await bot.session.close()

if __name__=="__main__": asyncio.run(main())
