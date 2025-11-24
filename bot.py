import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    referral_code = None
    if message.text and len(message.text.split()) > 1:
        referral_code = message.text.split()[1]

    webapp_url = WEBAPP_URL
    if referral_code:
        webapp_url = f"{WEBAPP_URL}?ref={referral_code}"
    
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
        "👇 Нажми кнопку ниже, чтобы начать игру!"
    )
    
    await message.answer(
        welcome_text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
