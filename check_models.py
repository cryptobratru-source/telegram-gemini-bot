import os
import aiohttp
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def list_models():
    api_key = os.getenv("GEMINI_API_KEY")
    url = "https://generativelanguage.googleapis.com/v1beta/models"

    headers = {"x-goog-api-key": api_key}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            data = await resp.json()

            if "models" in data:
                print("Доступные модели Gemini:\n")
                for model in data["models"]:
                    name = model.get("name", "")
                    display_name = model.get("displayName", "")
                    supported = model.get("supportedGenerationMethods", [])

                    if "generateContent" in supported:
                        print(f"✅ {name}")
                        print(f"   Название: {display_name}")
                        print(f"   Методы: {', '.join(supported)}\n")
            else:
                print("Ошибка:", data)

asyncio.run(list_models())
