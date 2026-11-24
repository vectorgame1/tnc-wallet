
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

WALLET = "💎 Кошелёк"
TRANSFER = "💸 Перевести TNC"
HISTORY = "📊 История"
ACCOUNT = "👤 Аккаунт"
CRYPTO = "₿ TNC Crypto"
GAMES = "🎮 TNC Games"
COMMUNITY = "👥 Community"
SETTINGS = "⚙️ Настройки"
MINI_APP = "🌐 Открыть Mini App"
CANCEL = "❌ Отмена"
BACK = "⬅️ Главное меню"


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
        input_field_placeholder="Выбери раздел TNC",
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
            f"💎 <b>Добро пожаловать в TNC, {name}!</b>\n\n"
            "Твой единый аккаунт цифровой экосистемы.\n"
            "Выбирай раздел с помощью клавиатуры ниже."
        )
    else:
        caption = (
            "💎 <b>TNC ECOSYSTEM</b>\n\n"
            "Главное меню. Выбери нужный раздел."
        )

    await send_section(
        message,
        "TNC ECOSYSTEM",
        "WELCOME TO TNC",
        "YOUR ACCOUNT. YOUR ECOSYSTEM.",
        "WALLET  •  CRYPTO  •  GAMES",
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
        "Команды и возможности TNC Wallet",
        "/start  •  /menu  •  /help",
        (
            "ℹ️ <b>Помощь TNC</b>\n\n"
            "/start — запуск аккаунта\n"
            "/menu — главное меню\n"
            "/help — помощь\n\n"
            "Для перевода получатель должен запустить бота.\n"
            "TNC Coin — внутренняя учётная валюта экосистемы."
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
                "💎 <b>TNC WALLET</b>\n\n"
                f"Доступный баланс: <b>{current_balance} TNC</b>\n\n"
                "Здесь отображаются внутренние средства твоего аккаунта."
            ),
        )
    except Exception:
        logger.exception("Wallet screen failed")
        await message.answer(
            "Не удалось открыть кошелёк. Попробуй ещё раз.",
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
        "Быстрый внутренний перевод",
        "RECIPIENT  →  AMOUNT  →  CONFIRMATION",
        (
            "💸 <b>Новый перевод</b>\n\n"
            "Введи Telegram ID получателя.\n"
            "Получатель должен предварительно запустить TNC Wallet."
        ),
    )

    await message.answer(
        "Отправь Telegram ID получателя или нажми «Отмена».",
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
        await message.answer("Введи корректный числовой Telegram ID.")
        return

    if receiver_id == message.from_user.id:
        await message.answer("Нельзя отправить перевод самому себе.")
        return

    await state.update_data(receiver_id=receiver_id)
    await state.set_state(TransferFlow.amount)

    await send_section(
        message,
        "TNC TRANSFER",
        "TRANSFER AMOUNT",
        "Укажи сумму в TNC",
        "MAXIMUM: 1 000 000 TNC",
        f"Получатель: <code>{receiver_id}</code>\n\nТеперь введи сумму перевода.",
    )

    await message.answer(
        "Например: 25 или 125.50",
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
                "✅ <b>Перевод выполнен</b>\n\n"
                f"Получатель: <code>{receiver_id}</code>\n"
                f"Операция: <code>{operation_id}</code>"
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
                    "💛 <b>Ты получил перевод TNC!</b>\n\n"
                    f"Отправитель: <code>{message.from_user.id}</code>\n"
                    f"Операция: <code>{operation_id}</code>"
                ),
            )
        except Exception:
            logger.exception("Could not notify transfer recipient")

        await message.answer(
            "Главное меню доступно ниже.",
            reply_markup=main_keyboard(),
        )

    except ValueError as error:
        await state.clear()
        await message.answer(
            f"❌ {html.escape(str(error))}",
            reply_markup=main_keyboard(),
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Transfer failed")
        await state.clear()
        await message.answer(
            "Не удалось выполнить перевод. Попробуй позже.",
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
            "Все операции твоего аккаунта",
            f"{len(transactions)} последних записей",
            "📊 <b>История TNC Wallet</b>",
        )

        if not transactions:
            await message.answer(
                "Пока нет операций.",
                reply_markup=main_keyboard(),
            )
            return

        lines = ["<b>Последние операции:</b>\n"]

        for tx in transactions:
            outgoing = tx.sender_id == message.from_user.id

            if tx.kind == "deposit":
                icon = "🟢"
                label = "Пополнение"
                sign = "+"
            elif tx.kind == "withdraw":
                icon = "🔴"
                label = "Списание"
                sign = "−"
            elif outgoing:
                icon = "↗️"
                label = "Отправлено"
                sign = "−"
            else:
                icon = "↙️"
                label = "Получено"
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
        await message.answer("Не удалось загрузить историю.")


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
            else "Не указан"
        )

        await send_section(
            message,
            "TNC ACCOUNT",
            "YOUR PROFILE",
            html.escape(user.first_name),
            f"ID: {user.telegram_id}",
            (
                "👤 <b>Твой TNC Account</b>\n\n"
                f"Имя: {html.escape(user.first_name)}\n"
                f"Username: {username}\n"
                f"Telegram ID: <code>{user.telegram_id}</code>\n"
                f"Баланс: <b>{current_balance} TNC</b>"
            ),
        )

    except Exception:
        logger.exception("Account screen failed")
        await message.answer("Не удалось открыть аккаунт.")


# --------------------------------------------------
# CRYPTO AND GAMES
# --------------------------------------------------

@dp.message(F.text == CRYPTO)
async def crypto_handler(message: Message):
    await send_section(
        message,
        "TNC CRYPTO",
        "CRYPTO HUB",
        "Единое криптонаправление TNC",
        "BLOCKCHAIN INTEGRATIONS — COMING",
        (
            "₿ <b>TNC CRYPTO</b>\n\n"
            "Здесь будет отдельное направление для криптовалют.\n"
            "Внешние блокчейны и реальные криптооперации пока не подключены."
        ),
    )


@dp.message(F.text == GAMES)
async def games_handler(message: Message):
    await send_section(
        message,
        "TNC GAMES",
        "GAME CENTER",
        "Игры, задания и турниры",
        "PLAY  •  EARN  •  COMPETE",
        (
            "🎮 <b>TNC GAMES</b>\n\n"
            "Игровое направление будет работать отдельно "
            "и использовать единый TNC Account."
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
        "Развивай экосистему вместе с нами",
        "INVITE  •  CONNECT  •  GROW",
        (
            "👥 <b>TNC COMMUNITY</b>\n\n"
            f"Твоя ссылка:\n"
            f"https://t.me/{me.username}?start=ref_{message.from_user.id}"
        ),
    )


@dp.message(F.text == SETTINGS)
async def settings_handler(message: Message):
    await send_section(
        message,
        "TNC SETTINGS",
        "PREFERENCES",
        "Настройки аккаунта",
        "ACCOUNT  •  SECURITY  •  NOTIFICATIONS",
        (
            "⚙️ <b>Настройки TNC</b>\n\n"
            "Раздел подготовлен для подключения настроек уведомлений, "
            "безопасности и профиля."
        ),
    )


@dp.message(F.text == MINI_APP)
async def miniapp_handler(message: Message):
    url = getattr(settings, "WEBAPP_URL", "") or ""

    if url.startswith("https://"):
        await message.answer(
            "Открой Mini App кнопкой в главном меню.",
            reply_markup=main_keyboard(),
        )
    else:
        await send_section(
            message,
            "TNC MINI APP",
            "WEB APP",
            "Большое приложение TNC готовится",
            "HTTPS ADDRESS NOT CONNECTED",
            "🌐 <b>Mini App ещё не опубликован.</b>",
        )


# --------------------------------------------------
# ADMIN OPERATIONS
# --------------------------------------------------

def is_admin(user_id):
    return int(user_id) in settings.ADMIN_IDS


@dp.message(Command("credit"))
async def admin_credit(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    parts = (message.text or "").split()

    if len(parts) != 3:
        await message.answer(
            "Формат: <code>/credit TELEGRAM_ID СУММА</code>",
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
            "💛 <b>На твой баланс зачислены TNC.</b>",
        )

        await message.answer(
            "✅ Пополнение выполнено.\n"
            f"Получатель: <code>{target_id}</code>\n"
            f"Сумма: <b>{fmt(tx.amount_units)} TNC</b>",
            parse_mode="HTML",
            reply_markup=main_keyboard(),
        )

    except ValueError as error:
        await message.answer(f"❌ {html.escape(str(error))}")
    except Exception:
        logger.exception("Admin credit failed")
        await message.answer(
            "Операция не выполнена. Проверь ID пользователя и его кошелёк."
        )


@dp.message(Command("debit"))
async def admin_debit(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    parts = (message.text or "").split()

    if len(parts) != 3:
        await message.answer(
            "Формат: <code>/debit TELEGRAM_ID СУММА</code>",
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
            "⚠️ <b>С баланса списаны TNC.</b>",
        )

        await message.answer(
            "✅ Списание выполнено.\n"
            f"Пользователь: <code>{target_id}</code>\n"
            f"Сумма: <b>{fmt(tx.amount_units)} TNC</b>",
            parse_mode="HTML",
            reply_markup=main_keyboard(),
        )

    except ValueError as error:
        await message.answer(f"❌ {html.escape(str(error))}")
    except Exception:
        logger.exception("Admin debit failed")
        await message.answer("Операция не выполнена.")


# --------------------------------------------------
# UNKNOWN MESSAGE
# --------------------------------------------------

@dp.message()
async def unknown_handler(message: Message):
    await message.answer(
        "Не понял команду. Используй кнопки меню ниже или /help.",
        reply_markup=main_keyboard(),
    )


# --------------------------------------------------
# STARTUP
# --------------------------------------------------

async def main():
    if not settings.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не настроен.")

    if not settings.ADMIN_IDS:
        logger.warning(
            "ADMIN_IDS пуст. Команды /credit и /debit недоступны."
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
