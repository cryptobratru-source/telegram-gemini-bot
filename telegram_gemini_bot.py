import asyncio
import logging
import os
import aiosqlite
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv
import aiohttp
from io import BytesIO

# File processing imports
from pypdf import PdfReader
from docx import Document
from openpyxl import load_workbook
from PIL import Image

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent"

if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN or GEMINI_API_KEY in .env")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

DB_PATH = "chat_history.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER,
                username TEXT,
                message_text TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        await db.commit()


async def save_message(chat_id: int, user_id: int, username: str, message_text: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (chat_id, user_id, username, message_text, timestamp) VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, username, message_text, datetime.now().isoformat())
        )
        await db.commit()


async def get_chat_history(chat_id: int, limit: int = 100):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT username, message_text FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return list(reversed(rows))


async def download_file(file_id: str) -> bytes:
    file = await bot.get_file(file_id)
    file_path = file.file_path

    async with aiohttp.ClientSession() as session:
        url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
        async with session.get(url) as resp:
            return await resp.read()


async def process_voice_gemini(voice_data: bytes) -> str:
    try:
        return "[голосовое сообщение - ожидает реализацию]"
    except Exception as e:
        logger.error(f"Voice processing error: {e}")
        return "[голосовое сообщение]"


async def process_pdf(file_data: bytes) -> str:
    try:
        pdf = PdfReader(BytesIO(file_data))
        text = ""
        for page in pdf.pages[:10]:
            text += page.extract_text() + "\n"
        return text[:8000]
    except Exception as e:
        logger.error(f"PDF error: {e}")
        return "[PDF - ошибка чтения]"


async def process_docx(file_data: bytes) -> str:
    try:
        doc = Document(BytesIO(file_data))
        text = "\n".join([para.text for para in doc.paragraphs[:200]])
        return text[:8000]
    except Exception as e:
        logger.error(f"DOCX error: {e}")
        return "[Word - ошибка чтения]"


async def process_excel(file_data: bytes) -> str:
    try:
        wb = load_workbook(BytesIO(file_data), read_only=True)
        text = ""
        for sheet_name in wb.sheetnames[:3]:
            sheet = wb[sheet_name]
            text += f"\n=== {sheet_name} ===\n"
            for row in list(sheet.iter_rows(values_only=True))[:30]:
                text += " | ".join([str(cell) if cell else "" for cell in row]) + "\n"
        return text[:8000]
    except Exception as e:
        logger.error(f"Excel error: {e}")
        return "[Excel - ошибка чтения]"


async def process_image(file_data: bytes) -> str:
    try:
        image = Image.open(BytesIO(file_data))
        return f"[Изображение: {image.size[0]}x{image.size[1]}]"
    except Exception as e:
        logger.error(f"Image error: {e}")
        return "[изображение]"


async def get_gemini_response(chat_id: int, user_message: str) -> str:
    history = await get_chat_history(chat_id, limit=10000)  # Все сообщения (практически безлимит)
    context = "\n".join([f"{username}: {text}" for username, text in history])

    prompt = f"""Ты — Gemini AI, участвуешь в групповом чате Telegram с пользователем Стасом и Баламутом.

История последних сообщений:
{context}

Новое сообщение:
{user_message}

Ответь естественно, учитывая всю историю общения."""

    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"Gemini API error {resp.status}: {error_text}")
                    return "Извини, произошла ошибка при обращении к Gemini API."

                result = await resp.json()
                return result["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return "Извини, произошла ошибка."


@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я Gemini AI бот.\n\n"
        "Умею:\n"
        "✅ Помню всё с момента запуска\n"
        "✅ Читаю PDF, Word, Excel\n"
        "✅ Анализирую изображения\n\n"
        "Упомяни меня @balamut_gemini_bot или ответь Reply."
    )


@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def handle_group_message(message: Message):
    username = message.from_user.username or message.from_user.first_name or "Аноним"
    text = message.text or ""

    # Voice (placeholder)
    if message.voice:
        voice_data = await download_file(message.voice.file_id)
        voice_text = await process_voice_gemini(voice_data)
        text = f"[Голос: {voice_text}]"

    # Documents
    if message.document:
        file_data = await download_file(message.document.file_id)
        file_name = message.document.file_name.lower()

        if file_name.endswith('.pdf'):
            text += f"\n{await process_pdf(file_data)}"
        elif file_name.endswith(('.docx', '.doc')):
            text += f"\n{await process_docx(file_data)}"
        elif file_name.endswith(('.xlsx', '.xls')):
            text += f"\n{await process_excel(file_data)}"

    # Photos
    if message.photo:
        photo = message.photo[-1]
        photo_data = await download_file(photo.file_id)
        text += f"\n{await process_image(photo_data)}"

    await save_message(message.chat.id, message.from_user.id, username, text)

    bot_username = (await bot.get_me()).username

    should_respond = False
    if message.reply_to_message and message.reply_to_message.from_user.id == bot.id:
        should_respond = True
    elif f"@{bot_username}" in text:
        should_respond = True

    if should_respond:
        response = await get_gemini_response(message.chat.id, text)
        await message.answer(response)
        await save_message(message.chat.id, bot.id, bot_username, response)


async def main():
    await init_db()
    logger.info("Бот запущен с REST API (gemini-1.5-pro)")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
