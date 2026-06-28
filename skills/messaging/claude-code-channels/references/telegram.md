# Telegram Channel Setup

## Step 1: Create a Telegram Bot

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`
3. Choose a display name and username (must end in `bot`)
4. BotFather replies with a bot token like `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`
5. Copy the token

## Step 2: Install the Plugin

```
/plugin install telegram@claude-plugins-official
```

If not found:
```
/plugin marketplace add anthropics/claude-plugins-official
/plugin install telegram@claude-plugins-official
```

## Step 3: Configure the Token

```
/telegram:configure <token>
```

This saves `TELEGRAM_BOT_TOKEN=...` to `~/.claude/channels/telegram/.env`.

Manual alternative:
```bash
mkdir -p ~/.claude/channels/telegram
printf 'TELEGRAM_BOT_TOKEN=<token>\n' > ~/.claude/channels/telegram/.env
chmod 600 ~/.claude/channels/telegram/.env
```

## Step 4: Launch with Channel Flag

```bash
claude --channels plugin:telegram@claude-plugins-official
```

## Step 5: Pair Your Account

1. Open Telegram and DM the bot
2. Bot replies with a 6-character pairing code
3. In Claude Code: `/telegram:access pair <code>`

## Step 6: Lock Down

```
/telegram:access policy allowlist
```

## Telegram-Specific Notes

### Verify Token
```bash
TOKEN=$(grep TELEGRAM_BOT_TOKEN ~/.claude/channels/telegram/.env | cut -d= -f2)
curl -s "https://api.telegram.org/bot$TOKEN/getMe" | python3 -m json.tool
```

### Group Chats

Enable a group by chat ID (negative number for groups):
```
/telegram:access group add -1001654782309
/telegram:access group add -1001654782309 --no-mention
```

### Tools Available

| Tool | Purpose |
|---|---|
| `reply` | Send message to chat, auto-chunks long text |
| `react` | Add emoji reaction (Telegram fixed whitelist only) |
| `edit_message` | Edit bot's own messages |
| `download_attachment` | Fetch photo/file to inbox |

### Delivery Settings

```
/telegram:access set ackReaction 👀          # Seen acknowledgment
/telegram:access set replyToMode first       # Thread first chunk only
/telegram:access set textChunkLimit 4096     # Max chars per message
/telegram:access set chunkMode newline       # Split at paragraph boundaries
/telegram:access set mentionPatterns '["^hey claude\\b"]'
```

### Limitations

- Telegram Bot API has no message history or search
- Photos are auto-downloaded to `~/.claude/channels/telegram/inbox/`
- Bot can only see messages in groups where it's a member and has message access
