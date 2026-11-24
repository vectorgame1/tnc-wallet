from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from aiogram.types import CallbackQuery, PreCheckoutQuery

import asyncio
import html
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    KeyboardButton,
    ReplyKeyboardMarkup,
    BufferedInputFile,
    WebAppInfo,
)

from app.core.config import settings
from app.database.connection import init_database, SessionLocal
from app.database.models import User
from app.services.accounts import get_or_create_user
from app.services.wallet import (
    balance,
    fmt,
    history,
    send,
    deposit,
    withdraw,
)
from app.services.transaction_image import (
    create_section_image,
    create_transaction_image,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("tnc.bot")

dp = Dispatcher(storage=MemoryStorage())


# --------------------------------------------------
# TNC MENU
# --------------------------------------------------

WALLET = "рџ’Ћ РљРѕС€РµР»С‘Рє"
TRANSFER = "рџ’ё РџРµСЂРµРІРµСЃС‚Рё TNC"
HISTORY = "рџ“Љ РСЃС‚РѕСЂРёСЏ"
ACCOUNT = "рџ‘¤ РђРєРєР°СѓРЅС‚"
CRYPTO = "в‚ї TNC Crypto"
GAMES = "рџЋ® TNC Games"
COMMUNITY = "рџ‘Ґ Community"
SETTINGS = "вљ™пёЏ РќР°СЃС‚СЂРѕР№РєРё"
MINI_APP = "рџЊђ РћС‚РєСЂС‹С‚СЊ Mini App"
CANCEL = "вќЊ РћС‚РјРµРЅР°"
BACK = "в¬…пёЏ Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ"


class TransferFlow(StatesGroup):
    receiver = State()
    amount = State()


def main_keyboard():
    rows = []

    webapp_url = getattr(settings, "WEBAPP_URL", "") or ""

    if webapp_url.startswith("https://"):
        rows.append([
            KeyboardButton(
                text=MINI_APP,
                web_app=WebAppInfo(url=webapp_url),
            )
        ])
    else:
        rows.append([KeyboardButton(text=MINI_APP)])

    rows.extend([
        [
            KeyboardButton(text=WALLET),
            KeyboardButton(text=TRANSFER),
        ],
        [
            KeyboardButton(text=HISTORY),
            KeyboardButton(text=ACCOUNT),
        ],
        [
            KeyboardButton(text=CRYPTO),
            KeyboardButton(text=GAMES),
        ],
        [
            KeyboardButton(text=COMMUNITY),
            KeyboardButton(text=SETTINGS),
        ],
    ])

    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Р’С‹Р±РµСЂРё СЂР°Р·РґРµР» TNC",
    )


def cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=CANCEL)],
            [KeyboardButton(text=BACK)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def ensure_user(tg_user):
    with SessionLocal() as db:
        user = get_or_create_user(
            db,
            {
                "id": tg_user.id,
                "username": tg_user.username,
                "first_name": tg_user.first_name or "TNC User",
            },
        )
        db.commit()
        return user.telegram_id


# --------------------------------------------------
# IMAGE HELPERS
# --------------------------------------------------

async def send_section(
    message: Message,
    section: str,
    title: str,
    subtitle: str,
    detail: str = "",
    caption: str = "",
):
    image = create_section_image(
        section=section,
        title=title,
        subtitle=subtitle,
        detail=detail,
    )

    await message.answer_photo(
        photo=BufferedInputFile(
            image.getvalue(),
            filename="tnc-section.png",
        ),
        caption=caption or f"<b>{html.escape(title)}</b>\n\n{html.escape(subtitle)}",
        reply_markup=main_keyboard(),
        parse_mode="HTML",
    )


async def send_operation_image(
    bot: Bot,
    chat_id: int,
    amount: int,
    operation: str,
    username: str,
    operation_id: str = "",
    caption: str = "",
):
    image = create_transaction_image(
        amount=amount,
        operation=operation,
        username=username,
        operation_id=operation_id,
    )

    await bot.send_photo(
        chat_id=chat_id,
        photo=BufferedInputFile(
            image.getvalue(),
            filename="tnc-operation.png",
        ),
        caption=caption,
        parse_mode="HTML",
    )


async def show_home(message: Message, greeting=True):
    if greeting:
        name = html.escape(message.from_user.first_name or "User")
        caption = (
            f"рџ’Ћ <b>Р”РѕР±СЂРѕ РїРѕР¶Р°Р»РѕРІР°С‚СЊ РІ TNC, {name}!</b>\n\n"
            "РўРІРѕР№ РµРґРёРЅС‹Р№ Р°РєРєР°СѓРЅС‚ С†РёС„СЂРѕРІРѕР№ СЌРєРѕСЃРёСЃС‚РµРјС‹.\n"
            "Р’С‹Р±РёСЂР°Р№ СЂР°Р·РґРµР» СЃ РїРѕРјРѕС‰СЊСЋ РєР»Р°РІРёР°С‚СѓСЂС‹ РЅРёР¶Рµ."
        )
    else:
        caption = (
            "рџ’Ћ <b>TNC ECOSYSTEM</b>\n\n"
            "Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ. Р’С‹Р±РµСЂРё РЅСѓР¶РЅС‹Р№ СЂР°Р·РґРµР»."
        )

    await send_section(
        message,
        "TNC ECOSYSTEM",
        "WELCOME TO TNC",
        "YOUR ACCOUNT. YOUR ECOSYSTEM.",
        "WALLET  вЂў  CRYPTO  вЂў  GAMES",
        caption,
    )


# --------------------------------------------------
# START AND COMMANDS
# --------------------------------------------------

@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()

    try:
        ensure_user(message.from_user)
    except ValueError as error:
        await message.answer(str(error))
        return

    await show_home(message)


@dp.message(Command("menu"))
async def menu_handler(message: Message, state: FSMContext):
    await state.clear()
    await show_home(message, greeting=False)


@dp.message(Command("help"))
async def help_handler(message: Message):
    await send_section(
        message,
        "TNC SUPPORT",
        "HELP CENTER",
        "РљРѕРјР°РЅРґС‹ Рё РІРѕР·РјРѕР¶РЅРѕСЃС‚Рё TNC Wallet",
        "/start  вЂў  /menu  вЂў  /help",
        (
            "в„№пёЏ <b>РџРѕРјРѕС‰СЊ TNC</b>\n\n"
            "/start вЂ” Р·Р°РїСѓСЃРє Р°РєРєР°СѓРЅС‚Р°\n"
            "/menu вЂ” РіР»Р°РІРЅРѕРµ РјРµРЅСЋ\n"
            "/help вЂ” РїРѕРјРѕС‰СЊ\n\n"
            "Р”Р»СЏ РїРµСЂРµРІРѕРґР° РїРѕР»СѓС‡Р°С‚РµР»СЊ РґРѕР»Р¶РµРЅ Р·Р°РїСѓСЃС‚РёС‚СЊ Р±РѕС‚Р°.\n"
            "TNC Coin вЂ” РІРЅСѓС‚СЂРµРЅРЅСЏСЏ СѓС‡С‘С‚РЅР°СЏ РІР°Р»СЋС‚Р° СЌРєРѕСЃРёСЃС‚РµРјС‹."
        ),
    )


@dp.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await show_home(message, greeting=False)


# --------------------------------------------------
# WALLET
# --------------------------------------------------

@dp.message(F.text == WALLET)
async def wallet_handler(message: Message):
    try:
        ensure_user(message.from_user)

        with SessionLocal() as db:
            current_balance = fmt(balance(db, message.from_user.id))

        await send_section(
            message,
            "TNC WALLET",
            "YOUR BALANCE",
            f"{current_balance} TNC",
            "SECURE INTERNAL ACCOUNT",
            (
                "рџ’Ћ <b>TNC WALLET</b>\n\n"
                f"Р”РѕСЃС‚СѓРїРЅС‹Р№ Р±Р°Р»Р°РЅСЃ: <b>{current_balance} TNC</b>\n\n"
                "Р—РґРµСЃСЊ РѕС‚РѕР±СЂР°Р¶Р°СЋС‚СЃСЏ РІРЅСѓС‚СЂРµРЅРЅРёРµ СЃСЂРµРґСЃС‚РІР° С‚РІРѕРµРіРѕ Р°РєРєР°СѓРЅС‚Р°."
            ),
        )
    except Exception:
        logger.exception("Wallet screen failed")
        await message.answer(
            "РќРµ СѓРґР°Р»РѕСЃСЊ РѕС‚РєСЂС‹С‚СЊ РєРѕС€РµР»С‘Рє. РџРѕРїСЂРѕР±СѓР№ РµС‰С‘ СЂР°Р·.",
            reply_markup=main_keyboard(),
        )


# --------------------------------------------------
# TRANSFERS
# --------------------------------------------------

@dp.message(F.text == TRANSFER)
async def transfer_start(message: Message, state: FSMContext):
    try:
        ensure_user(message.from_user)
    except ValueError as error:
        await message.answer(str(error))
        return

    await state.set_state(TransferFlow.receiver)

    await send_section(
        message,
        "TNC TRANSFER",
        "SEND TNC",
        "Р‘С‹СЃС‚СЂС‹Р№ РІРЅСѓС‚СЂРµРЅРЅРёР№ РїРµСЂРµРІРѕРґ",
        "RECIPIENT  в†’  AMOUNT  в†’  CONFIRMATION",
        (
            "рџ’ё <b>РќРѕРІС‹Р№ РїРµСЂРµРІРѕРґ</b>\n\n"
            "Р’РІРµРґРё Telegram ID РїРѕР»СѓС‡Р°С‚РµР»СЏ.\n"
            "РџРѕР»СѓС‡Р°С‚РµР»СЊ РґРѕР»Р¶РµРЅ РїСЂРµРґРІР°СЂРёС‚РµР»СЊРЅРѕ Р·Р°РїСѓСЃС‚РёС‚СЊ TNC Wallet."
        ),
    )

    await message.answer(
        "РћС‚РїСЂР°РІСЊ Telegram ID РїРѕР»СѓС‡Р°С‚РµР»СЏ РёР»Рё РЅР°Р¶РјРё В«РћС‚РјРµРЅР°В».",
        reply_markup=cancel_keyboard(),
    )


@dp.message(TransferFlow.receiver)
async def transfer_receiver(message: Message, state: FSMContext):
    if message.text in (CANCEL, BACK):
        await state.clear()
        await show_home(message, greeting=False)
        return

    try:
        receiver_id = int((message.text or "").strip())
        if receiver_id <= 0:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("Р’РІРµРґРё РєРѕСЂСЂРµРєС‚РЅС‹Р№ С‡РёСЃР»РѕРІРѕР№ Telegram ID.")
        return

    if receiver_id == message.from_user.id:
        await message.answer("РќРµР»СЊР·СЏ РѕС‚РїСЂР°РІРёС‚СЊ РїРµСЂРµРІРѕРґ СЃР°РјРѕРјСѓ СЃРµР±Рµ.")
        return

    await state.update_data(receiver_id=receiver_id)
    await state.set_state(TransferFlow.amount)

    await send_section(
        message,
        "TNC TRANSFER",
        "TRANSFER AMOUNT",
        "РЈРєР°Р¶Рё СЃСѓРјРјСѓ РІ TNC",
        "MAXIMUM: 1 000 000 TNC",
        f"РџРѕР»СѓС‡Р°С‚РµР»СЊ: <code>{receiver_id}</code>\n\nРўРµРїРµСЂСЊ РІРІРµРґРё СЃСѓРјРјСѓ РїРµСЂРµРІРѕРґР°.",
    )

    await message.answer(
        "РќР°РїСЂРёРјРµСЂ: 25 РёР»Рё 125.50",
        reply_markup=cancel_keyboard(),
    )


@dp.message(TransferFlow.amount)
async def transfer_amount(message: Message, state: FSMContext):
    if message.text in (CANCEL, BACK):
        await state.clear()
        await show_home(message, greeting=False)
        return

    amount_text = (message.text or "").strip().replace(",", ".")

    data = await state.get_data()
    receiver_id = data.get("receiver_id")

    try:
        with SessionLocal() as db:
            transaction = send(
                db,
                message.from_user.id,
                receiver_id,
                amount_text,
            )

        await state.clear()

        amount = transaction.amount_units / 1_000_000
        operation_id = transaction.operation_id

        await send_operation_image(
            message.bot,
            message.from_user.id,
            amount,
            "sent",
            message.from_user.first_name or "TNC USER",
            operation_id,
            (
                "вњ… <b>РџРµСЂРµРІРѕРґ РІС‹РїРѕР»РЅРµРЅ</b>\n\n"
                f"РџРѕР»СѓС‡Р°С‚РµР»СЊ: <code>{receiver_id}</code>\n"
                f"РћРїРµСЂР°С†РёСЏ: <code>{operation_id}</code>"
            ),
        )

        try:
            with SessionLocal() as db:
                recipient = db.get(User, receiver_id)
                recipient_name = (
                    recipient.first_name if recipient else "TNC USER"
                )

            await send_operation_image(
                message.bot,
                receiver_id,
                amount,
                "received",
                recipient_name,
                operation_id,
                (
                    "рџ’› <b>РўС‹ РїРѕР»СѓС‡РёР» РїРµСЂРµРІРѕРґ TNC!</b>\n\n"
                    f"РћС‚РїСЂР°РІРёС‚РµР»СЊ: <code>{message.from_user.id}</code>\n"
                    f"РћРїРµСЂР°С†РёСЏ: <code>{operation_id}</code>"
                ),
            )
        except Exception:
            logger.exception("Could not notify transfer recipient")

        await message.answer(
            "Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ РґРѕСЃС‚СѓРїРЅРѕ РЅРёР¶Рµ.",
            reply_markup=main_keyboard(),
        )

    except ValueError as error:
        await state.clear()
        await message.answer(
            f"вќЊ {html.escape(str(error))}",
            reply_markup=main_keyboard(),
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Transfer failed")
        await state.clear()
        await message.answer(
            "РќРµ СѓРґР°Р»РѕСЃСЊ РІС‹РїРѕР»РЅРёС‚СЊ РїРµСЂРµРІРѕРґ. РџРѕРїСЂРѕР±СѓР№ РїРѕР·Р¶Рµ.",
            reply_markup=main_keyboard(),
        )


# --------------------------------------------------
# HISTORY
# --------------------------------------------------

@dp.message(F.text == HISTORY)
async def history_handler(message: Message):
    try:
        ensure_user(message.from_user)

        with SessionLocal() as db:
            transactions = history(db, message.from_user.id, 15)

        await send_section(
            message,
            "TNC ACTIVITY",
            "TRANSACTION HISTORY",
            "Р’СЃРµ РѕРїРµСЂР°С†РёРё С‚РІРѕРµРіРѕ Р°РєРєР°СѓРЅС‚Р°",
            f"{len(transactions)} РїРѕСЃР»РµРґРЅРёС… Р·Р°РїРёСЃРµР№",
            "рџ“Љ <b>РСЃС‚РѕСЂРёСЏ TNC Wallet</b>",
        )

        if not transactions:
            await message.answer(
                "РџРѕРєР° РЅРµС‚ РѕРїРµСЂР°С†РёР№.",
                reply_markup=main_keyboard(),
            )
            return

        lines = ["<b>РџРѕСЃР»РµРґРЅРёРµ РѕРїРµСЂР°С†РёРё:</b>\n"]

        for tx in transactions:
            outgoing = tx.sender_id == message.from_user.id

            if tx.kind == "deposit":
                icon = "рџџў"
                label = "РџРѕРїРѕР»РЅРµРЅРёРµ"
                sign = "+"
            elif tx.kind == "withdraw":
                icon = "рџ”ґ"
                label = "РЎРїРёСЃР°РЅРёРµ"
                sign = "в€’"
            elif outgoing:
                icon = "в†—пёЏ"
                label = "РћС‚РїСЂР°РІР»РµРЅРѕ"
                sign = "в€’"
            else:
                icon = "в†™пёЏ"
                label = "РџРѕР»СѓС‡РµРЅРѕ"
                sign = "+"

            lines.append(
                f"{icon} <b>{label}</b>\n"
                f"{sign}{fmt(tx.amount_units)} TNC\n"
                f"<code>{tx.operation_id}</code>"
            )

        await message.answer(
            "\n\n".join(lines),
            reply_markup=main_keyboard(),
            parse_mode="HTML",
        )

    except Exception:
        logger.exception("History failed")
        await message.answer("РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ РёСЃС‚РѕСЂРёСЋ.")


# --------------------------------------------------
# ACCOUNT
# --------------------------------------------------

@dp.message(F.text == ACCOUNT)
async def account_handler(message: Message):
    try:
        ensure_user(message.from_user)

        with SessionLocal() as db:
            user = db.get(User, message.from_user.id)
            current_balance = fmt(balance(db, message.from_user.id))

        username = (
            f"@{html.escape(user.username)}"
            if user.username
            else "РќРµ СѓРєР°Р·Р°РЅ"
        )

        await send_section(
            message,
            "TNC ACCOUNT",
            "YOUR PROFILE",
            html.escape(user.first_name),
            f"ID: {user.telegram_id}",
            (
                "рџ‘¤ <b>РўРІРѕР№ TNC Account</b>\n\n"
                f"РРјСЏ: {html.escape(user.first_name)}\n"
                f"Username: {username}\n"
                f"Telegram ID: <code>{user.telegram_id}</code>\n"
                f"Р‘Р°Р»Р°РЅСЃ: <b>{current_balance} TNC</b>"
            ),
        )

    except Exception:
        logger.exception("Account screen failed")
        await message.answer("РќРµ СѓРґР°Р»РѕСЃСЊ РѕС‚РєСЂС‹С‚СЊ Р°РєРєР°СѓРЅС‚.")


# --------------------------------------------------
# CRYPTO AND GAMES
# --------------------------------------------------

@dp.message(F.text == CRYPTO)
async def crypto_handler(message: Message):
    await send_section(
        message,
        "TNC CRYPTO",
        "CRYPTO HUB",
        "Р•РґРёРЅРѕРµ РєСЂРёРїС‚РѕРЅР°РїСЂР°РІР»РµРЅРёРµ TNC",
        "BLOCKCHAIN INTEGRATIONS вЂ” COMING",
        (
            "в‚ї <b>TNC CRYPTO</b>\n\n"
            "Р—РґРµСЃСЊ Р±СѓРґРµС‚ РѕС‚РґРµР»СЊРЅРѕРµ РЅР°РїСЂР°РІР»РµРЅРёРµ РґР»СЏ РєСЂРёРїС‚РѕРІР°Р»СЋС‚.\n"
            "Р’РЅРµС€РЅРёРµ Р±Р»РѕРєС‡РµР№РЅС‹ Рё СЂРµР°Р»СЊРЅС‹Рµ РєСЂРёРїС‚РѕРѕРїРµСЂР°С†РёРё РїРѕРєР° РЅРµ РїРѕРґРєР»СЋС‡РµРЅС‹."
        ),
    )


@dp.message(F.text == GAMES)
async def games_handler(message: Message):
    await send_section(
        message,
        "TNC GAMES",
        "GAME CENTER",
        "РРіСЂС‹, Р·Р°РґР°РЅРёСЏ Рё С‚СѓСЂРЅРёСЂС‹",
        "PLAY  вЂў  EARN  вЂў  COMPETE",
        (
            "рџЋ® <b>TNC GAMES</b>\n\n"
            "РРіСЂРѕРІРѕРµ РЅР°РїСЂР°РІР»РµРЅРёРµ Р±СѓРґРµС‚ СЂР°Р±РѕС‚Р°С‚СЊ РѕС‚РґРµР»СЊРЅРѕ "
            "Рё РёСЃРїРѕР»СЊР·РѕРІР°С‚СЊ РµРґРёРЅС‹Р№ TNC Account."
        ),
    )


# --------------------------------------------------
# COMMUNITY AND SETTINGS
# --------------------------------------------------

@dp.message(F.text == COMMUNITY)
async def community_handler(message: Message):
    me = await message.bot.get_me()

    await send_section(
        message,
        "TNC COMMUNITY",
        "JOIN THE COMMUNITY",
        "Р Р°Р·РІРёРІР°Р№ СЌРєРѕСЃРёСЃС‚РµРјСѓ РІРјРµСЃС‚Рµ СЃ РЅР°РјРё",
        "INVITE  вЂў  CONNECT  вЂў  GROW",
        (
            "рџ‘Ґ <b>TNC COMMUNITY</b>\n\n"
            f"РўРІРѕСЏ СЃСЃС‹Р»РєР°:\n"
            f"https://t.me/{me.username}?start=ref_{message.from_user.id}"
        ),
    )


@dp.message(F.text == SETTINGS)
async def settings_handler(message: Message):
    await send_section(
        message,
        "TNC SETTINGS",
        "PREFERENCES",
        "РќР°СЃС‚СЂРѕР№РєРё Р°РєРєР°СѓРЅС‚Р°",
        "ACCOUNT  вЂў  SECURITY  вЂў  NOTIFICATIONS",
        (
            "вљ™пёЏ <b>РќР°СЃС‚СЂРѕР№РєРё TNC</b>\n\n"
            "Р Р°Р·РґРµР» РїРѕРґРіРѕС‚РѕРІР»РµРЅ РґР»СЏ РїРѕРґРєР»СЋС‡РµРЅРёСЏ РЅР°СЃС‚СЂРѕРµРє СѓРІРµРґРѕРјР»РµРЅРёР№, "
            "Р±РµР·РѕРїР°СЃРЅРѕСЃС‚Рё Рё РїСЂРѕС„РёР»СЏ."
        ),
    )


@dp.message(F.text == MINI_APP)
async def miniapp_handler(message: Message):
    url = getattr(settings, "WEBAPP_URL", "") or ""

    if url.startswith("https://"):
        await message.answer(
            "РћС‚РєСЂРѕР№ Mini App РєРЅРѕРїРєРѕР№ РІ РіР»Р°РІРЅРѕРј РјРµРЅСЋ.",
            reply_markup=main_keyboard(),
        )
    else:
        await send_section(
            message,
            "TNC MINI APP",
            "WEB APP",
            "Р‘РѕР»СЊС€РѕРµ РїСЂРёР»РѕР¶РµРЅРёРµ TNC РіРѕС‚РѕРІРёС‚СЃСЏ",
            "HTTPS ADDRESS NOT CONNECTED",
            "рџЊђ <b>Mini App РµС‰С‘ РЅРµ РѕРїСѓР±Р»РёРєРѕРІР°РЅ.</b>",
        )


# --------------------------------------------------
# ADMIN OPERATIONS
# --------------------------------------------------

def is_admin(user_id):
    return int(user_id) in settings.ADMIN_IDS


@dp.message(Command("credit"))
async def admin_credit(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("в›” РќРµС‚ РґРѕСЃС‚СѓРїР°.")
        return

    parts = (message.text or "").split()

    if len(parts) != 3:
        await message.answer(
            "Р¤РѕСЂРјР°С‚: <code>/credit TELEGRAM_ID РЎРЈРњРњРђ</code>",
            parse_mode="HTML",
        )
        return

    try:
        target_id = int(parts[1])

        with SessionLocal() as db:
            tx = deposit(
                db,
                target_id,
                parts[2],
                description=f"Admin credit by {message.from_user.id}",
            )

        await send_operation_image(
            message.bot,
            target_id,
            tx.amount_units / 1_000_000,
            "deposit",
            "TNC WALLET",
            tx.operation_id,
            "рџ’› <b>РќР° С‚РІРѕР№ Р±Р°Р»Р°РЅСЃ Р·Р°С‡РёСЃР»РµРЅС‹ TNC.</b>",
        )

        await message.answer(
            "вњ… РџРѕРїРѕР»РЅРµРЅРёРµ РІС‹РїРѕР»РЅРµРЅРѕ.\n"
            f"РџРѕР»СѓС‡Р°С‚РµР»СЊ: <code>{target_id}</code>\n"
            f"РЎСѓРјРјР°: <b>{fmt(tx.amount_units)} TNC</b>",
            parse_mode="HTML",
            reply_markup=main_keyboard(),
        )

    except ValueError as error:
        await message.answer(f"вќЊ {html.escape(str(error))}")
    except Exception:
        logger.exception("Admin credit failed")
        await message.answer(
            "РћРїРµСЂР°С†РёСЏ РЅРµ РІС‹РїРѕР»РЅРµРЅР°. РџСЂРѕРІРµСЂСЊ ID РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ Рё РµРіРѕ РєРѕС€РµР»С‘Рє."
        )


@dp.message(Command("debit"))
async def admin_debit(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("в›” РќРµС‚ РґРѕСЃС‚СѓРїР°.")
        return

    parts = (message.text or "").split()

    if len(parts) != 3:
        await message.answer(
            "Р¤РѕСЂРјР°С‚: <code>/debit TELEGRAM_ID РЎРЈРњРњРђ</code>",
            parse_mode="HTML",
        )
        return

    try:
        target_id = int(parts[1])

        with SessionLocal() as db:
            tx = withdraw(
                db,
                target_id,
                parts[2],
                description=f"Admin debit by {message.from_user.id}",
            )

        await send_operation_image(
            message.bot,
            target_id,
            tx.amount_units / 1_000_000,
            "withdraw",
            "TNC WALLET",
            tx.operation_id,
            "вљ пёЏ <b>РЎ Р±Р°Р»Р°РЅСЃР° СЃРїРёСЃР°РЅС‹ TNC.</b>",
        )

        await message.answer(
            "вњ… РЎРїРёСЃР°РЅРёРµ РІС‹РїРѕР»РЅРµРЅРѕ.\n"
            f"РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ: <code>{target_id}</code>\n"
            f"РЎСѓРјРјР°: <b>{fmt(tx.amount_units)} TNC</b>",
            parse_mode="HTML",
            reply_markup=main_keyboard(),
        )

    except ValueError as error:
        await message.answer(f"вќЊ {html.escape(str(error))}")
    except Exception:
        logger.exception("Admin debit failed")
        await message.answer("РћРїРµСЂР°С†РёСЏ РЅРµ РІС‹РїРѕР»РЅРµРЅР°.")


# --------------------------------------------------
# --------------------------------------------------
# TNC SHOP вЂ” TELEGRAM STARS
# --------------------------------------------------

@dp.message(Command("shop"))
async def tnc_shop_handler(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 TNC вЂ” 50 в­ђ", callback_data="tnc_buy:1"),
            InlineKeyboardButton(text="10 TNC вЂ” 500 в­ђ", callback_data="tnc_buy:10"),
        ],
        [
            InlineKeyboardButton(text="100 TNC вЂ” 5 000 в­ђ", callback_data="tnc_buy:100"),
        ],
        [
            InlineKeyboardButton(text="1 000 TNC вЂ” 50 000 в­ђ", callback_data="tnc_buy:1000"),
        ],
    ])
    await message.answer(
        "рџ›Ќ <b>TNC SHOP</b>\n\n"
        "Р’С‹Р±РµСЂРё РїР°РєРµС‚ РїРѕРїРѕР»РЅРµРЅРёСЏ.\n"
        "РљСѓСЂСЃ: 1 TNC = 50 в­ђ\n\n"
        "Р‘Р°Р»Р°РЅСЃ Р±СѓРґРµС‚ РїРѕРїРѕР»РЅРµРЅ РїРѕСЃР»Рµ РїРѕРґС‚РІРµСЂР¶РґРµРЅРёСЏ РѕРїР»Р°С‚С‹ Telegram.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("tnc_buy:"))
async def tnc_buy_handler(callback: CallbackQuery):
    from app.services.stars import create_order

    try:
        package = int(callback.data.split(":", 1)[1])
        payload, stars = create_order(callback.from_user.id, package)

        await callback.message.answer_invoice(
            title=f"{package} TNC",
            description=f"РџРѕРїРѕР»РЅРµРЅРёРµ РІРЅСѓС‚СЂРµРЅРЅРµРіРѕ Р±Р°Р»Р°РЅСЃР° TNC РЅР° {package} РјРѕРЅРµС‚.",
            payload=payload,
            currency="XTR",
            prices=[LabeledPrice(label=f"{package} TNC", amount=stars)],
        )
        await callback.answer()
    except Exception:
        logger.exception("Could not create TNC Stars invoice")
        await callback.answer("РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕР·РґР°С‚СЊ СЃС‡С‘С‚. РџРѕРїСЂРѕР±СѓР№ РµС‰С‘ СЂР°Р·.", show_alert=True)


@dp.pre_checkout_query()
async def tnc_pre_checkout_handler(query: PreCheckoutQuery):
    payload = query.invoice_payload or ""

    if query.currency != "XTR":
        await query.answer(
            ok=False,
            error_message="Неверная валюта платежа."
        )
        return

    try:
        if payload.startswith("gt_"):
            from app.services.game_tokens import check_stars_order

            valid = check_stars_order(
                payload,
                query.from_user.id,
                query.total_amount,
            )
        else:
            from app.services.stars import check_order

            valid = check_order(
                payload,
                query.from_user.id,
                query.total_amount,
            )

        if valid:
            await query.answer(ok=True)
        else:
            await query.answer(
                ok=False,
                error_message="Заказ недействителен. Создай новый счёт."
            )
    except Exception:
        logger.exception("Stars pre-checkout validation failed")
        await query.answer(
            ok=False,
            error_message="Не удалось проверить заказ. Попробуй ещё раз."
        )


@dp.message(F.successful_payment)
async def tnc_successful_payment_handler(message: Message):
    payment = message.successful_payment
    payload = payment.invoice_payload or ""

    if payment.currency != "XTR":
        await message.answer(
            "Не удалось подтвердить валюту платежа. Обратись в поддержку."
        )
        return

    try:
        if payload.startswith("gt_"):
            from app.services.game_tokens import complete_stars_payment

            result = complete_stars_payment(
                payload=payload,
                user_id=message.from_user.id,
                stars=payment.total_amount,
                charge_id=payment.telegram_payment_charge_id,
            )

            if result["already_processed"]:
                await message.answer(
                    "Этот платёж уже был обработан. Повторного начисления нет."
                )
                return

            await message.answer(
                "✅ <b>Покупка Game Tokens успешна!</b>\n\n"
                f"Начислено: <b>{result['tokens']:,} GT</b>\n"
                f"Оплачено: <b>{payment.total_amount} ⭐</b>\n\n"
                "Игровой баланс обновлён.",
                parse_mode="HTML",
            )
            return

        from app.services.stars import complete_payment

        credited = complete_payment(
            payload=payload,
            user_id=message.from_user.id,
            stars_amount=payment.total_amount,
            charge_id=payment.telegram_payment_charge_id,
        )

        if credited:
            await message.answer(
                "✅ <b>Оплата прошла успешно!</b>\n\n"
                "TNC зачислены на твой баланс.\n"
                "Проверить баланс можно в разделе «Кошелёк».",
                parse_mode="HTML",
            )
        else:
            await message.answer(
                "Этот платёж уже обработан или заказ недействителен. "
                "Если баланс не обновился, обратись в поддержку."
            )

    except Exception:
        logger.exception("Telegram Stars payment processing failed")
        await message.answer(
            "Telegram подтвердил оплату, но зачисление требует проверки. "
            "Не оплачивай повторно — обратись в поддержку."
        )

# --------------------------------------------------
# TNC GAMES ADMIN COMMANDS
# --------------------------------------------------

@dp.message(Command("gt_add"))
async def gt_admin_add(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    parts = (message.text or "").split(maxsplit=3)
    if len(parts) < 3:
        await message.answer(
            "Использование:\n/gt_add USER_ID AMOUNT [причина]"
        )
        return

    try:
        from app.services.game_tokens import admin_adjust_tokens

        user_id = int(parts[1])
        amount = int(parts[2])
        reason = parts[3] if len(parts) > 3 else "Выдано администратором"

        new_balance = admin_adjust_tokens(
            message.from_user.id,
            user_id,
            amount,
            "admin_add",
            reason,
        )
        await message.answer(
            "✅ <b>GT начислены</b>\n"
            f"Игрок: <code>{user_id}</code>\n"
            f"Начислено: <b>{amount:,} GT</b>\n"
            f"Новый баланс: <b>{new_balance:,} GT</b>",
            parse_mode="HTML",
        )
    except (ValueError, TypeError) as error:
        await message.answer(f"Ошибка: {error}")
    except Exception:
        logger.exception("Admin GT credit failed")
        await message.answer("Не удалось начислить GT. Проверь журнал сервера.")


@dp.message(Command("gt_take"))
async def gt_admin_take(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    parts = (message.text or "").split(maxsplit=3)
    if len(parts) < 3:
        await message.answer(
            "Использование:\n/gt_take USER_ID AMOUNT [причина]"
        )
        return

    try:
        from app.services.game_tokens import admin_adjust_tokens

        user_id = int(parts[1])
        amount = int(parts[2])
        reason = parts[3] if len(parts) > 3 else "Списано администратором"

        new_balance = admin_adjust_tokens(
            message.from_user.id,
            user_id,
            amount,
            "admin_take",
            reason,
        )
        await message.answer(
            "✅ <b>GT списаны</b>\n"
            f"Игрок: <code>{user_id}</code>\n"
            f"Списано: <b>{amount:,} GT</b>\n"
            f"Новый баланс: <b>{new_balance:,} GT</b>",
            parse_mode="HTML",
        )
    except (ValueError, TypeError) as error:
        await message.answer(f"Ошибка: {error}")
    except Exception:
        logger.exception("Admin GT debit failed")
        await message.answer("Не удалось списать GT. Проверь журнал сервера.")


@dp.message(Command("gt_balance"))
async def gt_admin_balance(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("Использование:\n/gt_balance USER_ID")
        return

    try:
        from app.services.game_tokens import get_balance

        user_id = int(parts[1])
        amount = get_balance(user_id)
        await message.answer(
            f"Игрок: <code>{user_id}</code>\n"
            f"Баланс: <b>{amount:,} GT</b>",
            parse_mode="HTML",
        )
    except ValueError:
        await message.answer("Некорректный Telegram ID.")
    except Exception:
        logger.exception("Admin GT balance lookup failed")
        await message.answer("Не удалось получить баланс.")


@dp.message(Command("gameban"))
async def gt_admin_ban(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        await message.answer(
            "Использование:\n/gameban USER_ID [причина]"
        )
        return

    try:
        from app.services.game_tokens import set_game_ban

        user_id = int(parts[1])
        reason = parts[2] if len(parts) > 2 else "Блокировка администратором"
        set_game_ban(message.from_user.id, user_id, True, reason)

        await message.answer(
            f"🔒 Игрок <code>{user_id}</code> заблокирован в TNC Games.",
            parse_mode="HTML",
        )
    except ValueError:
        await message.answer("Некорректный Telegram ID.")
    except Exception:
        logger.exception("Game ban failed")
        await message.answer("Не удалось заблокировать игрока.")


@dp.message(Command("gameunban"))
async def gt_admin_unban(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        await message.answer(
            "Использование:\n/gameunban USER_ID [причина]"
        )
        return

    try:
        from app.services.game_tokens import set_game_ban

        user_id = int(parts[1])
        reason = parts[2] if len(parts) > 2 else "Разблокировка администратором"
        set_game_ban(message.from_user.id, user_id, False, reason)

        await message.answer(
            f"🔓 Игрок <code>{user_id}</code> разблокирован в TNC Games.",
            parse_mode="HTML",
        )
    except ValueError:
        await message.answer("Некорректный Telegram ID.")
    except Exception:
        logger.exception("Game unban failed")
        await message.answer("Не удалось разблокировать игрока.")


@dp.message(Command("gt_admin_log"))
async def gt_admin_log_handler(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    try:
        from app.services.game_tokens import get_admin_log

        rows = get_admin_log(20)
        if not rows:
            await message.answer("Журнал административных действий пока пуст.")
            return

        lines = ["<b>Журнал TNC Games — последние 20 действий</b>"]
        for row in rows:
            lines.append(
                f"\n<code>{row['action']}</code>"
                f"\nАдмин: <code>{row['admin_id']}</code>"
                f" → Игрок: <code>{row['user_id']}</code>"
                f"\nКоличество: <b>{row['amount']:,} GT</b>"
                f"\nПричина: {row['reason'] or '—'}"
            )

        await message.answer("\n".join(lines), parse_mode="HTML")
    except Exception:
        logger.exception("Game admin log failed")
        await message.answer("Не удалось загрузить журнал.")


# UNKNOWN MESSAGE
# --------------------------------------------------

@dp.message()
async def unknown_handler(message: Message):
    await message.answer(
        "РќРµ РїРѕРЅСЏР» РєРѕРјР°РЅРґСѓ. РСЃРїРѕР»СЊР·СѓР№ РєРЅРѕРїРєРё РјРµРЅСЋ РЅРёР¶Рµ РёР»Рё /help.",
        reply_markup=main_keyboard(),
    )


# --------------------------------------------------
# STARTUP
# --------------------------------------------------

async def main():
    if not settings.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN РЅРµ РЅР°СЃС‚СЂРѕРµРЅ.")

    if not settings.ADMIN_IDS:
        logger.warning(
            "ADMIN_IDS РїСѓСЃС‚. РљРѕРјР°РЅРґС‹ /credit Рё /debit РЅРµРґРѕСЃС‚СѓРїРЅС‹."
        )

    init_database()

    bot = Bot(token=settings.BOT_TOKEN)

    logger.info("TNC Wallet is starting...")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())


