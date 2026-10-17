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
GEMINI_MODEL = "gemini-3.8-flash"
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


async def get_chat_history(chat_id: int, limit: int = 50):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT username, message_text FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return list(reversed(rows))


async def search_old_messages(chat_id: int, keywords: list, days_back: int = 90, limit: int = 10) -> list:
    """Ищет старые сообщения по ключевым словам за последние days_back дней"""
    if not keywords:
        return []

    async with aiosqlite.connect(DB_PATH) as db:
        # Формируем WHERE условие для поиска
        where_conditions = " OR ".join(["message_text LIKE ?" for _ in keywords])
        like_patterns = [f"%{kw}%" for kw in keywords]

        query = f"""
            SELECT username, message_text, timestamp
            FROM messages
            WHERE chat_id = ?
            AND ({where_conditions})
            AND datetime(timestamp) >= datetime('now', '-{days_back} days')
            ORDER BY timestamp DESC
            LIMIT ?
        """

        async with db.execute(query, (chat_id, *like_patterns, limit)) as cursor:
            rows = await cursor.fetchall()
            return list(reversed(rows))  # хронологический порядок


def extract_keywords(text: str) -> list:
    """Извлекает ключевые слова из текста для поиска"""
    # Убираем стоп-слова и короткие слова
    stop_words = {"и", "в", "на", "с", "по", "для", "как", "что", "это", "так", "то", "а", "о", "у"}
    words = text.lower().split()
    keywords = [w.strip(".,!?:;") for w in words if len(w) > 3 and w not in stop_words]
    return keywords[:5]  # максимум 5 ключевых слов


async def get_full_memory(chat_id: int, user_message: str) -> str:
    """Получает полную память: последние 20-50 + поиск по старым (если нужно)"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Последние 50 сообщений
        async with db.execute(
            "SELECT username, message_text FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT 50",
            (chat_id,)
        ) as cursor:
            recent = list(reversed(await cursor.fetchall()))

    # Проверяем, нужен ли поиск по старым сообщениям
    memory_triggers = ["помнишь", "назад", "тогда", "раньше", "говорил", "обсуждали", "неделю", "месяц", "вчера"]
    needs_search = any(trigger in user_message.lower() for trigger in memory_triggers)

    old_messages = []
    if needs_search:
        keywords = extract_keywords(user_message)
        old_results = await search_old_messages(chat_id, keywords, days_back=90, limit=10)
        old_messages = [(username, text) for username, text, _ in old_results]

    # Формируем контекст
    recent_context = "\n".join([f"{u}: {t}" for u, t in recent])

    if old_messages:
        old_context = "\n".join([f"{u}: {t}" for u, t in old_messages])
        return f"=== Старые сообщения (найдено по ключевым словам) ===\n{old_context}\n\n=== Последние 50 сообщений ===\n{recent_context}"

    return f"=== Последние 50 сообщений ===\n{recent_context}"


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
    # Получаем полную память с поиском по старым (если нужно)
    full_context = await get_full_memory(chat_id, user_message)

    prompt = f"""Ты — Нейробрат, мудрый AI-помощник.

Правила:
- Отвечай вдумчиво, по шагам
- Честно говори "не знаю", если не уверен
- Вежливый, без воды

История:
{full_context}

Сообщение: {user_message}"""

    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.6,
            "topP": 0.95,
            "topK": 40,
            "maxOutputTokens": 8192
        }
    }

    try:
        logger.info(f"Отправляю запрос к Gemini API (модель: {GEMINI_MODEL})")
        import time

        async with aiohttp.ClientSession() as session:
            # Retry logic: 3 попытки с exponential backoff
            for attempt in range(3):
                start = time.time()

                async with session.post(
                    GEMINI_API_URL,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "x-goog-api-key": GEMINI_API_KEY
                    },
                    timeout=aiohttp.ClientTimeout(total=45)
                ) as resp:
                    elapsed = time.time() - start
                    logger.info(f"Gemini ответил за {elapsed:.1f}s, статус: {resp.status} (попытка {attempt+1}/3)")

                    # 503 или 429 — retry
                    if resp.status in [429, 503]:
                        if attempt < 2:  # не последняя попытка
                            wait_time = 2 ** attempt  # 1s, 2s, 4s
                            logger.warning(f"Статус {resp.status}: ждём {wait_time}s перед retry")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            error_text = await resp.text()
                            logger.error(f"Все 3 попытки failed {resp.status}: {error_text[:300]}")
                            return f"Извини, Gemini API сейчас перегружен. Попробуй через минуту."

                    # Любая другая ошибка
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"Gemini API error {resp.status} ({elapsed:.1f}s): {error_text[:500]}")
                        return f"Извини, произошла ошибка при обращении к Gemini API (статус {resp.status})."

                    # Успех
                    result = await resp.json()
                    logger.info(f"Gemini успешно ответил ({len(result['candidates'][0]['content']['parts'][0]['text'])} символов)")
                    return result["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.error(f"Gemini API exception: {type(e).__name__}: {str(e)}")
        return f"Извини, произошла ошибка: {type(e).__name__}"


@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я Нейробрат (Gemini AI).\n\n"
        "Умею:\n"
        "✅ Помню всю историю общения (поиск по старым сообщениям)\n"
        "✅ Читаю PDF, Word, Excel\n"
        "✅ Анализирую изображения\n\n"
        "Упомяни меня @имя_бота или ответь Reply — я отвечу."
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

    # ВСЕГДА сохраняем сообщение в базу (для полной памяти)
    await save_message(message.chat.id, message.from_user.id, username, text)

    bot_username = (await bot.get_me()).username

    # Отвечаем ТОЛЬКО на @упоминание или Reply
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

    # Проверяем доступные модели при старте
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers={"x-goog-api-key": GEMINI_API_KEY}
            ) as resp:
                data = await resp.json()
                if "models" in data:
                    available = [m["name"] for m in data["models"] if "generateContent" in m.get("supportedGenerationMethods", [])]
                    logger.info(f"Доступные модели: {', '.join(available)}")
                else:
                    logger.warning(f"Не удалось получить список моделей: {data}")
    except Exception as e:
        logger.warning(f"Ошибка при проверке моделей: {e}")

    logger.info("Нейробрат запущен: полная память (последние 50 + поиск по старым), отвечает только на @упоминание")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
