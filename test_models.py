import requests
import os

key = os.getenv("GEMINI_API_KEY")
models = [
    "gemini-3.1-pro-preview",
    "gemini-3.1-pro-preview-customtools",
    "deep-research-pro-preview-12-2025"
]

print("=== Проверка PRO моделей ===")
for model in models:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    resp = requests.post(
        url,
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": "привет"}]}]},
        timeout=10
    )
    print(f"{model}: {resp.status_code}")
    if resp.status_code != 200:
        print(f"  Ошибка: {resp.text[:150]}")
