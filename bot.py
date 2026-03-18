import asyncio
import logging
import aiohttp
import time
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    WebAppInfo,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")
BACKEND_URL = "http://localhost:8000"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ─── Хранилище ожидающих привязок ────────────────────────────────────────────
# telegram_id -> minecraft_username
# Хранится в памяти до тех пор, пока пользователь не нажмёт кнопку выбора.
pending_links: dict[int, str] = {}


# ─── /start ──────────────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    referral_code = None
    if message.text and len(message.text.split()) > 1:
        referral_code = message.text.split()[1]

    # Уникальный timestamp → Telegram не найдёт этот URL в кеше → всегда свежий JS
    ts = int(time.time())
    if referral_code:
        webapp_url = f"{WEBAPP_URL}?ref={referral_code}&t={ts}"
    else:
        webapp_url = f"{WEBAPP_URL}?t={ts}"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎮 Открыть игру",
            web_app=WebAppInfo(url=webapp_url)
        )]
    ])

    welcome_text = "🎮 <b>Добро пожаловать в Clicker Game!</b>\n\n"

    if referral_code:
        welcome_text += "🎁 <b>Вас пригласил друг! Получите бонус при первом входе!</b>\n\n"

    welcome_text += (
        "💰 Кликай и зарабатывай валюту\n"
        "🏭 Покупай фермы для пассивного дохода\n"
        "👥 Приглашай друзей и получай бонусы\n"
        "🏆 Соревнуйся с другими игроками\n\n"
        "🔗 Чтобы привязать Minecraft аккаунт: /link &lt;ник&gt;\n\n"
        "👇 Нажми кнопку ниже, чтобы начать игру!"
    )

    await message.answer(
        welcome_text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# ─── /link ───────────────────────────────────────────────────────────────────

@dp.message(Command("link"))
async def cmd_link(message: types.Message):
    """
    Привязать Minecraft аккаунт к Telegram.
    Использование: /link MashinkaZ

    Если у пользователя есть прогресс и в TG и в MC — предлагает выбор.
    Если TG-прогресса нет — привязывает сразу к MC.
    """
    parts = message.text.strip().split(maxsplit=1)

    if len(parts) < 2:
        await message.answer(
            "❌ <b>Укажи ник Minecraft игрока!</b>\n\n"
            "Пример: <code>/link MashinkaZ</code>\n\n"
            "⚠️ Ник должен совпадать с тем, что в Minecraft (с учётом регистра).",
            parse_mode="HTML"
        )
        return

    minecraft_username = parts[1].strip()
    telegram_id = message.from_user.id

    await message.answer("🔍 Проверяю аккаунты, подожди секунду...")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{BACKEND_URL}/api/link/preview",
                params={
                    "telegram_id": telegram_id,
                    "minecraft_username": minecraft_username,
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()

        if not data.get("success"):
            error = data.get("error", "Неизвестная ошибка")
            await message.answer(
                f"❌ <b>Ошибка</b>\n\n{error}",
                parse_mode="HTML"
            )
            return

        mc_player = data["mc_player"]
        tg_player = data.get("tg_player")

        if not tg_player:
            # У пользователя нет TG-прогресса — привязываем сразу
            await _do_link(message, telegram_id, minecraft_username, source="minecraft")
            return

        # Есть оба аккаунта — предлагаем выбор
        pending_links[telegram_id] = minecraft_username

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎮 Взять прогресс Minecraft",
                    callback_data="link_mc",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📱 Взять прогресс Telegram",
                    callback_data="link_tg",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="link_cancel",
                ),
            ],
        ])

        text = (
            f"⚖️ <b>Выбери, чей прогресс сохранить:</b>\n\n"
            f"🎮 <b>Minecraft ({mc_player['name']}):</b>\n"
            f"  🍪 Печенек: <b>{mc_player['cookies']:,}</b>\n"
            f"  ⚡ Сила клика: <b>{mc_player['per_click']}</b>\n"
            f"  👆 Кликов: <b>{mc_player['clicker_clicks']:,}</b>\n\n"
            f"📱 <b>Telegram:</b>\n"
            f"  🍪 Печенек: <b>{tg_player['cookies']:,}</b>\n"
            f"  ⚡ Сила клика: <b>{tg_player['per_click']}</b>\n"
            f"  👆 Кликов: <b>{tg_player['clicker_clicks']:,}</b>\n\n"
            f"⚠️ <i>Прогресс другой платформы будет удалён.</i>\n"
            f"<i>Баланс Minecraft может незначительно отличаться — "
            f"сервер синхронизирует данные раз в несколько минут.</i>"
        )

        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    except aiohttp.ClientError:
        await message.answer(
            "❌ <b>Ошибка соединения с сервером.</b>\n"
            "Убедись что сервер запущен и попробуй снова.",
            parse_mode="HTML"
        )


# ─── Callback: выбор источника прогресса ─────────────────────────────────────

@dp.callback_query(F.data.in_({"link_mc", "link_tg", "link_cancel"}))
async def callback_link_choice(callback: CallbackQuery):
    telegram_id = callback.from_user.id

    if callback.data == "link_cancel":
        pending_links.pop(telegram_id, None)
        await callback.message.edit_text(
            "❌ <b>Привязка отменена.</b>",
            parse_mode="HTML"
        )
        await callback.answer()
        return

    if telegram_id not in pending_links:
        await callback.answer(
            "❌ Запрос устарел. Введи /link заново.",
            show_alert=True,
        )
        return

    minecraft_username = pending_links.pop(telegram_id)
    source = "minecraft" if callback.data == "link_mc" else "telegram"

    await callback.message.edit_text("🔗 Привязываю аккаунт...")
    await callback.answer()

    await _do_link(callback.message, telegram_id, minecraft_username, source=source)


# ─── Вспомогательная функция: выполнить привязку ─────────────────────────────

async def _do_link(
    message: types.Message,
    telegram_id: int,
    minecraft_username: str,
    source: str,
):
    """Вызывает POST /api/link/minecraft и обновляет сообщение результатом."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BACKEND_URL}/api/link/minecraft",
                json={
                    "telegram_id": telegram_id,
                    "minecraft_username": minecraft_username,
                    "source": source,
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()

        if data.get("success"):
            mc_name = data.get("mc_name", minecraft_username)
            source_label = "Minecraft 🎮" if source == "minecraft" else "Telegram 📱"
            await message.answer(
                f"✅ <b>Готово!</b>\n\n"
                f"Minecraft аккаунт <b>{mc_name}</b> успешно привязан!\n"
                f"Сохранён прогресс: <b>{source_label}</b>\n\n"
                f"Теперь клики в Minecraft и Telegram блокируют друг друга — "
                f"нельзя играть одновременно в двух местах.\n\n"
                f"Открой игру и посмотри свой баланс 🍪",
                parse_mode="HTML"
            )
        else:
            error = data.get("error", "Неизвестная ошибка")
            await message.answer(
                f"❌ <b>Не удалось привязать аккаунт</b>\n\n{error}",
                parse_mode="HTML"
            )

    except aiohttp.ClientError:
        await message.answer(
            "❌ <b>Ошибка соединения с сервером.</b>\n"
            "Убедись что сервер запущен и попробуй снова.",
            parse_mode="HTML"
        )


# ─── /help ───────────────────────────────────────────────────────────────────

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 <b>Команды:</b>\n\n"
        "/start — открыть игру\n"
        "/link &lt;ник&gt; — привязать Minecraft аккаунт\n"
        "/help — эта справка\n\n"
        "❓ <b>Зачем привязывать?</b>\n"
        "Чтобы твои печеньки из Minecraft и Telegram были общими. "
        "Нельзя кликать одновременно в обоих местах.\n\n"
        "ℹ️ <b>Про баланс:</b>\n"
        "Minecraft синхронизирует данные каждые несколько минут. "
        "Небольшое расхождение между балансами — это нормально.",
        parse_mode="HTML"
    )


# ─── Запуск ───────────────────────────────────────────────────────────────────

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
