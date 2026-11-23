import asyncio,logging
from aiogram import Bot,Dispatcher,F
from aiogram.filters import CommandStart,Command
from aiogram.types import Message,CallbackQuery,InlineKeyboardButton,InlineKeyboardMarkup,WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.core.config import settings
from app.database.connection import init_database,SessionLocal
from app.database.models import User
from app.services.accounts import get_or_create_user
from app.services.wallet import balance,fmt,history
logging.basicConfig(level=logging.INFO)
dp=Dispatcher()
def kb():
    b=InlineKeyboardBuilder()
    if settings.WEBAPP_URL.startswith("https://"): b.row(InlineKeyboardButton(text="💎 Открыть TNC Wallet",web_app=WebAppInfo(url=settings.WEBAPP_URL)))
    else: b.row(InlineKeyboardButton(text="💎 TNC Wallet",callback_data="wallet"))
    b.row(InlineKeyboardButton(text="👤 Аккаунт",callback_data="account"),InlineKeyboardButton(text="📊 История",callback_data="history"))
    b.row(InlineKeyboardButton(text="₿ TNC Crypto",callback_data="crypto"),InlineKeyboardButton(text="🎮 TNC Games",callback_data="games"))
    b.row(InlineKeyboardButton(text="👥 Community",callback_data="community"),InlineKeyboardButton(text="⚙️ Настройки",callback_data="settings"))
    return b.as_markup()
back=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Главное меню",callback_data="menu")]])
def ensure(tg):
    with SessionLocal() as db:
        u=get_or_create_user(db,{"id":tg.id,"username":tg.username,"first_name":tg.first_name or "TNC User"}); db.commit(); return u.telegram_id
@dp.message(CommandStart())
async def start(m:Message):
    ensure(m.from_user)
    await m.answer(f"💎 <b>TNC ECOSYSTEM</b>\n\nДобро пожаловать, {m.from_user.first_name}!\nКошелёк, TNC Coin, игры и сообщество — в одном аккаунте.",reply_markup=kb(),parse_mode="HTML")
@dp.message(Command("menu"))
async def menu_cmd(m): await m.answer("💎 <b>Главное меню TNC</b>",reply_markup=kb(),parse_mode="HTML")
@dp.message(Command("help"))
async def help_cmd(m): await m.answer("Команды: /start, /menu, /help. TNC Coin — внутренняя учётная валюта экосистемы.")
@dp.callback_query(F.data=="menu")
async def menu_cb(c): await c.message.edit_text("💎 <b>Главное меню TNC</b>",reply_markup=kb(),parse_mode="HTML"); await c.answer()
@dp.callback_query(F.data.in_({"wallet","account"}))
async def account_cb(c):
    ensure(c.from_user)
    with SessionLocal() as db:
        u=db.get(User,c.from_user.id); bal=fmt(balance(db,c.from_user.id))
    text=(f"👤 <b>TNC ACCOUNT</b>\nИмя: {u.first_name}\nID: <code>{u.telegram_id}</code>" if c.data=="account" else f"💎 <b>TNC WALLET</b>\nБаланс: <b>{bal} TNC</b>\n\nTNC Coin — внутренняя валюта.")
    await c.message.edit_text(text,reply_markup=back,parse_mode="HTML"); await c.answer()
@dp.callback_query(F.data=="history")
async def hist_cb(c):
    with SessionLocal() as db: rows=history(db,c.from_user.id)
    lines=["📊 <b>История операций</b>"]
    lines += [f"{'↗️' if t.sender_id==c.from_user.id else '↙️'} {fmt(t.amount_units)} TNC · {t.kind}" for t in rows] or ["Операций пока нет."]
    await c.message.edit_text("\n".join(lines),reply_markup=back,parse_mode="HTML"); await c.answer()
@dp.callback_query(F.data=="crypto")
async def crypto(c): await c.message.edit_text("₿ <b>TNC CRYPTO</b>\n\nРаздел внешних блокчейн-кошельков. Реальные криптооперации пока отключены.",reply_markup=back,parse_mode="HTML"); await c.answer()
@dp.callback_query(F.data=="games")
async def games(c): await c.message.edit_text("🎮 <b>TNC GAMES</b>\n\nРаздел игр, заданий, турниров и наград. Подключение к единому TNC Account предусмотрено.",reply_markup=back,parse_mode="HTML"); await c.answer()
@dp.callback_query(F.data=="community")
async def community(c):
    me=await c.bot.get_me()
    await c.message.edit_text(f"👥 <b>TNC COMMUNITY</b>\n\nТвоя ссылка-приглашение:\nhttps://t.me/{me.username}?start=ref_{c.from_user.id}",reply_markup=back,parse_mode="HTML"); await c.answer()
@dp.callback_query(F.data=="settings")
async def settings_cb(c): await c.message.edit_text("⚙️ <b>Настройки</b>\n\nУведомления и дополнительные параметры появятся в следующих модулях.",reply_markup=back,parse_mode="HTML"); await c.answer()
async def main():
    if not settings.BOT_TOKEN: raise RuntimeError("Добавь BOT_TOKEN в .env")
    init_database()
    bot=Bot(settings.BOT_TOKEN)
    await dp.start_polling(bot)
if __name__=="__main__": asyncio.run(main())
