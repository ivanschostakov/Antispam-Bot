# Antispam Bot

Telegram antispam bot for moderated group chats. It stores moderated chats, member state, poll questions, and allowed links in PostgreSQL, uses a quiz-based captcha for newcomers, and writes per-chat message scoring logs to `logs/messages/<chat_id>.csv`.

## What It Does

- Moderates only chats that are registered in the database.
- Automatically adds a group to moderation when the bot is promoted to admin with delete/restrict rights.
- Challenges new users with a quiz captcha before they can speak.
- Uses chat-specific poll questions, or falls back to default seeded questions.
- Blocks every link by default for non-admin users unless it is explicitly allowed for that chat.
- Mutes users for 5 minutes if they send a disallowed link.
- Supports a per-chat greeting shown before the captcha.
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

Default poll questions from [`src/poll_questions.py`](/Users/paylakurusyan/Projects/My/Antispam-Bot/src/poll_questions.py) are seeded automatically on first start if no default questions exist.

## Run

```bash
python run.py
```

The bot entrypoint is [`run.py`](/Users/paylakurusyan/Projects/My/Antispam-Bot/run.py), which starts polling through [`src/bot/main.py`](/Users/paylakurusyan/Projects/My/Antispam-Bot/src/bot/main.py).

## How Moderation Works

1. Add a Telegram group or supergroup to the moderated list.
   Or simply promote the bot to admin with moderation rights and it will register the chat automatically.
2. When a user joins, they are tracked in DB but cannot freely speak until they pass the quiz captcha.
3. If they answer correctly, they are allowed to send messages.
4. If they fail 3 captcha attempts, they are restricted until an admin unmutes them.
5. If a passed non-admin user posts a link not present in that chat's allow-list, the message is deleted and the user is muted for 5 minutes.

## Admin Commands

Use these inside a moderated chat unless noted otherwise.

- `/chat_add <chat_id>`: add a chat to moderation.
- `/chat_remove <chat_id>`: remove a chat from moderation.
- `/chat_list`: list moderated chats.
- `/set_greeting`: show current greeting for this chat.
- `/set_greeting <text>`: set greeting shown before captcha.
- `/set_greeting clear`: remove greeting.
- `/set_greetings <chat_id> <html text>`: set greeting for a moderated chat from private chat or another admin context.
- `/set_greetings <chat_id> clear`: remove greeting for that chat.
- `/poll_add`: send CSV template for bulk poll import.
- Send the filled CSV back with caption `/poll_add`: bulk add poll questions for this chat.
- `/poll_list`: export question list for this chat. If the chat has no custom questions, default questions are listed.
- `/poll_delete <question_id>`: delete one custom question from this chat.
- `/allow_link <domain_or_link>`: allow a domain or Telegram link for this chat.
- `/unallow_link <domain_or_link>`: remove an allowed domain or link.
- `/allowed_links`: export allow-list for this chat.
- `/whitelist add <user_id>` or reply with `/whitelist add`: exempt a user from captcha/link restrictions.
- `/whitelist remove <user_id>`: remove user from whitelist.
- `/mute <minutes>` as reply: mute a user.
- `/unmute <user_id>` or reply with `/unmute`: restore user permissions and reset captcha state.
- `/spam` as reply: mark a replied message as spam and restrict the sender.
- `/get_thread`: return current Telegram thread id.

Admins can also use the bot in private chat for the OCR/classifier helper path implemented in [`src/bot/services/admin_flow.py`](/Users/paylakurusyan/Projects/My/Antispam-Bot/src/bot/services/admin_flow.py).

## Poll CSV Format

The CSV import format is:

```csv
question,right,wrong1,wrong2,wrong3,
How many legs does a cat have?,4,2,3,6,
```

Rules:

- Exactly 5 columns are required: `question`, `right`, `wrong1`, `wrong2`, `wrong3`
- All 4 answers must be non-empty
- All 4 answers must be unique
- The bot shuffles answer order when sending the quiz, so the correct answer is not fixed to one position

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
- Chat-specific poll questions override defaults; if a chat has none, defaults are used.
- The bot creates database tables on startup too, but Alembic migrations should still be treated as the source of truth.
