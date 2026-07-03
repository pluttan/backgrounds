<div align="center">

# Backgrounds

**Wallpaper collection with a Telegram sorting bot**


</div>

A wallpaper management toolkit: a curated image collection plus a Telegram bot that presents each wallpaper and lets you sort it into categories via inline keyboard buttons. New images can be pulled in from GitHub repositories or from the comment threads of Telegram channels.

## ■ Features

- ❖ **Telegram sorting bot** — browse wallpapers in batches and file each into a category, skip, or trash with inline buttons
- ❖ **Category management** — create and delete named categories on the fly; sorted images are moved into matching subfolders
- ❖ **Trash with restore** — deleted images move to a `.trash` folder; browse, restore, purge, or empty it from the bot
- ❖ **GitHub repo importer** — clone a wallpaper repo (`git clone --depth 1`) and pull every image into the collection
- ❖ **Channel downloader** — fetch images from a Telegram channel's discussion (comments) group via Telethon, resuming from the last seen message
- ❖ **Session generator** — `gen_session.py` produces a Telethon string session for channel access
- ❖ **Access control & proxy** — optional `ALLOWED_USERS` whitelist and `HTTP_PROXY` for both the bot and Telethon

## ■ Stack

<div align="center">

| Component | Technology |
|-----------|------------|
| Bot | Python 3, aiogram (FSM, inline keyboards) |
| Channel downloader | Telethon |
| Repo importer | git (subprocess) |
| Config | python-dotenv |
| Proxy | python-socks |

</div>

## ■ How It Works

```
1. Configure .env with BOT_TOKEN (and optionally API_ID/API_HASH/TG_SESSION for channel access).
2. Optionally run gen_session.py to produce a Telethon string session for channel downloads.
3. Start the bot pointing at a folder; send /start in Telegram to begin browsing.
4. The bot presents each wallpaper with inline buttons — sort into a named category, skip, or trash it.
5. Sorted images are moved into matching subfolders; trashed images go to .trash and can be restored later.
6. New wallpapers can be imported at any time via the GitHub repo importer or the Telegram channel downloader.
```

## ■ Usage

```bash
# 1. Configure .env (BOT_TOKEN required; API_ID/API_HASH/TG_SESSION for channels;
#    ALLOWED_USERS and HTTP_PROXY optional)
cp .env.example .env

# 2. (optional) Generate a Telethon session for channel downloads
python src/gen_session.py

# 3. Run the bot on a folder (defaults to ./images), then send /start in Telegram
python src/sort_bot.py [path_to_folder]
```

## ■ Repository Structure

```
backgrounds/
├── src/
│   ├── sort_bot.py      # Telegram sorting bot (aiogram + Telethon)
│   └── gen_session.py   # Telethon string session generator
├── images/              # wallpaper collection (sorted into category subfolders)
└── .env.example         # config template
```

## ■ License

MIT © [pluttan](https://github.com/pluttan)
