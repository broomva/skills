# Discord Channel Setup

## Step 1: Create a Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application**, name it
3. Go to **Bot** in the sidebar, create a username
4. Click **Reset Token**, copy it (shown only once)
5. **Critical**: Scroll to **Privileged Gateway Intents**, enable **Message Content Intent** — without this, messages arrive with empty content and the bot silently ignores them

## Step 2: Invite the Bot to a Server

Go to **OAuth2 → URL Generator**:
- Select `bot` scope
- Enable permissions: View Channels, Send Messages, Send Messages in Threads, Read Message History, Attach Files, Add Reactions
- For channel/thread creation, also enable: Manage Channels, Create Public Threads, Create Private Threads, Manage Threads

Generate the URL with the desired permissions. Replace `CLIENT_ID` with the application ID:
```
https://discord.com/oauth2/authorize?client_id=CLIENT_ID&permissions=395405544528&scope=bot
```

The permission value `395405544528` includes all recommended permissions.

## Step 3: Install the Plugin

```
/plugin install discord@claude-plugins-official
```

If not found:
```
/plugin marketplace add anthropics/claude-plugins-official
/plugin install discord@claude-plugins-official
```

## Step 4: Configure the Token

```
/discord:configure <token>
```

This saves `DISCORD_BOT_TOKEN=...` to `~/.claude/channels/discord/.env`.

Manual alternative:
```bash
mkdir -p ~/.claude/channels/discord
printf 'DISCORD_BOT_TOKEN=<token>\n' > ~/.claude/channels/discord/.env
chmod 600 ~/.claude/channels/discord/.env
```

## Step 5: Launch with Channel Flag

```bash
claude --channels plugin:discord@claude-plugins-official
```

**Important**: The Discord MCP server may show as "failed" on initial startup (race condition). After launch, run `/mcp`, navigate to `plugin:discord:discord`, and select **Reconnect**. It connects successfully on retry.

## Step 6: Pair Your Account

1. DM the bot on Discord
2. Bot replies with a 6-character pairing code
3. In Claude Code: `/discord:access pair <code>`

## Step 7: Lock Down

```
/discord:access policy allowlist
```

## Discord-Specific Notes

### Verify Token
```bash
TOKEN=$(grep DISCORD_BOT_TOKEN ~/.claude/channels/discord/.env | cut -d= -f2)
curl -s -H "Authorization: Bot $TOKEN" https://discord.com/api/v10/users/@me | python3 -m json.tool
```

### Guild Channels

Discord guild channels are opt-in by channel ID (not guild ID). Enable Developer Mode (User Settings → Advanced) to copy IDs via right-click.

```
/discord:access group add <channel_id>                # Responds to @mentions only
/discord:access group add <channel_id> --no-mention   # Responds to all messages
/discord:access group add <channel_id> --allow id1,id2  # Restrict to specific users
/discord:access group rm <channel_id>                  # Disable
```

Threads inherit their parent channel's opt-in — no separate entry needed.

### Listing Server Channels via API

To programmatically list channels and their IDs:
```bash
TOKEN=$(grep DISCORD_BOT_TOKEN ~/.claude/channels/discord/.env | cut -d= -f2)

# List guilds
curl -s -H "Authorization: Bot $TOKEN" https://discord.com/api/v10/users/@me/guilds

# List channels in a guild (type 0 = text, 2 = voice, 4 = category)
curl -s -H "Authorization: Bot $TOKEN" https://discord.com/api/v10/guilds/GUILD_ID/channels
```

### Creating Channels and Threads via API

The bot can create channels and threads if it has Manage Channels permission:

```bash
TOKEN=$(grep DISCORD_BOT_TOKEN ~/.claude/channels/discord/.env | cut -d= -f2)

# Create a text channel
curl -s -X POST "https://discord.com/api/v10/guilds/GUILD_ID/channels" \
  -H "Authorization: Bot $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "channel-name", "type": 0, "topic": "Channel description"}'

# Create a thread (type 11 = public thread)
curl -s -X POST "https://discord.com/api/v10/channels/CHANNEL_ID/threads" \
  -H "Authorization: Bot $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "thread-name", "type": 11, "auto_archive_duration": 1440}'

# Send a message in a channel or thread
curl -s -X POST "https://discord.com/api/v10/channels/CHANNEL_OR_THREAD_ID/messages" \
  -H "Authorization: Bot $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Hello from the bot!"}'
```

After creating a channel, add it to access.json for the bot to respond there. Threads inherit from their parent channel automatically.

### Tools Available

| Tool | Purpose |
|---|---|
| `reply` | Send to channel, auto-chunks at 2000 chars, supports file attachments (max 10, 25MB each) |
| `react` | Add emoji reaction (Unicode or custom `<:name:id>`) |
| `edit_message` | Edit bot's own messages (no push notification) |
| `fetch_messages` | Pull recent history (max 100, oldest-first) |
| `download_attachment` | Download message attachments to inbox |

### Delivery Settings

```
/discord:access set ackReaction 🔨           # Seen acknowledgment (empty string disables)
/discord:access set replyToMode first        # Thread first chunk only (first/all/off)
/discord:access set textChunkLimit 2000      # Discord hard limit is 2000
/discord:access set chunkMode newline        # Split at paragraph boundaries
/discord:access set mentionPatterns '["^hey claude\\b"]'
```

### Multiple Bot Instances

To run multiple bots with different tokens and separate allowlists, set `DISCORD_STATE_DIR` to a different directory per instance:
```bash
DISCORD_STATE_DIR=~/.claude/channels/discord-bot2 claude --channels plugin:discord@claude-plugins-official
```

### Recommended Discord Permission Value

`395405544528` includes:
- View Channels, Send Messages, Embed Links, Read Message History
- Attach Files, Add Reactions, Send Messages in Threads
- Create Public/Private Threads, Manage Threads, Manage Channels
