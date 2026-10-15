# Управление Telegram ботом с Gemini API

**Последнее обновление:** 2026-10-16

---

## 🤖 Информация о боте

**Telegram бот:** @balamut_gemini_bot  
**GitHub:** https://github.com/cryptobratru-source/telegram-gemini-bot  
**Деплой:** Render.com (ожидает настройки)

### Токены и ключи

Храним в Environment Variables на Render (не в коде):
- `TELEGRAM_BOT_TOKEN` — токен из @BotFather
- `GEMINI_API_KEY` — ключ из AI Studio

**Gemini Project:** gen-lang-client-0438544452 (Free tier, 15 req/min, 1500 req/day)

---

## 📋 Возможности бота

- ✅ Бесконечная память (SQLite, последние 50 сообщений как контекст)
- ✅ Чтение PDF (первые 10 страниц)
- ✅ Чтение Word (первые 200 параграфов)
- ✅ Чтение Excel (первые 3 листа, 30 строк)
- ✅ Анализ изображений (через Gemini Vision)
- ⏳ Голосовые сообщения (placeholder, требует реализации)

**Как работает:**
- Бот отвечает на: @balamut_gemini_bot или Reply на его сообщения
- Все сообщения сохраняются в `chat_history.db`
- Контекст: последние 50 сообщений чата отправляются в Gemini

---

## 🚀 Деплой на Render.com

### Почему Render?
Gemini API **геоблокирован из России** (400 User location is not supported). Render.com даёт бесплатный сервер за границей (750 часов/месяц).

### Шаги деплоя:

1. **Зайти на render.com**
   - https://render.com → Sign up with GitHub
   - Использовать аккаунт: cryptobratru-source (cryptobratru@gmail.com)

2. **Создать Web Service**
   - Dashboard → New → Web Service
   - Connect repository: `telegram-gemini-bot`

3. **Настройки сервиса**
   - Name: `telegram-gemini-bot`
   - Region: любой (по умолчанию)
   - Branch: `master`
   - Runtime: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python telegram_gemini_bot.py`

4. **Environment Variables**
   ```
   TELEGRAM_BOT_TOKEN = <токен из @BotFather>
   GEMINI_API_KEY = <ключ из AI Studio>
   ```

5. **Deploy**
   - Create Web Service → ждать ~5 минут
   - Логи покажут: "Бот запущен успешно! Команды: /start, /help"

---

## 🔧 Локальный запуск (для тестов)

**НЕ РАБОТАЕТ из России** (геоблокировка Gemini API).

```bash
cd telegram_gemini_bot
python telegram_gemini_bot.py
```

Для остановки: `Ctrl+C`

---

## 📊 Мониторинг

### Логи на Render

1. Зайти в Render Dashboard
2. Выбрать сервис `telegram-gemini-bot`
3. Вкладка **Logs**

**Что смотреть:**
- `Бот запущен успешно!` — всё OK
- `400 User location is not supported` — геоблокировка (не должно быть на Render)
- `401 Unauthorized` — неверный токен
- `429 Too Many Requests` — превышен лимит (15 req/min)

### Статус бота в Telegram

Написать боту: `/start` или `/help`

Если бот не отвечает:
1. Проверить логи на Render
2. Проверить статус сервиса (Dashboard → Status)
3. Перезапустить сервис (Dashboard → Manual Deploy → Deploy latest commit)

---

## 🔄 Обновление кода

### Автоматический деплой

Render автоматически деплоит при `git push`:

```bash
cd telegram_gemini_bot
git add .
git commit -m "feat: описание изменений"
git push
```

Render подхватит изменения и задеплоит ~5 минут.

### Ручной деплой

Render Dashboard → telegram-gemini-bot → Manual Deploy → Deploy latest commit

---

## 🐛 Решение проблем

### Бот не отвечает

1. **Проверить статус на Render:**
   - Dashboard → telegram-gemini-bot → Status: должен быть "Live"

2. **Проверить логи:**
   - Dashboard → Logs → ищем ошибки

3. **Перезапустить:**
   - Dashboard → Manual Deploy → Deploy latest commit

### Ошибка "400 User location is not supported"

**Причина:** Gemini API вызывается из России.

**Решение:** Убедиться, что бот запущен на Render, а не локально.

### Ошибка "429 Too Many Requests"

**Причина:** Превышен лимит Free tier (15 req/min, 1500 req/day).

**Решение:**
1. Подождать 1 минуту
2. Если лимит 1500 req/day исчерпан — ждать до следующего дня
3. Если нужно больше — апгрейд Gemini API (но тогда уже не бесплатно)

### Бот читает не все сообщения в группе

**Причина:** Group Privacy включён.

**Решение:** @BotFather → выбрать бота → Group Privacy → Turn off

---

## 📁 Структура проекта

```
telegram_gemini_bot/
├── telegram_gemini_bot.py  # основной скрипт
├── requirements.txt        # зависимости
├── .env                    # токены (не в git)
├── .gitignore              # исключения для git
├── Procfile                # команда запуска для Render
├── render.yaml             # конфигурация Render
├── README.md               # документация для разработчиков
└── ADMIN.md                # этот файл (администрирование)
```

### База данных

`chat_history.db` (SQLite):
- Таблица `messages`: chat_id, user_id, username, message_text, timestamp
- Хранится на сервере Render
- Сбрасывается при каждом деплое (ephemeral storage на Free tier)

**Для сохранения истории между деплоями:**
- Upgrade на Render до платного плана с persistent disk
- Или подключить внешнюю БД (PostgreSQL)

---

## 🔐 Безопасность

### Токены

- **Не коммитить** `.env` в git (уже в `.gitignore`)
- Токены хранятся только в Environment Variables на Render
- Если токен утёк → пересоздать:
  - Telegram: @BotFather → /revoke
  - Gemini: https://aistudio.google.com → API keys → Delete

### Доступ к боту

- Бот работает в любых группах, куда его добавили
- Отвечает только на @mention или Reply
- Не отправляет данные никуда кроме Gemini API

---

## 💰 Стоимость

**Полностью бесплатно:**
- ✅ Telegram Bot API (бесплатно навсегда)
- ✅ Gemini API Free tier (15 req/min, 1500 req/day)
- ✅ Render.com Free tier (750 часов/месяц = 31 день × 24 часа)
- ✅ GitHub (публичный репозиторий)

**Ограничения Free tier:**
- Render: сервис засыпает после 15 минут неактивности, просыпается ~1 минута
- Gemini: 1500 запросов в день (для группы из 3 человек вполне достаточно)

---

## 📞 Контакты

**Разработчик:** Claude (Эйдос)  
**GitHub:** cryptobratru-source  
**Проект:** uLiberti / Balamut
