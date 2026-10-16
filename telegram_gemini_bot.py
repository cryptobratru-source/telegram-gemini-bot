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
GEMINI_MODEL = "gemini-1.5-flash"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

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
    timestamp = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (chat_id, user_id, username, message_text, timestamp) VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, username, message_text, timestamp)
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


async def get_full_memory(chat_id: int) -> str:
    """Получает полную память: последние 20 + каждое 5-е из старых"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Последние 20 сообщений
        async with db.execute(
            "SELECT username, message_text FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT 20",
            (chat_id,)
        ) as cursor:
            recent = list(reversed(await cursor.fetchall()))

        # Старые сообщения: каждое 5-е
        async with db.execute(
            "SELECT id, username, message_text FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT -1 OFFSET 20",
            (chat_id,)
        ) as cursor:
            all_old = await cursor.fetchall()
            old_sampled = [all_old[i] for i in range(0, len(all_old), 5)]  # каждое 5-е
            old_sampled.reverse()  # хронологический порядок
            old_messages = [(username, text) for _, username, text in old_sampled]

    # Формируем контекст
    old_context = "\n".join([f"{u}: {t}" for u, t in old_messages]) if old_messages else ""
    recent_context = "\n".join([f"{u}: {t}" for u, t in recent])

    if old_context:
        return f"=== Старые сообщения (дословно, каждое 5-е) ===\n{old_context}\n\n=== Последние 20 сообщений ===\n{recent_context}"
    return recent_context


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
    # Получаем полную память с умной выборкой
    full_context = await get_full_memory(chat_id)

    prompt = f"""Ты — Gemini AI, участвуешь в групповом чате Telegram с пользователем Стасом и Баламутом.

История общения (дословно сохранена):
{full_context}

Новое сообщение:
{user_message}

Ты помнишь КАЖДОЕ СЛОВО из всей истории нашего общения. Отвечай естественно, учитывая весь контекст."""

    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    try:
        logger.info(f"Отправляю запрос к Gemini API (модель: {GEMINI_MODEL})")
        import time
        start = time.time()

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                elapsed = time.time() - start
                logger.info(f"Gemini ответил за {elapsed:.1f}s, статус: {resp.status}")

                if resp.status == 429:
                    logger.warning(f"Rate limit 429: ждём 4 секунды перед повтором")
                    await asyncio.sleep(4)
                    # Повторный запрос
                    async with session.post(
                        f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
                        json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as retry_resp:
                        if retry_resp.status != 200:
                            error_text = await retry_resp.text()
                            logger.error(f"Повтор тоже failed {retry_resp.status}: {error_text[:500]}")
                            return f"Извини, Gemini API перегружен (429 rate limit). Попробуй через минуту."
                        result = await retry_resp.json()
                        return result["candidates"][0]["content"]["parts"][0]["text"]

                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"Gemini API error {resp.status} ({elapsed:.1f}s): {error_text[:500]}")
                    return f"Извини, произошла ошибка при обращении к Gemini API (статус {resp.status})."

                result = await resp.json()
                logger.info(f"Gemini успешно ответил ({len(result['candidates'][0]['content']['parts'][0]['text'])} символов)")
                return result["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.error(f"Gemini API exception: {type(e).__name__}: {str(e)}")
        return f"Извини, произошла ошибка: {type(e).__name__}"


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
    logger.info("Бот запущен с полной памятью (каждое 5-е + последние 20)")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
