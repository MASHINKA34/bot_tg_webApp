# Clicker Game - Telegram Web App

## Описание
Telegram Web App кликер-игра с фермами, ежедневными бонусами и лидербордом.

## Структура проекта
```
clicker_webapp/
├── backend/
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── clicker.py      # Эндпоинты кликера
│   │   ├── daily.py        # Ежедневные бонусы
│   │   ├── farms.py        # Система ферм
│   │   └── leaderboard.py  # Лидерборд
│   ├── __init__.py
│   ├── config.py           # Конфигурация
│   ├── database.py         # Подключение к БД
│   ├── models.py           # SQLAlchemy модели
│   └── schemas.py          # Pydantic схемы
├── frontend/
│   ├── index.html          # HTML интерфейс
│   ├── styles.css          # Стили
│   └── app.js              # JavaScript логика
├── bot.py                  # Telegram бот
├── main.py                 # FastAPI приложение
├── .env                    # Переменные окружения
└── requirements.txt        # Зависимости
```

## Установка

1. **Установи зависимости:**
```bash
pip install -r requirements.txt
```

2. **Настрой .env файл:**
```env
BOT_TOKEN=your_bot_token
WEBAPP_URL=your_ngrok_url
DATABASE_URL=sqlite+aiosqlite:///./clicker.db
SECRET_KEY=your_secret_key
```

3. **Запустить ngrok:**
```bash
ngrok http 8000
```

4. **Обнови WEBAPP_URL в .env** с ngrok URL

## Запуск

### Запуск FastAPI сервера:
```bash
python main.py
```

### Запуск Telegram бота (в другом терминале):
```bash
python bot.py
```