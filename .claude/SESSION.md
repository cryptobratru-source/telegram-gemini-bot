# SESSION — Баламут (Telegram бот)

## ПОСЛЕДНЯЯ СЕССИЯ
**Дата:** 2026-10-16  
**Задача:** Деплой Telegram бота @balamut_gemini_bot на Render.com

### Что сделали ✅

1. **Создали бота и подготовили код**
   - Telegram бот @balamut_gemini_bot (token: 8779961482:...)
   - Gemini API (ключ AQ.Ab8RN6J..., проект gen-lang-client-0438544452)
   - Репозиторий: https://github.com/cryptobratru-source/telegram-gemini-bot
   - Основной файл: `telegram_gemini_bot.py` (aiogram + google-generativeai REST API)
   - Зависимости: aiogram, google-generativeai, aiosqlite, pypdf, python-docx, openpyxl, Pillow 11.0.0

2. **Подключили репо к Render.com**
   - Создали аккаунт через GitHub (cryptobratru@gmail.com)
   - Подключили репо telegram-gemini-bot
   - Добавили env переменные: TELEGRAM_BOT_TOKEN, GEMINI_API_KEY

3. **Исправили проблемы с Python окружением**
   - Создали `.python-version` с версией `3.12` (вместо дефолтной 3.14)
   - Обновили `requirements.txt`: Pillow 10.2.0 → 11.0.0
   - Почему: Python 3.14 ломал сборку (Pillow KeyError, pydantic-core Rust ошибки)

4. **Создали Blueprint конфиг для правильного деплоя**
   - Файл: `render.yaml`
   - Тип сервиса: **Background Worker** (не Web Service!)
   - Конфиг: Python 3.12, free tier, buildCommand='pip install -r requirements.txt', startCommand='python telegram_gemini_bot.py'
   - Коммит: 9dcad25
   - Почему Blueprint: первый деплой был как Web Service → упал из-за отсутствия HTTP порта (Telegram long-polling не открывает порты)

5. **Убрали токены из кода**
   - GitHub secret-scanning заблокировал push с токенами в ADMIN.md
   - Заменили примеры токенов на плейсхолдеры
   - Коммит: 1422525

### Где остановились ❌

**Проблема:** Бот НЕ задеплоен на Render.

**Причина:** Первый деплой создал **Web Service** вместо **Background Worker**.  
Web Service требует открытый HTTP порт → бот упал через 5 минут (No open ports detected).

**Текущее состояние:**
- Старый сервис на Render: https://dashboard.render.com/web/srv-db8l4ptg1s2s73akv6e0/deploys/dep-db8lesvavr4c738nu220
- Статус: Failed (No open ports detected)
- В GitHub есть правильный `render.yaml` с типом **worker** (коммит 9dcad25)
- Стас устал, остановились на ручном деплое через Dashboard

## ТЕКУЩАЯ ЗАДАЧА

**Цель:** Бот работает в Telegram 24/7 через Render.com.

**Что осталось сделать:**

### Вариант 1: Render.com (через Blueprint) — РЕКОМЕНДУЮ
1. Удалить старый Web Service на Render:
   - Dashboard → Settings → Delete Service
2. Создать новый через Blueprint:
   - New+ → Blueprint → выбрать репо `telegram-gemini-bot`
   - Blueprint прочитает `render.yaml` и создаст Background Worker автоматически
3. Добавить env переменные (TELEGRAM_BOT_TOKEN, GEMINI_API_KEY)
4. Дождаться деплоя → проверить логи → протестировать бота

**Проблема:** Render API недоступен публично, нужен браузер вручную (3 клика).

### Вариант 2: Railway.app или fly.io (через CLI)
- У них есть CLI → можно сделать автоматически
- Стас не выбрал этот вариант

### Вариант 3: Heroku
- Тоже есть CLI
- Более дорогой

## ТЕХНИЧЕСКИЕ ДЕТАЛИ

### Архитектура бота
- **Фреймворк:** aiogram (асинхронный Telegram bot framework)
- **AI модель:** Gemini 1.5 Pro через REST API (обход гео-блокировки России)
- **База данных:** SQLite (`chat_history.db`, хранит последние 50 сообщений на чат)
- **Файлы:** Обрабатывает PDF (первые 10 страниц), Word (200 параграфов), Excel (3 листа × 30 строк), изображения (Gemini Vision)
- **Режим работы:** Long polling (не webhook), поэтому не нужен HTTP порт

### Лимиты и ограничения
- **Gemini API бесплатный тир:** 15 req/min, 1500 req/день
- **Render Free tier:** 750 часов/месяц, 0.1 CPU, 512MB RAM
- **Важно:** На Free tier сервис засыпает через 15 мин бездействия → первый запрос разбудит (холодный старт ~30 сек)
- **Ephemeral storage:** SQLite БД сбрасывается при каждом редеплое

### Проблемы при разработке
1. **Python 3.14 → 3.12:** Новые пакеты не совместимы с 3.14
2. **Web Service → Background Worker:** Long-polling бот != веб-сервер
3. **Secret scanning:** GitHub блокирует push с токенами → убрали из кода
4. **Render не читает runtime.txt:** Нужен `.python-version` или PYTHON_VERSION env var

## СЛЕДУЮЩИЙ ШАГ

**Завтра:**
1. Заходим на Render Dashboard
2. Удаляем старый Web Service
3. New+ → Blueprint → telegram-gemini-bot → Deploy
4. Проверяем логи и тестируем бота

**Альтернатива:** Переехать на Railway.app/fly.io (есть CLI, можно автоматизировать).

## ССЫЛКИ

- Репо: https://github.com/cryptobratru-source/telegram-gemini-bot
- Render Dashboard: https://dashboard.render.com/
- Документация бота: `ADMIN.md` в репо
- Telegram бот: @balamut_gemini_bot

---

**Статус:** Код готов, Blueprint настроен, осталось 3 клика в Dashboard.
