![Header](header.png)

<div align="center">

# Backgrounds

**Коллекция обоев с Telegram-ботом для сортировки**

[![License](https://img.shields.io/badge/license-MIT-2C2C2C?style=for-the-badge&labelColor=1E1E1E)](LICENSE)
[![Python](https://img.shields.io/badge/python-3-2C2C2C?style=for-the-badge&logo=python&labelColor=1E1E1E)]()
[![Telegram](https://img.shields.io/badge/telegram-bot-2C2C2C?style=for-the-badge&logo=telegram&labelColor=1E1E1E)]()

</div>

Инструментарий для управления обоями: курируемая коллекция изображений и Telegram-бот, который показывает каждое обои и позволяет раскладывать их по категориям с помощью кнопок встроенной клавиатуры. Новые изображения можно подтягивать из GitHub-репозиториев или из тредов с комментариями Telegram-каналов.

## ■ Возможности

- ❖ **Telegram-бот сортировки** — просматривайте обои пачками и отправляйте каждое в категорию, пропускайте или удаляйте встроенными кнопками
- ❖ **Управление категориями** — создавайте и удаляйте именованные категории на лету; отсортированные изображения перемещаются в соответствующие подпапки
- ❖ **Корзина с восстановлением** — удалённые изображения попадают в папку `.trash`; можно просматривать, восстанавливать, очищать или удалять их через бота
- ❖ **Импорт из GitHub-репозитория** — склонировать репозиторий с обоями (`git clone --depth 1`) и перетянуть все изображения в коллекцию
- ❖ **Загрузчик из канала** — скачивайте изображения из группы обсуждений (комментариев) Telegram-канала через Telethon, возобновляя загрузку с последнего обработанного сообщения
- ❖ **Генератор сессии** — `gen_session.py` создаёт строковую сессию Telethon для доступа к каналам
- ❖ **Контроль доступа и прокси** — опциональный белый список `ALLOWED_USERS` и `HTTP_PROXY` для бота и Telethon

## ■ Стек

<div align="center">

| Компонент | Технология |
|-----------|------------|
| Бот | Python 3, aiogram (FSM, inline keyboards) |
| Загрузчик из канала | Telethon |
| Импорт из репозитория | git (subprocess) |
| Конфигурация | python-dotenv |
| Прокси | python-socks |

</div>

## ■ Repository Structure

```
backgrounds/
├── src/
│   ├── sort_bot.py      # Telegram sorting bot (aiogram + Telethon)
│   └── gen_session.py   # Telethon string session generator
├── images/              # wallpaper collection (sorted into category subfolders)
└── .env.example         # config template
```

## ■ Запуск

```bash
# 1. Настройте .env (BOT_TOKEN обязателен; API_ID/API_HASH/TG_SESSION для каналов;
#    ALLOWED_USERS и HTTP_PROXY опциональны)
cp .env.example .env

# 2. (опционально) Сгенерируйте сессию Telethon для загрузки из каналов
python src/gen_session.py

# 3. Запустите бота для папки (по умолчанию ./images), затем отправьте /start в Telegram
python src/sort_bot.py [path_to_folder]
```

## ■ License

MIT © [pluttan](https://github.com/pluttan)
