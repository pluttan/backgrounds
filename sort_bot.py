"""
Telegram-бот для сортировки обоев по категориям.

Использование:
    BOT_TOKEN=... python sort_bot.py [путь_к_папке]

Для скачивания из Telegram-каналов дополнительно:
    API_ID=... API_HASH=... (с my.telegram.org)
    При первом запуске попросит номер телефона + код в консоли.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# --- Конфигурация ---

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
API_ID = os.environ.get("API_ID", "")
API_HASH = os.environ.get("API_HASH", "")
IMAGE_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
STATE_FILE = IMAGE_DIR / ".sort_state.json"
SESSION_FILE = IMAGE_DIR / ".telethon_session"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}

router = Router()
tg_client = None  # Telethon client, инициализируется в main()


# --- Состояния ---

class SortStates(StatesGroup):
    browsing = State()
    adding_category = State()
    cloning_repo = State()
    channel_url = State()


# --- Утилиты ---

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"categories": [], "sorted": [], "deleted": []}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def get_unsorted(st: dict) -> list[Path]:
    done = set(st.get("sorted", [])) | set(st.get("deleted", []))
    files = []
    for f in sorted(IMAGE_DIR.iterdir()):
        if f.is_file() and f.suffix.lower() in IMAGE_EXTS and f.name not in done:
            files.append(f)
    return files


def count_in_cat(cat: str) -> int:
    d = IMAGE_DIR / cat
    if not d.is_dir():
        return 0
    return sum(1 for f in d.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTS)


def get_trash_files() -> list[Path]:
    trash = IMAGE_DIR / ".trash"
    if not trash.is_dir():
        return []
    return sorted(f for f in trash.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTS)


def count_trash() -> int:
    return len(get_trash_files())


def clone_and_extract(url: str) -> tuple[int, str]:
    """Клонирует репо, копирует изображения в IMAGE_DIR, удаляет клон."""
    repo_name = url.rstrip("/").split("/")[-1].removesuffix(".git")
    tmp_dir = IMAGE_DIR / f".clone_{repo_name}"

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)

    subprocess.run(
        ["git", "clone", "--depth", "1", url, str(tmp_dir)],
        check=True, capture_output=True, text=True,
    )

    added = 0
    for f in tmp_dir.rglob("*"):
        if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
            dest = IMAGE_DIR / f.name
            if dest.exists():
                dest = IMAGE_DIR / f"{repo_name}_{f.name}"
            if not dest.exists():
                shutil.copy2(str(f), str(dest))
                added += 1

    shutil.rmtree(tmp_dir)
    return added, repo_name


def parse_channel(url: str) -> str:
    """Извлекает username канала из URL или возвращает как есть."""
    url = url.strip().rstrip("/")
    if url.startswith("https://t.me/"):
        return url.split("https://t.me/")[1].split("/")[0]
    if url.startswith("@"):
        return url[1:]
    return url


async def download_from_channel(channel_input: str, progress_cb=None) -> tuple[int, str]:
    """Скачивает изображения из комментов канала через Telethon."""
    from telethon.tl.functions.channels import GetFullChannelRequest

    channel_username = parse_channel(channel_input)
    channel = await tg_client.get_entity(channel_username)
    full = await tg_client(GetFullChannelRequest(channel))

    discussion = full.full_chat.linked_chat_id
    if not discussion:
        raise ValueError("У канала нет группы обсуждения (комментариев)")

    discussion_group = await tg_client.get_entity(discussion)

    st = load_state()
    channels_state = st.setdefault("channels", {})
    last_id = channels_state.get(channel_username, 0)

    added = 0
    new_last_id = last_id

    async for msg in tg_client.iter_messages(discussion_group, min_id=last_id):
        if msg.id > new_last_id:
            new_last_id = msg.id

        if not (msg.photo or msg.document):
            continue

        # проверяем что документ — изображение
        if msg.document:
            mime = msg.document.mime_type or ""
            if not mime.startswith("image/"):
                continue

        fname = f"tg_{channel_username}_{msg.id}"
        # определяем расширение
        if msg.photo:
            fname += ".jpg"
        elif msg.document:
            ext = ""
            for attr in msg.document.attributes:
                if hasattr(attr, "file_name") and attr.file_name:
                    ext = Path(attr.file_name).suffix
                    break
            if not ext:
                mime = msg.document.mime_type or ""
                ext = {"image/png": ".png", "image/webp": ".webp",
                       "image/gif": ".gif", "image/bmp": ".bmp"}.get(mime, ".jpg")
            fname += ext

        dest = IMAGE_DIR / fname
        if dest.exists():
            continue

        await tg_client.download_media(msg, file=str(dest))
        added += 1

        if progress_cb and added % 10 == 0:
            await progress_cb(added)

    channels_state[channel_username] = new_last_id
    save_state(st)
    return added, channel_username


# --- Клавиатуры ---

def build_menu_kb(st: dict) -> InlineKeyboardMarkup:
    unsorted = get_unsorted(st)
    cats = st.get("categories", [])
    rows = [
        [InlineKeyboardButton(
            text=f"Сортировать ({len(unsorted)} шт)",
            callback_data="menu:sort",
        )],
        [InlineKeyboardButton(
            text=f"Категории ({len(cats)})",
            callback_data="menu:cats",
        )],
        [InlineKeyboardButton(
            text=f"Корзина ({count_trash()} шт)",
            callback_data="menu:trash",
        )],
        [InlineKeyboardButton(text="Клонировать репо", callback_data="menu:clone")],
    ]
    if tg_client:
        rows.append([InlineKeyboardButton(text="Скачать из канала", callback_data="menu:channel")])
    rows.append([InlineKeyboardButton(text="Сброс прогресса", callback_data="menu:reset")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_sort_kb(categories: list[str]) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for cat in categories:
        row.append(InlineKeyboardButton(text=cat, callback_data=f"cat:{cat}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    rows.append([InlineKeyboardButton(text="+ Категория", callback_data="add_cat")])
    rows.append([
        InlineKeyboardButton(text="<< Пропустить >>", callback_data="skip"),
        InlineKeyboardButton(text="Удалить", callback_data="delete"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_cats_kb(cats: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for cat in cats:
        n = count_in_cat(cat)
        rows.append([
            InlineKeyboardButton(text=f"{cat} ({n} шт)", callback_data="noop"),
            InlineKeyboardButton(text="X", callback_data=f"rmcat:{cat}"),
        ])
    rows.append([InlineKeyboardButton(text="<< Меню", callback_data="menu:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# --- Отправка текущей обоины ---

async def send_current(bot: Bot, chat_id: int, fsm: FSMContext):
    st = load_state()
    unsorted = get_unsorted(st)

    if not unsorted:
        await bot.send_message(chat_id, "Все обои отсортированы!", reply_markup=build_menu_kb(st))
        return

    current = unsorted[0]
    total = len(unsorted) + len(st.get("sorted", [])) + len(st.get("deleted", []))
    done_n = len(st.get("sorted", [])) + len(st.get("deleted", []))

    await fsm.update_data(current_file=current.name)
    await fsm.set_state(SortStates.browsing)

    caption = f"[{done_n + 1}/{total}]  осталось: {len(unsorted)}\n<code>{current.name}</code>"
    kb = build_sort_kb(st.get("categories", []))

    try:
        photo = FSInputFile(current)
        await bot.send_photo(chat_id, photo=photo, caption=caption, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        await bot.send_message(
            chat_id,
            f"Не удалось отправить <code>{current.name}</code>: {e}\nПропускаю...",
            parse_mode="HTML",
        )
        st.setdefault("deleted", []).append(current.name)
        save_state(st)
        await send_current(bot, chat_id, fsm)


async def delete_msg(msg):
    try:
        await msg.delete()
    except Exception:
        pass


# --- /start ---

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    st = load_state()
    unsorted = get_unsorted(st)
    cats = st.get("categories", [])
    text = (
        f"Обоев для сортировки: <b>{len(unsorted)}</b>\n"
        f"Категории: {', '.join(cats) if cats else '—'}"
    )
    await message.answer(text, reply_markup=build_menu_kb(st), parse_mode="HTML")


# --- Меню ---

@router.callback_query(F.data == "menu:sort")
async def menu_sort(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await delete_msg(cb.message)
    await send_current(cb.bot, cb.message.chat.id, state)


@router.callback_query(F.data == "menu:cats")
async def menu_cats(cb: CallbackQuery):
    st = load_state()
    cats = st.get("categories", [])
    await cb.answer()
    if not cats:
        text = "Категорий пока нет.\nДобавь при сортировке кнопкой «+ Категория»."
    else:
        text = "Категории (X — удалить):"
    await cb.message.edit_text(text, reply_markup=build_cats_kb(cats))


@router.callback_query(F.data == "menu:clone")
async def menu_clone(cb: CallbackQuery, state: FSMContext):
    await state.set_state(SortStates.cloning_repo)
    await cb.answer()
    await cb.message.edit_text(
        "Отправь ссылку на GitHub-репозиторий с обоями:\n\n"
        "<i>Например: https://github.com/dharmx/walls</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="<< Отмена", callback_data="menu:back")],
        ]),
    )


@router.callback_query(F.data == "menu:channel")
async def menu_channel(cb: CallbackQuery, state: FSMContext):
    if not tg_client:
        await cb.answer("Telethon не настроен (нужны API_ID и API_HASH)")
        return
    await state.set_state(SortStates.channel_url)
    await cb.answer()

    st = load_state()
    channels = st.get("channels", {})
    if channels:
        rows = []
        for ch in channels:
            rows.append([InlineKeyboardButton(text=f"@{ch}", callback_data=f"dlchan:{ch}")])
        rows.append([InlineKeyboardButton(text="<< Отмена", callback_data="menu:back")])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        await cb.message.edit_text(
            "Выбери канал или отправь новую ссылку:\n\n"
            "<i>Например: https://t.me/anime_wallpaperspk</i>",
            parse_mode="HTML",
            reply_markup=kb,
        )
    else:
        await cb.message.edit_text(
            "Отправь ссылку на Telegram-канал:\n\n"
            "<i>Например: https://t.me/anime_wallpaperspk</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="<< Отмена", callback_data="menu:back")],
            ]),
        )


@router.callback_query(F.data == "menu:reset")
async def menu_reset(cb: CallbackQuery):
    st = load_state()
    st["sorted"] = []
    st["deleted"] = []
    save_state(st)
    await cb.answer("Прогресс сброшен")
    unsorted = get_unsorted(st)
    cats = st.get("categories", [])
    text = (
        f"Прогресс сброшен. Категории сохранены.\n\n"
        f"Обоев для сортировки: <b>{len(unsorted)}</b>\n"
        f"Категории: {', '.join(cats) if cats else '—'}"
    )
    await cb.message.edit_text(text, reply_markup=build_menu_kb(st), parse_mode="HTML")


@router.callback_query(F.data == "menu:back")
async def menu_back(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    st = load_state()
    unsorted = get_unsorted(st)
    cats = st.get("categories", [])
    text = (
        f"Обоев для сортировки: <b>{len(unsorted)}</b>\n"
        f"Категории: {', '.join(cats) if cats else '—'}"
    )
    await cb.answer()
    await cb.message.edit_text(text, reply_markup=build_menu_kb(st), parse_mode="HTML")


@router.callback_query(F.data == "noop")
async def on_noop(cb: CallbackQuery):
    await cb.answer()


# --- Корзина ---

async def send_trash_item(bot: Bot, chat_id: int, fsm: FSMContext):
    files = get_trash_files()
    if not files:
        st = load_state()
        await bot.send_message(chat_id, "Корзина пуста.", reply_markup=build_menu_kb(st))
        return

    data = await fsm.get_data()
    idx = data.get("trash_idx", 0)
    if idx >= len(files):
        idx = 0
    current = files[idx]
    await fsm.update_data(trash_idx=idx, trash_file=current.name)

    caption = f"Корзина [{idx + 1}/{len(files)}]\n<code>{current.name}</code>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="<< Пред", callback_data="trash:prev"),
            InlineKeyboardButton(text="След >>", callback_data="trash:next"),
        ],
        [
            InlineKeyboardButton(text="Восстановить", callback_data="trash:restore"),
            InlineKeyboardButton(text="Удалить навсегда", callback_data="trash:rm"),
        ],
        [InlineKeyboardButton(text="Очистить корзину", callback_data="trash:clear")],
        [InlineKeyboardButton(text="<< Меню", callback_data="menu:back")],
    ])

    try:
        photo = FSInputFile(current)
        await bot.send_photo(chat_id, photo=photo, caption=caption, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await bot.send_message(chat_id, f"Не удалось показать {current.name}", reply_markup=kb)


@router.callback_query(F.data == "menu:trash")
async def menu_trash(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await delete_msg(cb.message)
    await state.update_data(trash_idx=0)
    await send_trash_item(cb.bot, cb.message.chat.id, state)


@router.callback_query(F.data == "trash:next")
async def trash_next(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    idx = data.get("trash_idx", 0) + 1
    await state.update_data(trash_idx=idx)
    await cb.answer()
    await delete_msg(cb.message)
    await send_trash_item(cb.bot, cb.message.chat.id, state)


@router.callback_query(F.data == "trash:prev")
async def trash_prev(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    idx = max(data.get("trash_idx", 0) - 1, 0)
    await state.update_data(trash_idx=idx)
    await cb.answer()
    await delete_msg(cb.message)
    await send_trash_item(cb.bot, cb.message.chat.id, state)


@router.callback_query(F.data == "trash:restore")
async def trash_restore(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    filename = data.get("trash_file")
    if not filename:
        await cb.answer("Нет файла")
        return

    src = IMAGE_DIR / ".trash" / filename
    if src.exists():
        shutil.move(str(src), str(IMAGE_DIR / filename))

    st = load_state()
    if filename in st.get("deleted", []):
        st["deleted"].remove(filename)
        save_state(st)

    await cb.answer("Восстановлено")
    await delete_msg(cb.message)
    await send_trash_item(cb.bot, cb.message.chat.id, state)


@router.callback_query(F.data == "trash:rm")
async def trash_rm(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    filename = data.get("trash_file")
    if not filename:
        await cb.answer("Нет файла")
        return

    src = IMAGE_DIR / ".trash" / filename
    if src.exists():
        src.unlink()

    await cb.answer("Удалено навсегда")
    await delete_msg(cb.message)
    await send_trash_item(cb.bot, cb.message.chat.id, state)


@router.callback_query(F.data == "trash:clear")
async def trash_clear(cb: CallbackQuery, state: FSMContext):
    trash = IMAGE_DIR / ".trash"
    if trash.is_dir():
        shutil.rmtree(trash)
    await cb.answer("Корзина очищена")
    await delete_msg(cb.message)
    st = load_state()
    await cb.bot.send_message(cb.message.chat.id, "Корзина очищена.", reply_markup=build_menu_kb(st))


# --- Скачивание из канала ---

async def do_channel_download(bot: Bot, chat_id: int, channel: str, state: FSMContext):
    msg = await bot.send_message(chat_id, f"Скачиваю из @{channel}...")

    async def on_progress(n):
        try:
            await msg.edit_text(f"Скачиваю из @{channel}... ({n} шт)")
        except Exception:
            pass

    try:
        added, name = await download_from_channel(channel, progress_cb=on_progress)
    except Exception as e:
        await msg.edit_text(f"Ошибка: {e}")
        await state.clear()
        return

    st = load_state()
    await msg.edit_text(
        f"@{name}: добавлено <b>{added}</b> изображений.",
        reply_markup=build_menu_kb(st),
        parse_mode="HTML",
    )
    await state.clear()


@router.callback_query(F.data.startswith("dlchan:"))
async def on_dl_channel_btn(cb: CallbackQuery, state: FSMContext):
    channel = cb.data[7:]
    await cb.answer()
    await delete_msg(cb.message)
    await do_channel_download(cb.bot, cb.message.chat.id, channel, state)


@router.message(SortStates.channel_url)
async def on_channel_url(message: Message, state: FSMContext):
    channel = parse_channel(message.text)
    if not channel:
        await message.answer("Не удалось разобрать канал, попробуй ещё:")
        return
    await do_channel_download(message.bot, message.chat.id, channel, state)


# --- Клонирование репо ---

@router.message(SortStates.cloning_repo)
async def on_repo_url(message: Message, state: FSMContext):
    url = message.text.strip()
    if not url.startswith("http"):
        await message.answer("Не похоже на ссылку, попробуй ещё:")
        return

    msg = await message.answer("Клонирую репозиторий...")

    try:
        added, repo_name = await asyncio.to_thread(clone_and_extract, url)
    except subprocess.CalledProcessError as e:
        await msg.edit_text(f"Ошибка клонирования:\n<code>{e.stderr[:500]}</code>", parse_mode="HTML")
        return
    except Exception as e:
        await msg.edit_text(f"Ошибка: {e}")
        return

    st = load_state()
    await msg.edit_text(
        f"<b>{repo_name}</b>: добавлено {added} изображений.",
        reply_markup=build_menu_kb(st),
        parse_mode="HTML",
    )
    await state.clear()


# --- Удаление категории ---

@router.callback_query(F.data.startswith("rmcat:"))
async def on_rmcat(cb: CallbackQuery):
    cat = cb.data[6:]
    st = load_state()
    cats = st.get("categories", [])
    if cat in cats:
        cats.remove(cat)
        st["categories"] = cats
        save_state(st)
        await cb.answer(f"«{cat}» удалена")
    else:
        await cb.answer("Уже удалена")
    text = "Категории (X — удалить):" if cats else "Категорий не осталось."
    await cb.message.edit_reply_markup(reply_markup=build_cats_kb(cats))


# --- Сортировка: выбор категории ---

@router.callback_query(F.data.startswith("cat:"))
async def on_category(cb: CallbackQuery, state: FSMContext):
    cat = cb.data[4:]
    data = await state.get_data()
    filename = data.get("current_file")
    if not filename:
        await cb.answer("Нет активного файла")
        return

    src = IMAGE_DIR / filename
    dest_dir = IMAGE_DIR / cat
    dest_dir.mkdir(exist_ok=True)

    if src.exists():
        shutil.move(str(src), str(dest_dir / filename))

    st = load_state()
    st.setdefault("sorted", []).append(filename)
    save_state(st)

    await cb.answer(f"-> {cat}")
    await delete_msg(cb.message)
    await send_current(cb.bot, cb.message.chat.id, state)


# --- Пропуск ---

@router.callback_query(F.data == "skip")
async def on_skip(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    filename = data.get("current_file")
    if not filename:
        await cb.answer("Нет активного файла")
        return

    st = load_state()
    st.setdefault("sorted", []).append(filename)
    save_state(st)

    await cb.answer("Пропущено")
    await delete_msg(cb.message)
    await send_current(cb.bot, cb.message.chat.id, state)


# --- Удалить в корзину ---

@router.callback_query(F.data == "delete")
async def on_delete(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    filename = data.get("current_file")
    if not filename:
        await cb.answer("Нет активного файла")
        return

    src = IMAGE_DIR / filename
    trash = IMAGE_DIR / ".trash"
    trash.mkdir(exist_ok=True)
    if src.exists():
        shutil.move(str(src), str(trash / filename))

    st = load_state()
    st.setdefault("deleted", []).append(filename)
    save_state(st)

    await cb.answer("В корзину")
    await delete_msg(cb.message)
    await send_current(cb.bot, cb.message.chat.id, state)


# --- Добавить категорию (текстовый ввод) ---

@router.callback_query(F.data == "add_cat")
async def on_add_cat(cb: CallbackQuery, state: FSMContext):
    await state.set_state(SortStates.adding_category)
    await cb.answer()
    await cb.message.answer("Напиши название новой категории:")


@router.message(SortStates.adding_category)
async def on_new_category_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("Пустое имя, попробуй ещё:")
        return

    st = load_state()
    cats = st.get("categories", [])
    if name not in cats:
        cats.append(name)
        st["categories"] = cats
        save_state(st)
        (IMAGE_DIR / name).mkdir(exist_ok=True)
        await message.answer(f"Категория «{name}» добавлена.")
    else:
        await message.answer(f"Категория «{name}» уже есть.")

    await send_current(message.bot, message.chat.id, state)


# --- Запуск ---

async def init_telethon():
    global tg_client
    if not API_ID or not API_HASH:
        print("Telethon: API_ID/API_HASH не заданы — скачивание из каналов отключено.")
        return

    from telethon import TelegramClient
    tg_client = TelegramClient(str(SESSION_FILE), int(API_ID), API_HASH)
    await tg_client.start()
    me = await tg_client.get_me()
    print(f"Telethon: авторизован как {me.first_name} (@{me.username})")


async def main():
    if not BOT_TOKEN:
        print("Установи BOT_TOKEN: export BOT_TOKEN=...")
        sys.exit(1)

    await init_telethon()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    print(f"Сортировка папки: {IMAGE_DIR}")
    print(f"Изображений: {len(get_unsorted(load_state()))}")
    print("Бот запущен. /start в Telegram.")

    try:
        await dp.start_polling(bot)
    finally:
        if tg_client:
            await tg_client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
