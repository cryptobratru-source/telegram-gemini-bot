import asyncio
import aiosqlite
import numpy as np
from sentence_transformers import SentenceTransformer
import logging

logger = logging.getLogger(__name__)

DB_PATH = "chat_history.db"
model = None

def get_embedding_model():
    global model
    if model is None:
        model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    return model

async def init_rag_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS message_embeddings (
                message_id INTEGER PRIMARY KEY,
                embedding BLOB NOT NULL,
                FOREIGN KEY (message_id) REFERENCES messages(id)
            )
        """)
        await db.commit()

async def save_embedding(message_id: int, text: str):
    try:
        model = get_embedding_model()
        embedding = model.encode(text, convert_to_numpy=True)
        embedding_bytes = embedding.tobytes()

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO message_embeddings (message_id, embedding) VALUES (?, ?)",
                (message_id, embedding_bytes)
            )
            await db.commit()
    except Exception as e:
        logger.error(f"Ошибка сохранения embedding: {e}")

async def get_message_id(chat_id: int, timestamp: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM messages WHERE chat_id = ? AND timestamp = ? ORDER BY id DESC LIMIT 1",
            (chat_id, timestamp)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def find_relevant_messages(chat_id: int, query: str, limit: int = 10):
    try:
        model = get_embedding_model()
        query_embedding = model.encode(query, convert_to_numpy=True)

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT m.id, m.username, m.message_text, me.embedding
                FROM messages m
                JOIN message_embeddings me ON m.id = me.message_id
                WHERE m.chat_id = ?
                ORDER BY m.id DESC
                LIMIT 1000
            """, (chat_id,)) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            return []

        similarities = []
        for msg_id, username, text, emb_bytes in rows:
            emb = np.frombuffer(emb_bytes, dtype=np.float32)
            similarity = np.dot(query_embedding, emb) / (np.linalg.norm(query_embedding) * np.linalg.norm(emb))
            similarities.append((similarity, username, text))

        similarities.sort(reverse=True)
        return [(username, text) for _, username, text in similarities[:limit]]

    except Exception as e:
        logger.error(f"Ошибка поиска релевантных сообщений: {e}")
        return []
