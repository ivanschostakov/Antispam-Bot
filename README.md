# Antispam Bot

Telegram anti-spam bot for moderated group chats. It stores moderated chats, member state, allowed links, and the default quiz questions used to verify newcomers. Message scoring logs are written to `logs/messages/<chat_id>.csv`.

## What It Does

- Moderates only chats registered in the database.
- Automatically adds a group to moderation when the bot is promoted to admin with delete/restrict rights.
- Shows a greeting to newcomers and starts a default quiz captcha when they try to send their first message.
- Uses only the built-in default quiz questions from [src/poll_questions.py](/Users/paylakurusyan/Projects/My/Antispam-Bot/src/poll_questions.py).
- Blocks every link by default for non-admin users unless it is explicitly allowed for that chat.
- Mutes users for 5 minutes if they send a disallowed link.
- Forwards `/report` complaints to one global reports channel.
- Restores active mutes on restart.

## Requirements

- Python 3.13+
- PostgreSQL
- Tesseract OCR installed if you want OCR from images to be used during spam scoring

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Environment Variables

Create a `.env` file in the project root:

```env
ANTISPAM_BOT_TOKEN=123456:telegram_bot_token
REPORTS_CHANNEL_ID=-1001234567890

POSTGRES_DB=antispam_bot_db
POSTGRES_USER=antispam_user
POSTGRES_PASSWORD=change_me
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
```

## Database Setup

Create the database and user, then run migrations:

```bash
alembic upgrade head
```

The default quiz questions from [src/poll_questions.py](/Users/paylakurusyan/Projects/My/Antispam-Bot/src/poll_questions.py) are seeded automatically on first start if the table is empty.

## Run

```bash
python run.py
```

The bot entrypoint is [run.py](/Users/paylakurusyan/Projects/My/Antispam-Bot/run.py), which starts polling through [src/bot/main.py](/Users/paylakurusyan/Projects/My/Antispam-Bot/src/bot/main.py).

## How Moderation Works

1. Add a Telegram group or supergroup to the moderated list, or simply promote the bot to admin with moderation rights.
2. When a user joins, the bot stores their state and sends a greeting.
3. When that user tries to send the first message, the bot deletes it and starts one quiz captcha in the same chat using a random default question.
4. If the user answers correctly, they can speak normally.
5. If the user fails or times out 3 times, they stay restricted until an admin unmutes them.
6. If a verified non-admin user posts a link not present in that chat's allow-list, the message is deleted and the user is muted for 5 minutes.

## Admin Commands

Use these inside a moderated chat unless noted otherwise.

- `/chat_add <chat_id>`: add a chat to moderation.
- `/chat_remove <chat_id>`: remove a chat from moderation.
- `/chat_list`: list moderated chats.
- `/set_greeting`: show current greeting for this chat.
- `/set_greeting <text>`: set the greeting shown to newcomers.
- `/set_greeting clear`: remove the greeting.
- `/set_greetings <chat_id> <html text>`: set greeting for a moderated chat from private chat or another admin context.
- `/set_greetings <chat_id> clear`: remove greeting for that chat.
- `/allow_link <domain_or_link>`: allow a domain or Telegram link for this chat.
- `/unallow_link <domain_or_link>`: remove an allowed domain or link.
- `/allowed_links`: export the allow-list for this chat.
- `/whitelist add <user_id>` or reply with `/whitelist add`: exempt a user from captcha and link restrictions.
- `/whitelist remove <user_id>`: remove a user from the whitelist.
- `/mute <minutes>` as reply: mute a user.
- `/unmute <user_id>` or reply with `/unmute`: restore user permissions and reset captcha state.
- `/spam` as reply: mark a replied message as spam and restrict the sender.
- `/get_thread`: return the current Telegram thread id.

Admins can also use the bot in private chat for the OCR/classifier helper path implemented in [src/bot/services/admin_flow.py](/Users/paylakurusyan/Projects/My/Antispam-Bot/src/bot/services/admin_flow.py).

## User Command

- `/report` as reply: forward the replied message and the report message to `REPORTS_CHANNEL_ID`

## Logs

Scored messages are appended to per-chat CSV files:

```text
logs/messages/<chat_id>.csv
```

Columns:

```text
TimestampUTC,ChatID,UserID,MessageID,Message,PredictedProba,TrueLabel
```

## Notes

- Only chats present in `moderated_chats` are moderated.
- Only the default quiz-question pool is used for captcha.
- The bot creates database tables on startup too, but Alembic migrations should still be treated as the source of truth.
