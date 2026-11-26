
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
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    LabeledPrice,
    PreCheckoutQuery,
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
from app.services.transaction_image import create_transaction_image


# ============================================================
# CONFIGURATION
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("tnc.bot")
dp = Dispatcher(storage=MemoryStorage())

BRAND = "TNC ECOSYSTEM"
HISTORY_PAGE_SIZE = 5

TNC_PACKAGES = {
    1: 50,
    10: 500,
    100: 5000,
    1000: 50000,
}

# ============================================================
# FSM STATES
# ============================================================

class TransferFlow(StatesGroup):
    receiver = State()
    amount = State()
    confirm = State()


# ============================================================
# COMMON HELPERS
# ============================================================

def esc(value):
    return html.escape(str(value or ""))


def is_admin(user_id):
    try:
        return int(user_id) in settings.ADMIN_IDS
    except (TypeError, ValueError):
        return False


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


def button(text, callback):
    return InlineKeyboardButton(
        text=text,
        callback_data=callback,
    )


def navigation_keyboard(back="home"):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                button("НАЗАД", f"nav:{back}"),
                button("ГЛАВНОЕ МЕНЮ", "nav:home"),
            ]
        ]
    )


async def edit_screen(callback, text, keyboard):
    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    except Exception as error:
        # Telegram сообщает об ошибке, если сообщение не изменилось.
        if "message is not modified" not in str(error).lower():
            logger.exception("Could not edit screen")
            await callback.message.answer(
                text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )


async def answer_screen(callback, text, keyboard):
    await edit_screen(callback, text, keyboard)
    await callback.answer()


async def send_operation_image(
    bot,
    chat_id,
    amount,
    operation,
    username,
    operation_id="",
    caption="",
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
        logger.exception(
            "Transaction image rendering failed: %s",
            operation,
        )

        if caption:
            await bot.send_message(
                chat_id=chat_id,
                text=caption,
                parse_mode="HTML",
            )


# ============================================================
# MAIN MENU
# ============================================================

def main_keyboard(user_id=None):
    rows = [
        [
            button("МОЙ КОШЕЛЁК", "nav:wallet"),
            button("ПЕРЕВЕСТИ TNC", "nav:transfer"),
        ],
        [
            button("ИСТОРИЯ ОПЕРАЦИЙ", "nav:history:0"),
        ],
        [
            button("МОЙ ПРОФИЛЬ", "nav:account"),
            button("БАЛАНС GT", "nav:gt"),
        ],
        [
            button("МАГАЗИН", "nav:shop"),
            button("РЕФЕРАЛЬНАЯ ПРОГРАММА", "nav:community"),
        ],
        [
            button("ЦЕНТР ПОМОЩИ", "nav:help"),
        ],
    ]

    url = (
        getattr(settings, "WEBAPP_URL", "") or ""
    ).strip()

    if url.startswith("https://"):
        rows.insert(
            0,
            [
                InlineKeyboardButton(
                    text="ОТКРЫТЬ TNC APP",
                    web_app=WebAppInfo(url=url),
                )
            ],
        )

    if user_id is not None and is_admin(user_id):
        rows.append([
            button("АДМИНИСТРАТИВНАЯ ПАНЕЛЬ", "nav:admin"),
        ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def transfer_cancel_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [button("ОТМЕНИТЬ ПЕРЕВОД", "transfer:cancel")],
            [button("ГЛАВНОЕ МЕНЮ", "nav:home")],
        ]
    )


async def show_home(message, greeting=True):
    try:
        ensure_user(message.from_user)
    except Exception:
        logger.exception("User initialization failed")
        await message.answer(
            "Не удалось открыть аккаунт. Попробуй позже."
        )
        return

    name = esc(message.from_user.first_name or "Пользователь")

    if greeting:
        heading = f"Добро пожаловать, {name}"
    else:
        heading = "Центр управления аккаунтом"

    text = (
        f"<b>{heading}</b>\n"
        f"<code>{BRAND}</code>\n\n"
        "Единый центр управления аккаунтом TNC.\n\n"
        "<b>Доступные разделы</b>\n"
        "Кошелёк, переводы, история, профиль, игровые токены "
        "и пополнение баланса.\n\n"
        "Выбери действие ниже."
    )

    await message.answer(
        text,
        reply_markup=main_keyboard(message.from_user.id),
        parse_mode="HTML",
    )


async def show_home_callback(callback):
    name = esc(callback.from_user.first_name or "Пользователь")

    text = (
        f"<b>ЦЕНТР УПРАВЛЕНИЯ TNC</b>\n"
        f"<code>{BRAND}</code>\n\n"
        f"Аккаунт: <b>{name}</b>\n\n"
        "Выбери нужный раздел."
    )

    await answer_screen(
        callback,
        text,
        main_keyboard(callback.from_user.id),
    )


# ============================================================
# START AND COMMANDS
# ============================================================

@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    await show_home(message)


@dp.message(Command("menu"))
async def menu_handler(message: Message, state: FSMContext):
    await state.clear()
    await show_home(message, greeting=False)


@dp.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await show_home(message, greeting=False)


@dp.message(Command("help"))
async def help_command(message: Message):
    text = (
        "<b>ЦЕНТР ПОМОЩИ TNC</b>\n\n"
        "<b>Команды</b>\n"
        "/start — открыть аккаунт\n"
        "/menu — главное меню\n"
        "/help — помощь\n"
        "/cancel — отменить действие\n\n"
        "<b>Кошелёк</b>\n"
        "Внутренний баланс TNC и операции с ним.\n\n"
        "<b>Переводы</b>\n"
        "Переводы между аккаунтами TNC. "
        "Перед отправкой требуется подтверждение.\n\n"
        "<b>GT</b>\n"
        "Отдельные игровые баллы. GT не являются TNC Coin "
        "и не выводятся как деньги."
    )

    await message.answer(
        text,
        reply_markup=main_keyboard(message.from_user.id),
        parse_mode="HTML",
    )


# ============================================================
# NAVIGATION
# ============================================================

@dp.callback_query(F.data.startswith("nav:"))
async def navigation_handler(
    callback: CallbackQuery,
    state: FSMContext,
):
    parts = callback.data.split(":")
    section = parts[1]

    if section == "home":
        await state.clear()
        await show_home_callback(callback)
        return

    if section == "wallet":
        await state.clear()
        await wallet_screen(callback)
        return

    if section == "transfer":
        await start_transfer(callback, state)
        return

    if section == "history":
        await state.clear()
        page = int(parts[2]) if len(parts) > 2 else 0
        await history_screen(callback, page)
        return

    if section == "account":
        await state.clear()
        await account_screen(callback)
        return

    if section == "gt":
        await state.clear()
        await gt_screen(callback)
        return

    if section == "shop":
        await state.clear()
        await shop_screen(callback)
        return

    if section == "community":
        await state.clear()
        await community_screen(callback)
        return

    if section == "help":
        await state.clear()
        await help_screen(callback)
        return

    if section == "admin":
        await state.clear()
        if not is_admin(callback.from_user.id):
            await callback.answer(
                "Доступ запрещён.",
                show_alert=True,
            )
            return

        await admin_screen(callback)
        return

    await callback.answer(
        "Раздел не найден.",
        show_alert=True,
    )


# ============================================================
# WALLET
# ============================================================

async def wallet_screen(callback):
    try:
        ensure_user(callback.from_user)

        with SessionLocal() as db:
            current_balance = fmt(
                balance(db, callback.from_user.id)
            )

        text = (
            "<b>МОЙ КОШЕЛЁК</b>\n"
            "<code>TNC WALLET</code>\n\n"
            "<b>ДОСТУПНЫЙ БАЛАНС</b>\n"
            f"<code>{esc(current_balance)} TNC</code>\n\n"
            "Внутренний баланс аккаунта TNC.\n"
            "Средства учитываются в системе кошелька.\n\n"
            "<b>Доступные действия</b>\n"
            "Перевод между пользователями и пополнение через магазин."
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [button("ПЕРЕВЕСТИ TNC", "nav:transfer")],
                [button("ПОПОЛНИТЬ БАЛАНС", "nav:shop")],
                [button("ИСТОРИЯ ОПЕРАЦИЙ", "nav:history:0")],
                [button("ГЛАВНОЕ МЕНЮ", "nav:home")],
            ]
        )

        await answer_screen(callback, text, keyboard)

    except Exception:
        logger.exception("Wallet screen failed")
        await callback.answer(
            "Не удалось загрузить кошелёк.",
            show_alert=True,
        )


# ============================================================
# GT BALANCE
# ============================================================

async def gt_screen(callback):
    try:
        ensure_user(callback.from_user)

        from app.services.game_tokens import get_balance

        amount = get_balance(callback.from_user.id)

        text = (
            "<b>ИГРОВОЙ БАЛАНС</b>\n"
            "<code>TNC GAMES</code>\n\n"
            "<b>ДОСТУПНО</b>\n"
            f"<code>{amount:,} GT</code>\n\n"
            "GT — отдельные игровые баллы экосистемы.\n"
            "Они не являются TNC Coin, не конвертируются "
            "в TNC и не выводятся как деньги."
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [button("НАЗАД", "nav:home")],
            ]
        )

        await answer_screen(callback, text, keyboard)

    except Exception:
        logger.exception("GT balance screen failed")
        await callback.answer(
            "Не удалось загрузить баланс GT.",
            show_alert=True,
        )


# ============================================================
# TRANSFERS
# ============================================================

async def start_transfer(callback, state):
    try:
        ensure_user(callback.from_user)
    except Exception:
        logger.exception("Transfer user initialization failed")
        await callback.answer(
            "Не удалось открыть перевод.",
            show_alert=True,
        )
        return

    await state.clear()
    await state.set_state(TransferFlow.receiver)

    text = (
        "<b>НОВЫЙ ПЕРЕВОД</b>\n"
        "<code>TNC TRANSFER</code>\n\n"
        "<b>ШАГ 1 ИЗ 3 — ПОЛУЧАТЕЛЬ</b>\n\n"
        "Введи Telegram ID получателя.\n"
        "Получатель должен предварительно запустить бота."
    )

    await edit_screen(
        callback,
        text,
        transfer_cancel_keyboard(),
    )
    await callback.answer()


@dp.message(TransferFlow.receiver)
async def transfer_receiver(message: Message, state: FSMContext):
    raw = (message.text or "").strip()

    if raw.lower() in ("отмена", "cancel"):
        await state.clear()
        await show_home(message, greeting=False)
        return

    if not raw.isdigit() or int(raw) <= 0:
        await message.answer(
            "Введи корректный числовой Telegram ID.",
            reply_markup=transfer_cancel_keyboard(),
        )
        return

    receiver_id = int(raw)

    if receiver_id == message.from_user.id:
        await message.answer("Нельзя переводить TNC самому себе.")
        return

    try:
        with SessionLocal() as db:
            recipient = db.get(User, receiver_id)

        if recipient is None:
            await message.answer(
                "Получатель не найден. Попроси его запустить TNC Bot."
            )
            return

        recipient_name = recipient.first_name or "TNC User"
        recipient_username = recipient.username or "Не указан"

        await state.update_data(
            receiver_id=receiver_id,
            recipient_name=recipient_name,
            recipient_username=recipient_username,
        )

        await state.set_state(TransferFlow.amount)

        await message.answer(
            "<b>ПОЛУЧАТЕЛЬ НАЙДЕН</b>\n\n"
            f"Имя: <b>{esc(recipient_name)}</b>\n"
            f"Username: {esc(recipient_username)}\n"
            f"Telegram ID: <code>{receiver_id}</code>\n\n"
            "<b>ШАГ 2 ИЗ 3 — СУММА</b>\n"
            "Введи сумму перевода в TNC.",
            reply_markup=transfer_cancel_keyboard(),
            parse_mode="HTML",
        )

    except Exception:
        logger.exception("Recipient lookup failed")
        await message.answer(
            "Не удалось проверить получателя. Попробуй позже."
        )


@dp.message(TransferFlow.amount)
async def transfer_amount(message: Message, state: FSMContext):
    raw = (message.text or "").strip().replace(",", ".")

    if raw.lower() in ("отмена", "cancel"):
        await state.clear()
        await show_home(message, greeting=False)
        return

    try:
        amount = Decimal(raw)

        if not amount.is_finite() or amount <= 0:
            raise InvalidOperation

        if amount > Decimal("1000000"):
            await message.answer(
                "Максимальная сумма одного перевода — 1 000 000 TNC."
            )
            return

        if amount.as_tuple().exponent < -6:
            await message.answer(
                "Максимальная точность — 6 знаков после запятой."
            )
            return

    except (InvalidOperation, ValueError):
        await message.answer(
            "Введи корректную сумму, например 25 или 125.50."
        )
        return

    data = await state.get_data()
    receiver_id = data.get("receiver_id")

    try:
        with SessionLocal() as db:
            current_balance = Decimal(
                str(balance(db, message.from_user.id))
            )

        amount_units = int(amount * Decimal("1000000"))

        if amount_units > int(current_balance):
            await message.answer(
                "Недостаточно средств.\n"
                f"Доступно: <b>{esc(fmt(int(current_balance)))} TNC</b>",
                reply_markup=transfer_cancel_keyboard(),
                parse_mode="HTML",
            )
            return

    except Exception:
        logger.exception("Transfer balance validation failed")
        await message.answer(
            "Не удалось проверить баланс. Попробуй позже."
        )
        return

    await state.update_data(amount=str(amount))
    await state.set_state(TransferFlow.confirm)

    text = (
        "<b>ПРОВЕРЬ ПЕРЕВОД</b>\n"
        "<code>TRANSFER CONFIRMATION</code>\n\n"
        "<b>ШАГ 3 ИЗ 3 — ПОДТВЕРЖДЕНИЕ</b>\n\n"
        f"Получатель: <b>{esc(data['recipient_name'])}</b>\n"
        f"Username: {esc(data['recipient_username'])}\n"
        f"Telegram ID: <code>{receiver_id}</code>\n\n"
        f"Сумма: <b>{amount} TNC</b>\n\n"
        "Проверь данные. Отправка начнётся только после "
        "нажатия кнопки подтверждения."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [button("ПОДТВЕРДИТЬ ПЕРЕВОД", "transfer:confirm")],
            [button("ОТМЕНИТЬ", "transfer:cancel")],
        ]
    )

    await message.answer(
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "transfer:cancel")
async def transfer_cancel(callback, state):
    await state.clear()

    await answer_screen(
        callback,
        "<b>ПЕРЕВОД ОТМЕНЁН</b>\n\nСредства не списаны.",
        main_keyboard(callback.from_user.id),
    )


@dp.callback_query(F.data == "transfer:confirm")
async def transfer_confirm(callback, state):
    if await state.get_state() != TransferFlow.confirm.state:
        await callback.answer(
            "Перевод уже обработан или истёк.",
            show_alert=True,
        )
        return

    data = await state.get_data()

    receiver_id = data.get("receiver_id")
    amount = data.get("amount")

    if not receiver_id or not amount:
        await state.clear()
        await callback.answer(
            "Данные перевода не найдены.",
            show_alert=True,
        )
        return

    # Сразу меняем состояние, чтобы повторное нажатие
    # не запустило второй вызов отправки.
    await state.set_state(TransferFlow.confirm)

    await callback.answer("Обрабатываю перевод...")

    try:
        with SessionLocal() as db:
            # Повторная проверка существования получателя.
            recipient = db.get(User, int(receiver_id))

            if recipient is None:
                raise ValueError("Аккаунт получателя больше не найден.")

            transaction = send(
                db,
                callback.from_user.id,
                int(receiver_id),
                amount,
            )

        await state.clear()

        operation_id = transaction.operation_id
        amount_value = transaction.amount_units / 1_000_000

        result_text = (
            "<b>ПЕРЕВОД ВЫПОЛНЕН</b>\n"
            "<code>TNC TRANSFER</code>\n\n"
            f"Получатель: <code>{receiver_id}</code>\n"
            f"Сумма: <b>{esc(fmt(transaction.amount_units))} TNC</b>\n"
            f"ID операции: <code>{esc(operation_id)}</code>\n\n"
            "Операция зарегистрирована в кошельке."
        )

        await edit_screen(
            callback,
            result_text,
            main_keyboard(callback.from_user.id),
        )

        await send_operation_image(
            callback.bot,
            callback.from_user.id,
            amount_value,
            "sent",
            callback.from_user.first_name or "TNC USER",
            str(operation_id),
        )

        try:
            with SessionLocal() as db:
                recipient = db.get(User, int(receiver_id))
                recipient_name = (
                    recipient.first_name
                    if recipient
                    else "TNC USER"
                )

            await send_operation_image(
                callback.bot,
                int(receiver_id),
                amount_value,
                "received",
                recipient_name,
                str(operation_id),
                (
                    "<b>ПОЛУЧЕН ПЕРЕВОД TNC</b>\n\n"
                    f"Отправитель: <code>{callback.from_user.id}</code>\n"
                    f"Сумма: <b>{esc(fmt(transaction.amount_units))} TNC</b>\n"
                    f"Операция: <code>{esc(operation_id)}</code>"
                ),
            )

        except Exception:
            logger.exception("Recipient notification failed")

    except ValueError as error:
        await state.clear()

        await edit_screen(
            callback,
            "<b>ПЕРЕВОД НЕ ВЫПОЛНЕН</b>\n\n"
            f"{esc(error)}",
            main_keyboard(callback.from_user.id),
        )

    except Exception:
        logger.exception("Transfer execution failed")
        await state.clear()

        await edit_screen(
            callback,
            "<b>НЕ УДАЛОСЬ ВЫПОЛНИТЬ ПЕРЕВОД</b>\n\n"
            "Проверь историю операций перед повторной попыткой. "
            "Не отправляй перевод повторно, пока не проверишь статус.",
            main_keyboard(callback.from_user.id),
        )


# ============================================================
# HISTORY
# ============================================================

def history_keyboard(page, has_next):
    rows = []
    navigation = []

    if page > 0:
        navigation.append(
            button("ПРЕДЫДУЩАЯ", f"nav:history:{page - 1}")
        )

    if has_next:
        navigation.append(
            button("СЛЕДУЮЩАЯ", f"nav:history:{page + 1}")
        )

    if navigation:
        rows.append(navigation)

    rows.append([
        button("КОШЕЛЁК", "nav:wallet"),
        button("ГЛАВНОЕ МЕНЮ", "nav:home"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def history_screen(callback, page=0):
    try:
        page = max(0, int(page))
        ensure_user(callback.from_user)

        limit = (page + 1) * HISTORY_PAGE_SIZE + 1

        with SessionLocal() as db:
            transactions = history(
                db,
                callback.from_user.id,
                limit,
            )

        start = page * HISTORY_PAGE_SIZE
        records = transactions[start:start + HISTORY_PAGE_SIZE]
        has_next = len(transactions) > start + HISTORY_PAGE_SIZE

        lines = [
            "<b>ИСТОРИЯ ОПЕРАЦИЙ</b>",
            "<code>TNC ACTIVITY</code>",
            f"Страница {page + 1}",
            "",
        ]

        if not records:
            lines.append("Операций на этой странице нет.")
        else:
            for tx in records:
                outgoing = tx.sender_id == callback.from_user.id

                if tx.kind == "deposit":
                    label = "Пополнение"
                    sign = "+"
                elif tx.kind == "withdraw":
                    label = "Списание"
                    sign = "−"
                elif outgoing:
                    label = "Отправлено"
                    sign = "−"
                else:
                    label = "Получено"
                    sign = "+"

                lines.extend([
                    f"<b>{label}</b>",
                    f"Сумма: <b>{sign}{esc(fmt(tx.amount_units))} TNC</b>",
                    f"ID: <code>{esc(tx.operation_id)}</code>",
                    "",
                ])

        await answer_screen(
            callback,
            "\n".join(lines),
            history_keyboard(page, has_next),
        )

    except Exception:
        logger.exception("History screen failed")
        await callback.answer(
            "Не удалось загрузить историю.",
            show_alert=True,
        )


# ============================================================
# ACCOUNT PROFILE
# ============================================================

async def account_screen(callback):
    try:
        ensure_user(callback.from_user)

        with SessionLocal() as db:
            user = db.get(User, callback.from_user.id)
            current_balance = fmt(
                balance(db, callback.from_user.id)
            )

        if user is None:
            await callback.answer(
                "Аккаунт не найден.",
                show_alert=True,
            )
            return

        from app.services.game_tokens import get_balance
        gt_amount = get_balance(callback.from_user.id)

        username = (
            f"@{esc(user.username)}"
            if user.username
            else "Не указан"
        )

        text = (
            "<b>МОЙ ПРОФИЛЬ</b>\n"
            "<code>TNC ACCOUNT</code>\n\n"
            f"Имя: <b>{esc(user.first_name)}</b>\n"
            f"Username: {username}\n"
            f"Telegram ID: <code>{user.telegram_id}</code>\n\n"
            "<b>БАЛАНСЫ</b>\n"
            f"TNC: <b>{esc(current_balance)}</b>\n"
            f"GT: <b>{gt_amount:,}</b>\n\n"
            "Управление средствами доступно через разделы кошелька."
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [button("МОЙ КОШЕЛЁК", "nav:wallet")],
                [button("БАЛАНС GT", "nav:gt")],
                [button("РЕФЕРАЛЬНАЯ ССЫЛКА", "nav:community")],
                [button("ГЛАВНОЕ МЕНЮ", "nav:home")],
            ]
        )

        await answer_screen(callback, text, keyboard)

    except Exception:
        logger.exception("Account screen failed")
        await callback.answer(
            "Не удалось загрузить профиль.",
            show_alert=True,
        )


# ============================================================
# REFERRAL
# ============================================================

async def community_screen(callback):
    try:
        bot_info = await callback.bot.get_me()

        if not bot_info.username:
            raise RuntimeError("Bot username is unavailable")

        referral_url = (
            f"https://t.me/{bot_info.username}"
            f"?start=ref_{callback.from_user.id}"
        )

        share_url = (
            "https://t.me/share/url"
            f"?url={referral_url}"
        )

        text = (
            "<b>РЕФЕРАЛЬНАЯ ПРОГРАММА</b>\n"
            "<code>TNC COMMUNITY</code>\n\n"
            "Приглашай друзей в экосистему TNC.\n\n"
            "<b>ТВОЯ ПЕРСОНАЛЬНАЯ ССЫЛКА</b>\n"
            f"<code>{esc(referral_url)}</code>\n\n"
            "Ссылка содержит твой Telegram ID."
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="ПОДЕЛИТЬСЯ ССЫЛКОЙ",
                        url=share_url,
                    )
                ],
                [button("МОЙ ПРОФИЛЬ", "nav:account")],
                [button("ГЛАВНОЕ МЕНЮ", "nav:home")],
            ]
        )

        await answer_screen(callback, text, keyboard)

    except Exception:
        logger.exception("Referral screen failed")
        await callback.answer(
            "Не удалось создать ссылку.",
            show_alert=True,
        )


# ============================================================
# HELP SCREEN
# ============================================================

async def help_screen(callback):
    text = (
        "<b>ЦЕНТР ПОМОЩИ TNC</b>\n"
        "<code>TNC SUPPORT</code>\n\n"
        "<b>КОШЕЛЁК</b>\n"
        "Внутренний баланс TNC и операции с ним.\n\n"
        "<b>ПЕРЕВОДЫ</b>\n"
        "Перевод между аккаунтами TNC с подтверждением.\n\n"
        "<b>ИСТОРИЯ</b>\n"
        "Просмотр зарегистрированных операций.\n\n"
        "<b>GAME TOKENS</b>\n"
        "GT — отдельные игровые баллы, не являющиеся TNC Coin.\n\n"
        "<b>TELEGRAM STARS</b>\n"
        "Пополнение обрабатывается после подтверждения платежа Telegram.\n\n"
        "<b>КОМАНДЫ</b>\n"
        "/start — запуск\n"
        "/menu — меню\n"
        "/help — помощь\n"
        "/cancel — отмена"
    )

    await answer_screen(
        callback,
        text,
        navigation_keyboard(),
    )


# ============================================================
# TNC SHOP
# ============================================================

def shop_keyboard():
    rows = []

    for package, stars in TNC_PACKAGES.items():
        rows.append([
            button(
                f"{package:,} TNC  |  {stars:,} STARS",
                f"tnc_buy:{package}",
            )
        ])

    rows.extend([
        [button("МОЙ КОШЕЛЁК", "nav:wallet")],
        [button("ГЛАВНОЕ МЕНЮ", "nav:home")],
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def shop_screen(callback):
    text = (
        "<b>МАГАЗИН TNC</b>\n"
        "<code>OFFICIAL TOP-UP</code>\n\n"
        "Выбери пакет пополнения внутреннего баланса.\n\n"
        "<b>ПАКЕТЫ</b>\n"
        "1 TNC — 50 Stars\n"
        "10 TNC — 500 Stars\n"
        "100 TNC — 5 000 Stars\n"
        "1 000 TNC — 50 000 Stars\n\n"
        "Начисление выполняется после подтверждения "
        "успешного платежа Telegram."
    )

    await answer_screen(
        callback,
        text,
        shop_keyboard(),
    )


@dp.callback_query(F.data.startswith("tnc_buy:"))
async def tnc_buy_handler(callback):
    from app.services.stars import create_order

    try:
        package = int(callback.data.split(":", 1)[1])

        if package not in TNC_PACKAGES:
            raise ValueError("Неизвестный пакет.")

        payload, stars = create_order(
            callback.from_user.id,
            package,
        )

        if int(stars) != TNC_PACKAGES[package]:
            raise ValueError("Стоимость заказа не совпадает с пакетом.")

        await callback.message.answer_invoice(
            title=f"{package:,} TNC",
            description=(
                f"Пополнение внутреннего баланса TNC "
                f"на {package:,} монет."
            ),
            payload=payload,
            currency="XTR",
            prices=[
                LabeledPrice(
                    label=f"{package:,} TNC",
                    amount=stars,
                )
            ],
        )

        await callback.answer("Счёт создан.")

    except Exception:
        logger.exception("TNC invoice creation failed")
        await callback.answer(
            "Не удалось создать счёт.",
            show_alert=True,
        )


# ============================================================
# TELEGRAM STARS PAYMENT
# ============================================================

@dp.pre_checkout_query()
async def tnc_pre_checkout_handler(query: PreCheckoutQuery):
    payload = query.invoice_payload or ""

    if query.currency != "XTR":
        await query.answer(
            ok=False,
            error_message="Неверная валюта платежа.",
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
                error_message="Заказ недействителен. Создай новый счёт.",
            )

    except Exception:
        logger.exception("Stars pre-checkout validation failed")
        await query.answer(
            ok=False,
            error_message="Не удалось проверить заказ.",
        )


@dp.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    payment = message.successful_payment
    payload = payment.invoice_payload or ""

    if payment.currency != "XTR":
        await message.answer(
            "Не удалось подтвердить валюту платежа."
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
                    "Этот платёж уже обработан. Повторного начисления нет."
                )
                return

            await message.answer(
                "<b>ПЛАТЁЖ GT ОБРАБОТАН</b>\n\n"
                f"Начислено: <b>{result['tokens']:,} GT</b>\n"
                f"Оплачено: <b>{payment.total_amount} Stars</b>",
                parse_mode="HTML",
                reply_markup=main_keyboard(message.from_user.id),
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
                "<b>ПОПОЛНЕНИЕ ВЫПОЛНЕНО</b>\n\n"
                "Оплата подтверждена Telegram.\n"
                "Проверь баланс в разделе «Мой кошелёк».",
                parse_mode="HTML",
                reply_markup=main_keyboard(message.from_user.id),
            )
        else:
            await message.answer(
                "Платёж уже обработан или заказ недействителен. "
                "Если баланс не обновился, обратись в поддержку."
            )

    except Exception:
        logger.exception("Stars payment processing failed")
        await message.answer(
            "Telegram подтвердил оплату, но зачисление требует проверки. "
            "Не оплачивай повторно — обратись в поддержку."
        )


# ============================================================
# ADMIN PANEL
# ============================================================

async def admin_screen(callback):
    if not is_admin(callback.from_user.id):
        await callback.answer(
            "Доступ запрещён.",
            show_alert=True,
        )
        return

    text = (
        "<b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n"
        "<code>TNC CONTROL CENTER</code>\n\n"
        "<b>УПРАВЛЕНИЕ TNC</b>\n"
        "<code>/credit USER_ID AMOUNT</code>\n"
        "Начислить TNC.\n\n"
        "<code>/debit USER_ID AMOUNT</code>\n"
        "Списать TNC.\n\n"
        "<b>УПРАВЛЕНИЕ GT</b>\n"
        "<code>/gt_add USER_ID AMOUNT [reason]</code>\n"
        "<code>/gt_take USER_ID AMOUNT [reason]</code>\n"
        "<code>/gt_balance USER_ID</code>\n\n"
        "<b>ИГРОВЫЕ ОГРАНИЧЕНИЯ</b>\n"
        "<code>/gameban USER_ID [reason]</code>\n"
        "<code>/gameunban USER_ID [reason]</code>\n\n"
        "<code>/gt_admin_log</code>\n"
        "Журнал административных операций."
    )

    await answer_screen(
        callback,
        text,
        InlineKeyboardMarkup(
            inline_keyboard=[
                [button("ЖУРНАЛ GT", "admin:log")],
                [button("ГЛАВНОЕ МЕНЮ", "nav:home")],
            ]
        ),
    )


@dp.callback_query(F.data == "admin:log")
async def admin_log_screen(callback):
    if not is_admin(callback.from_user.id):
        await callback.answer(
            "Доступ запрещён.",
            show_alert=True,
        )
        return

    try:
        from app.services.game_tokens import get_admin_log

        rows = get_admin_log(20)

        if not rows:
            text = (
                "<b>ЖУРНАЛ TNC GAMES</b>\n\n"
                "Записей пока нет."
            )
        else:
            lines = [
                "<b>ЖУРНАЛ TNC GAMES</b>",
                "<code>ADMIN ACTIVITY</code>",
                "",
            ]

            for row in rows:
                lines.extend([
                    f"<b>{esc(row['action'])}</b>",
                    f"Администратор: <code>{row['admin_id']}</code>",
                    f"Пользователь: <code>{row['user_id']}</code>",
                    f"Количество: <b>{row['amount']:,} GT</b>",
                    f"Причина: {esc(row['reason'] or 'Не указана')}",
                    "",
                ])

            text = "\n".join(lines)

        await answer_screen(
            callback,
            text,
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [button("НАЗАД В АДМИНКУ", "nav:admin")],
                    [button("ГЛАВНОЕ МЕНЮ", "nav:home")],
                ]
            ),
        )

    except Exception:
        logger.exception("Admin log screen failed")
        await callback.answer(
            "Не удалось загрузить журнал.",
            show_alert=True,
        )


@dp.message(Command("admin"))
async def admin_command(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.")
        return

    text = (
        "<b>TNC ADMINISTRATION</b>\n\n"
        "<code>/credit USER_ID AMOUNT</code> — начислить TNC\n"
        "<code>/debit USER_ID AMOUNT</code> — списать TNC\n"
        "<code>/gt_add USER_ID AMOUNT [reason]</code> — начислить GT\n"
        "<code>/gt_take USER_ID AMOUNT [reason]</code> — списать GT\n"
        "<code>/gt_balance USER_ID</code> — проверить GT\n"
        "<code>/gameban USER_ID [reason]</code> — запретить игры\n"
        "<code>/gameunban USER_ID [reason]</code> — снять запрет\n"
        "<code>/gt_admin_log</code> — журнал действий"
    )

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=main_keyboard(message.from_user.id),
    )


# ============================================================
# ADMIN TNC CREDIT
# ============================================================

@dp.message(Command("credit"))
async def admin_credit(message):
    if not is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.")
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
            str(tx.operation_id),
            (
                "<b>НАЧИСЛЕНИЕ TNC</b>\n\n"
                f"Сумма: <b>{esc(fmt(tx.amount_units))} TNC</b>"
            ),
        )

        await message.answer(
            "<b>НАЧИСЛЕНИЕ ВЫПОЛНЕНО</b>\n"
            f"Пользователь: <code>{target_id}</code>\n"
            f"Сумма: <b>{esc(fmt(tx.amount_units))} TNC</b>",
            parse_mode="HTML",
        )

    except ValueError as error:
        await message.answer(esc(error))
    except Exception:
        logger.exception("Admin credit failed")
        await message.answer("Не удалось выполнить начисление.")


# ============================================================
# ADMIN TNC DEBIT
# ============================================================

@dp.message(Command("debit"))
async def admin_debit(message):
    if not is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.")
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
            str(tx.operation_id),
            (
                "<b>СПИСАНИЕ TNC</b>\n\n"
                f"Сумма: <b>{esc(fmt(tx.amount_units))} TNC</b>"
            ),
        )

        await message.answer(
            "<b>СПИСАНИЕ ВЫПОЛНЕНО</b>\n"
            f"Пользователь: <code>{target_id}</code>\n"
            f"Сумма: <b>{esc(fmt(tx.amount_units))} TNC</b>",
            parse_mode="HTML",
        )

    except ValueError as error:
        await message.answer(esc(error))
    except Exception:
        logger.exception("Admin debit failed")
        await message.answer("Не удалось выполнить списание.")


# ============================================================
# ADMIN GT CREDIT
# ============================================================

@dp.message(Command("gt_add"))
async def gt_admin_add(message):
    if not is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.")
        return

    parts = (message.text or "").split(maxsplit=3)

    if len(parts) < 3:
        await message.answer(
            "Использование: /gt_add USER_ID AMOUNT [причина]"
        )
        return

    try:
        from app.services.game_tokens import admin_adjust_tokens

        user_id = int(parts[1])
        amount = int(parts[2])

        if amount <= 0:
            raise ValueError("Количество GT должно быть положительным.")

        reason = (
            parts[3]
            if len(parts) > 3
            else "Выдано администратором"
        )

        new_balance = admin_adjust_tokens(
            message.from_user.id,
            user_id,
            amount,
            "admin_add",
            reason,
        )

        await message.answer(
            "<b>GT НАЧИСЛЕНЫ</b>\n"
            f"Игрок: <code>{user_id}</code>\n"
            f"Начислено: <b>{amount:,} GT</b>\n"
            f"Новый баланс: <b>{new_balance:,} GT</b>",
            parse_mode="HTML",
        )

    except (ValueError, TypeError) as error:
        await message.answer(esc(error))
    except Exception:
        logger.exception("Admin GT credit failed")
        await message.answer("Не удалось начислить GT.")


# ============================================================
# ADMIN GT DEBIT
# ============================================================

@dp.message(Command("gt_take"))
async def gt_admin_take(message):
    if not is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.")
        return

    parts = (message.text or "").split(maxsplit=3)

    if len(parts) < 3:
        await message.answer(
            "Использование: /gt_take USER_ID AMOUNT [причина]"
        )
        return

    try:
        from app.services.game_tokens import admin_adjust_tokens

        user_id = int(parts[1])
        amount = int(parts[2])

        if amount <= 0:
            raise ValueError("Количество GT должно быть положительным.")

        reason = (
            parts[3]
            if len(parts) > 3
            else "Списано администратором"
        )

        new_balance = admin_adjust_tokens(
            message.from_user.id,
            user_id,
            amount,
            "admin_take",
            reason,
        )

        await message.answer(
            "<b>GT СПИСАНЫ</b>\n"
            f"Игрок: <code>{user_id}</code>\n"
            f"Списано: <b>{amount:,} GT</b>\n"
            f"Новый баланс: <b>{new_balance:,} GT</b>",
            parse_mode="HTML",
        )

    except (ValueError, TypeError) as error:
        await message.answer(esc(error))
    except Exception:
        logger.exception("Admin GT debit failed")
        await message.answer("Не удалось списать GT.")


# ============================================================
# ADMIN GT BALANCE
# ============================================================

@dp.message(Command("gt_balance"))
async def gt_admin_balance(message):
    if not is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.")
        return

    parts = (message.text or "").split()

    if len(parts) != 2:
        await message.answer(
            "Использование: /gt_balance USER_ID"
        )
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
        logger.exception("Admin GT balance failed")
        await message.answer("Не удалось получить баланс.")


# ============================================================
# ADMIN GAME BAN
# ============================================================

@dp.message(Command("gameban"))
async def gt_admin_ban(message):
    if not is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.")
        return

    parts = (message.text or "").split(maxsplit=2)

    if len(parts) < 2:
        await message.answer(
            "Использование: /gameban USER_ID [причина]"
        )
        return

    try:
        from app.services.game_tokens import set_game_ban

        user_id = int(parts[1])
        reason = (
            parts[2]
            if len(parts) > 2
            else "Блокировка администратором"
        )

        set_game_ban(
            message.from_user.id,
            user_id,
            True,
            reason,
        )

        await message.answer(
            f"Игрок <code>{user_id}</code> заблокирован в TNC Games.",
            parse_mode="HTML",
        )

    except ValueError:
        await message.answer("Некорректный Telegram ID.")
    except Exception:
        logger.exception("Game ban failed")
        await message.answer("Не удалось заблокировать игрока.")


# ============================================================
# ADMIN GAME UNBAN
# ============================================================

@dp.message(Command("gameunban"))
async def gt_admin_unban(message):
    if not is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.")
        return

    parts = (message.text or "").split(maxsplit=2)

    if len(parts) < 2:
        await message.answer(
            "Использование: /gameunban USER_ID [причина]"
        )
        return

    try:
        from app.services.game_tokens import set_game_ban

        user_id = int(parts[1])
        reason = (
            parts[2]
            if len(parts) > 2
            else "Разблокировка администратором"
        )

        set_game_ban(
            message.from_user.id,
            user_id,
            False,
            reason,
        )

        await message.answer(
            f"Игрок <code>{user_id}</code> разблокирован в TNC Games.",
            parse_mode="HTML",
        )

    except ValueError:
        await message.answer("Некорректный Telegram ID.")
    except Exception:
        logger.exception("Game unban failed")
        await message.answer("Не удалось разблокировать игрока.")


# ============================================================
# ADMIN GT LOG
# ============================================================

@dp.message(Command("gt_admin_log"))
async def gt_admin_log_handler(message):
    if not is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.")
        return

    try:
        from app.services.game_tokens import get_admin_log

        rows = get_admin_log(20)

        if not rows:
            await message.answer(
                "Журнал административных действий пока пуст."
            )
            return

        lines = [
            "<b>ЖУРНАЛ TNC GAMES — ПОСЛЕДНИЕ 20 ДЕЙСТВИЙ</b>"
        ]

        for row in rows:
            lines.append(
                f"\n<b>{esc(row['action'])}</b>"
                f"\nАдминистратор: <code>{row['admin_id']}</code>"
                f"\nИгрок: <code>{row['user_id']}</code>"
                f"\nКоличество: <b>{row['amount']:,} GT</b>"
                f"\nПричина: {esc(row['reason'] or 'Не указана')}"
            )

        await message.answer(
            "\n".join(lines),
            parse_mode="HTML",
        )

    except Exception:
        logger.exception("GT admin log failed")
        await message.answer("Не удалось загрузить журнал.")


# ============================================================
# UNKNOWN MESSAGE
# ============================================================

@dp.message()
async def unknown_handler(message: Message):
    await message.answer(
        "<b>КОМАНДА НЕ РАСПОЗНАНА</b>\n\n"
        "Используй кнопки меню или команду /help.",
        reply_markup=main_keyboard(message.from_user.id),
        parse_mode="HTML",
    )


# ============================================================
# STARTUP
# ============================================================

async def main():
    if not settings.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не настроен.")

    if not settings.ADMIN_IDS:
        logger.warning(
            "ADMIN_IDS пуст. Административные команды недоступны."
        )

    init_database()

    bot = Bot(token=settings.BOT_TOKEN)

    logger.info("TNC Ecosystem Bot is starting...")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
