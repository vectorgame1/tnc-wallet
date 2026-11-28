from aiogram.types import LabeledPrice, PreCheckoutQuery

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

WALLET = "Кошелёк TNC"
TRANSFER = "Перевести TNC"
HISTORY = "История операций"
ACCOUNT = "Мой аккаунт"
GT_BALANCE = "Баланс GT"
SHOP = "Магазин TNC"
COMMUNITY = "Реферальная ссылка"
MINI_APP = "Открыть приложение"
CANCEL = "Отмена"
BACK = "Главное меню"
SHOP_1 = "Пакет 1 TNC — 50 Stars"
SHOP_10 = "Пакет 10 TNC — 500 Stars"
SHOP_100 = "Пакет 100 TNC — 5 000 Stars"
SHOP_1000 = "Пакет 1 000 TNC — 50 000 Stars"
TRANSFER_CONFIRM = "Подтвердить перевод"


class TransferFlow(StatesGroup):
    receiver = State()
    amount = State()
    confirm = State()


def main_keyboard():
    """В меню остаются только реализованные функции."""
    rows = []
    webapp_url = (getattr(settings, "WEBAPP_URL", "") or "").strip()

    if webapp_url.startswith("https://"):
        rows.append([
            KeyboardButton(
                text=MINI_APP,
                web_app=WebAppInfo(url=webapp_url),
            )
        ])

    rows.extend([
        [KeyboardButton(text=WALLET), KeyboardButton(text=TRANSFER)],
        [KeyboardButton(text=HISTORY), KeyboardButton(text=ACCOUNT)],
        [KeyboardButton(text=GT_BALANCE), KeyboardButton(text=SHOP)],
        [KeyboardButton(text=COMMUNITY)],
    ])

    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выбери действие TNC",
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


def shop_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=SHOP_1), KeyboardButton(text=SHOP_10)],
            [KeyboardButton(text=SHOP_100)],
            [KeyboardButton(text=SHOP_1000)],
            [KeyboardButton(text=BACK)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выбери пакет пополнения TNC",
    )


def transfer_confirm_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=TRANSFER_CONFIRM)],
            [KeyboardButton(text=CANCEL)],
            [KeyboardButton(text=BACK)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Подтверди или отмени перевод",
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
    safe_caption = caption or (
        f"<b>{html.escape(title)}</b>\\n\\n{html.escape(subtitle)}"
    )
    try:
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
            caption=safe_caption,
            reply_markup=main_keyboard(),
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Section image rendering failed: %s", section)
        await message.answer(
            safe_caption,
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
    try:
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
    except Exception:
        logger.exception("Transaction image rendering failed: %s", operation)
        await bot.send_message(
            chat_id=chat_id,
            text=caption or (
                f"<b>{html.escape(operation.title())}</b>\\n"
                f"Сумма: <b>{amount:g} TNC</b>\\n"
                f"Операция: <code>{html.escape(operation_id)}</code>"
            ),
            parse_mode="HTML",
        )


async def show_home(message: Message, greeting=True):
    if greeting:
        name = html.escape(message.from_user.first_name or "User")
        caption = (
            f" <b>Добро пожаловать в TNC, {name}!</b>\n\n"
            "Твой единый аккаунт цифровой экосистемы.\n"
            "Выбирай раздел с помощью клавиатуры ниже."
        )
    else:
        caption = (
            " <b>TNC ECOSYSTEM</b>\n\n"
            "Главное меню. Выбери нужный раздел."
        )

    await send_section(
        message,
        "TNC ECOSYSTEM",
        "WELCOME TO TNC",
        "YOUR ACCOUNT. YOUR ECOSYSTEM.",
        "WALLET  •  TRANSFERS  •  ACCOUNT",
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
            "<b>Помощь TNC</b>\n\n"
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
                " <b>TNC WALLET</b>\n\n"
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
# GAME TOKEN BALANCE
# --------------------------------------------------

@dp.message(F.text == GT_BALANCE)
async def gt_balance_handler(message: Message):
    try:
        ensure_user(message.from_user)
        from app.services.game_tokens import get_balance

        amount = get_balance(message.from_user.id)
        await send_section(
            message,
            "TNC GAMES",
            "GAME TOKEN BALANCE",
            f"{amount:,} GT",
            "CLOSED-LOOP GAME POINTS",
            (
                "<b>Баланс игровых токенов</b>\\n\\n"
                f"Доступно: <b>{amount:,} GT</b>\\n\\n"
                "GT используются внутри игрового раздела. "
                "Они не являются TNC Coin и не выводятся как деньги."
            ),
        )
    except Exception:
        logger.exception("User GT balance screen failed")
        await message.answer(
            "Не удалось загрузить баланс GT. Попробуй позже.",
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
            " <b>Новый перевод</b>\n\n"
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
        from decimal import Decimal, InvalidOperation
        amount_value = Decimal(amount_text)
        if not amount_value.is_finite() or amount_value <= 0:
            raise InvalidOperation
        if amount_value > Decimal("1000000"):
            await message.answer("Максимальная сумма одного перевода — 1 000 000 TNC.")
            return
        if amount_value.as_tuple().exponent < -6:
            await message.answer("Максимальная точность суммы — 6 знаков после запятой.")
            return
    except (InvalidOperation, ValueError):
        await message.answer("Введи корректную сумму, например 25 или 125.50.")
        return

    try:
        with SessionLocal() as db:
            current_balance = Decimal(str(balance(db, message.from_user.id)))
        if amount_value * Decimal("1000000") > current_balance:
            await message.answer("Недостаточно средств. Проверь баланс кошелька.")
            return
    except Exception:
        logger.exception("Could not validate transfer balance")
        await message.answer("Не удалось проверить баланс. Попробуй позже.")
        return

    await state.update_data(amount=amount_text)
    await state.set_state(TransferFlow.confirm)
    await send_section(
        message,
        "TNC TRANSFER",
        "CONFIRM TRANSFER",
        f"{amount_text} TNC",
        f"RECIPIENT ID: {receiver_id}",
        (
            "<b>Проверь перевод перед списанием</b>\n\n"
            f"Получатель: <code>{receiver_id}</code>\n"
            f"Сумма: <b>{html.escape(amount_text)} TNC</b>\n\n"
            "Средства будут списаны только после подтверждения."
        ),
    )
    await message.answer(
        "Подтверди перевод или отмени операцию.",
        reply_markup=transfer_confirm_keyboard(),
    )


@dp.message(TransferFlow.confirm)
async def transfer_confirm(message: Message, state: FSMContext):
    if message.text in (CANCEL, BACK):
        await state.clear()
        await show_home(message, greeting=False)
        return
    if message.text != TRANSFER_CONFIRM:
        await message.answer("Нажми «Подтвердить перевод» или «Отмена».", reply_markup=transfer_confirm_keyboard())
        return

    data = await state.get_data()
    receiver_id = data.get("receiver_id")
    amount_text = data.get("amount")
    if not receiver_id or not amount_text:
        await state.clear()
        await message.answer("Данные перевода устарели. Начни заново.", reply_markup=main_keyboard())
        return

    # Prevent a second submission while the operation is executing.
    await state.clear()
    try:
        with SessionLocal() as db:
            transaction = send(db, message.from_user.id, receiver_id, amount_text)

        amount = transaction.amount_units / 1_000_000
        operation_id = transaction.operation_id
        await send_operation_image(
            message.bot, message.from_user.id, amount, "sent",
            message.from_user.first_name or "TNC USER", operation_id,
            ("<b>Перевод выполнен</b>\n\n"
             f"Получатель: <code>{receiver_id}</code>\n"
             f"Сумма: <b>{fmt(transaction.amount_units)} TNC</b>\n"
             f"Операция: <code>{html.escape(str(operation_id))}</code>"),
        )
        try:
            with SessionLocal() as db:
                recipient = db.get(User, receiver_id)
                recipient_name = recipient.first_name if recipient else "TNC USER"
            await send_operation_image(
                message.bot, receiver_id, amount, "received", recipient_name,
                operation_id,
                ("<b>Получен перевод TNC</b>\n\n"
                 f"Отправитель: <code>{message.from_user.id}</code>\n"
                 f"Сумма: <b>{fmt(transaction.amount_units)} TNC</b>\n"
                 f"Операция: <code>{html.escape(str(operation_id))}</code>"),
            )
        except Exception:
            logger.exception("Could not notify transfer recipient")
        await message.answer("Операция завершена. Главное меню ниже.", reply_markup=main_keyboard())
    except ValueError as error:
        await send_section(message, "TNC TRANSFER", "TRANSFER FAILED", "Операция не выполнена", "Проверь данные", html.escape(str(error)))
    except Exception:
        logger.exception("Transfer failed")
        await send_section(message, "TNC TRANSFER", "TRANSFER ERROR", "Не удалось выполнить перевод", "Проверь историю перед повтором", "Не удалось подтвердить результат. Не отправляй перевод повторно, пока не проверишь историю операций.")


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
            " <b>История TNC Wallet</b>",
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
                icon = ""
                label = "Пополнение"
                sign = "+"
            elif tx.kind == "withdraw":
                icon = ""
                label = "Списание"
                sign = "−"
            elif outgoing:
                icon = "↗"
                label = "Отправлено"
                sign = "−"
            else:
                icon = "↙"
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
                " <b>Твой TNC Account</b>\n\n"
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
# COMMUNITY
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
            " <b>TNC COMMUNITY</b>\n\n"
            f"Твоя ссылка:\n"
            f"https://t.me/{me.username}?start=ref_{message.from_user.id}"
        ),
    )


@dp.message(F.text == MINI_APP)
async def miniapp_handler(message: Message):
    url = (getattr(settings, "WEBAPP_URL", "") or "").strip()
    if url.startswith("https://"):
        await message.answer(
            "Открой приложение через кнопку в главном меню.",
            reply_markup=main_keyboard(),
        )
    else:
        await message.answer(
            "Веб-приложение пока не опубликовано. "
            "Кошелёк, переводы и история доступны прямо в боте.",
            reply_markup=main_keyboard(),
        )


# --------------------------------------------------
# ADMIN OPERATIONS
# --------------------------------------------------

def is_admin(user_id):
    return int(user_id) in settings.ADMIN_IDS


@dp.message(Command("admin"))
async def admin_panel_handler(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.")
        return

    await send_section(
        message,
        "TNC ADMIN",
        "ADMIN CONTROL CENTER",
        "Управление аккаунтами и игровыми ограничениями",
        "TNC  •  GT  •  AUDIT",
        (
            "<b>Административная панель</b>\n\n"
            "<code>/credit USER_ID AMOUNT</code> — начислить TNC\n"
            "<code>/debit USER_ID AMOUNT</code> — списать TNC\n"
            "<code>/gt_add USER_ID AMOUNT [reason]</code> — начислить GT\n"
            "<code>/gt_take USER_ID AMOUNT [reason]</code> — списать GT\n"
            "<code>/gt_balance USER_ID</code> — проверить GT\n"
            "<code>/gameban USER_ID [reason]</code> — запретить игры\n"
            "<code>/gameunban USER_ID [reason]</code> — снять запрет\n"
            "<code>/gt_admin_log</code> — журнал действий"
        ),
    )


@dp.message(Command("credit"))
async def admin_credit(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(" Нет доступа.")
        return

    parts = (message.text or "").split()

    if len(parts)!= 3:
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
            " <b>На твой баланс зачислены TNC.</b>",
        )

        await message.answer(
            " Пополнение выполнено.\n"
            f"Получатель: <code>{target_id}</code>\n"
            f"Сумма: <b>{fmt(tx.amount_units)} TNC</b>",
            parse_mode="HTML",
            reply_markup=main_keyboard(),
        )

    except ValueError as error:
        await message.answer(f" {html.escape(str(error))}")
    except Exception:
        logger.exception("Admin credit failed")
        await message.answer(
            "Операция не выполнена. Проверь ID пользователя и его кошелёк."
        )


@dp.message(Command("debit"))
async def admin_debit(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(" Нет доступа.")
        return

    parts = (message.text or "").split()

    if len(parts)!= 3:
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
            " <b>С баланса списаны TNC.</b>",
        )

        await message.answer(
            " Списание выполнено.\n"
            f"Пользователь: <code>{target_id}</code>\n"
            f"Сумма: <b>{fmt(tx.amount_units)} TNC</b>",
            parse_mode="HTML",
            reply_markup=main_keyboard(),
        )

    except ValueError as error:
        await message.answer(f" {html.escape(str(error))}")
    except Exception:
        logger.exception("Admin debit failed")
        await message.answer("Операция не выполнена.")


# --------------------------------------------------
# --------------------------------------------------
# TNC SHOP — TELEGRAM STARS
# --------------------------------------------------

@dp.message(F.text == SHOP)
async def tnc_shop_button_handler(message: Message):
    await tnc_shop_handler(message)


@dp.message(Command("shop"))
async def tnc_shop_handler(message: Message):
    await send_section(
        message,
        "TNC SHOP",
        "CHOOSE YOUR PACKAGE",
        "Пополнение внутреннего баланса TNC",
        "1 TNC = 50 Telegram Stars",
        (
            "<b>Магазин TNC</b>\n\n"
            "Выбери пакет кнопкой внизу.\n\n"
            "1 TNC — 50 Stars\n"
            "10 TNC — 500 Stars\n"
            "100 TNC — 5 000 Stars\n"
            "1 000 TNC — 50 000 Stars\n\n"
            "Баланс зачисляется после подтверждения успешного платежа Telegram."
        ),
    )
    await message.answer("Выбери пакет пополнения:", reply_markup=shop_keyboard())


async def create_tnc_invoice(message: Message, package: int):
    from app.services.stars import create_order
    try:
        payload, stars = create_order(message.from_user.id, package)
        expected = package * 50
        if int(stars) != expected:
            raise ValueError("Стоимость заказа не совпадает с тарифом магазина.")
        await message.answer_invoice(
            title=f"{package:,} TNC",
            description=f"Пополнение внутреннего баланса TNC на {package:,} монет.",
            payload=payload,
            currency="XTR",
            prices=[LabeledPrice(label=f"{package:,} TNC", amount=int(stars))],
        )
    except Exception:
        logger.exception("Could not create TNC Stars invoice")
        await message.answer("Не удалось создать счёт. Попробуй позже.", reply_markup=shop_keyboard())


@dp.message(F.text.in_({SHOP_1, SHOP_10, SHOP_100, SHOP_1000}))
async def tnc_shop_package_handler(message: Message):
    packages = {SHOP_1: 1, SHOP_10: 10, SHOP_100: 100, SHOP_1000: 1000}
    await create_tnc_invoice(message, packages[message.text])


@dp.pre_checkout_query()
async def tnc_pre_checkout_handler(query: PreCheckoutQuery):
    payload = query.invoice_payload or ""

    if query.currency!= "XTR":
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

    if payment.currency!= "XTR":
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
                " <b>Покупка Game Tokens успешна!</b>\n\n"
                f"Начислено: <b>{result['tokens']:,} GT</b>\n"
                f"Оплачено: <b>{payment.total_amount} Stars</b>\n\n"
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
                " <b>Оплата прошла успешно!</b>\n\n"
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
        await message.answer(" Нет доступа.")
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
            " <b>GT начислены</b>\n"
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
        await message.answer(" Нет доступа.")
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
            " <b>GT списаны</b>\n"
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
        await message.answer(" Нет доступа.")
        return

    parts = (message.text or "").split()
    if len(parts)!= 2:
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
        await message.answer(" Нет доступа.")
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
            f" Игрок <code>{user_id}</code> заблокирован в TNC Games.",
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
        await message.answer(" Нет доступа.")
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
            f" Игрок <code>{user_id}</code> разблокирован в TNC Games.",
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
        await message.answer(" Нет доступа.")
        return

    try:
        from app.services.game_tokens import get_admin_log

        rows = get_admin_log(20)
        await send_section(
            message,
            "TNC ADMIN AUDIT",
            "ADMIN ACTIVITY LOG",
            "Последние административные операции",
            f"{len(rows)} записей",
            "Журнал действий администраторов TNC Games.",
        )
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

    logger.info("TNC Bot is starting...")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())