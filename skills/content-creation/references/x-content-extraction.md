# X/Twitter Content Extraction — Programmatic Methods

Practical, working methods for extracting text, images, and video from X/Twitter posts in a CLI or agent context.

---

## 1. FxTwitter API (No Auth Required) — Fastest for Agents

The FxTwitter API (used by FixTweet/FxEmbed) returns structured JSON for any public tweet with zero authentication.

### Get tweet data as JSON

```bash
curl -s "https://api.fxtwitter.com/status/TWEET_ID" | jq .
```

### Response includes

- `.tweet.text` — full tweet text
- `.tweet.media.photos[].url` — image URLs (original quality)
- `.tweet.media.videos[].url` — video download URL (highest quality mp4)
- `.tweet.author` — author info
- `.tweet.likes`, `.tweet.retweets`, `.tweet.views` — engagement

### Get direct media URL only

```bash
# Direct video: prefix URL with d.
curl -sL "https://d.fxtwitter.com/user/status/TWEET_ID" -o video.mp4

# Or append .mp4 to any fxtwitter URL
curl -sL "https://fxtwitter.com/user/status/TWEET_ID.mp4" -o video.mp4
```

### From a CLI agent

```bash
# Extract video URL from any tweet
VIDEO_URL=$(curl -s "https://api.fxtwitter.com/status/$TWEET_ID" | jq -r '.tweet.media.videos[0].url')
curl -L "$VIDEO_URL" -o tweet_video.mp4

# Extract all image URLs
curl -s "https://api.fxtwitter.com/status/$TWEET_ID" | jq -r '.tweet.media.photos[].url'
```

**Pros**: No auth, no rate limit issues for moderate use, returns actual download URLs.
**Cons**: Public tweets only. No reply fetching.

---

## 2. TweetSave MCP Server — Best for Claude/Agent Integration

MCP server that wraps FxTwitter API. Zero API keys required.

### Install for Claude Code

```bash
# Global
claude mcp add -s user tweetsave -- npx -y mcp-remote https://mcp.tweetsave.org/sse

# Project-only
claude mcp add tweetsave -- npx -y mcp-remote https://mcp.tweetsave.org/sse
```

### Claude Desktop / Cursor config

```json
{
  "mcpServers": {
    "tweetsave": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://mcp.tweetsave.org/sse"]
    }
  }
}
```

### Available tools

| Tool | Description |
|------|-------------|
| `tweetsave_get_tweet` | Fetch single tweet: text, media URLs, metrics |
| `tweetsave_get_thread` | Retrieve connected tweets in a thread |
| `tweetsave_to_blog` | Convert tweet to formatted blog post |
| `tweetsave_batch` | Process up to 10 tweets simultaneously |
| `tweetsave_extract_media` | Extract direct media URLs (photos/videos/all) |

### Parameters

```
tweetsave_get_tweet(url: "https://x.com/user/status/ID", response_format: "json")
tweetsave_extract_media(url: "https://x.com/user/status/ID", media_type: "videos")
```

---

## 3. yt-dlp — Video Download

### Install

```bash
brew install yt-dlp        # macOS
pip install -U yt-dlp       # pip
```

### Download Twitter/X video

```bash
# Basic download (best quality)
yt-dlp "https://x.com/user/status/TWEET_ID"

# List available formats
yt-dlp -F "https://x.com/user/status/TWEET_ID"

# Select best mp4
yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" "https://x.com/user/status/TWEET_ID"

# Download with metadata
yt-dlp --write-info-json --write-thumbnail "https://x.com/user/status/TWEET_ID"

# Just print the video URL without downloading
yt-dlp -g "https://x.com/user/status/TWEET_ID"

# Custom output template
yt-dlp -o "%(uploader)s_%(id)s.%(ext)s" "https://x.com/user/status/TWEET_ID"
```

### Authentication (for age-gated or login-required content)

```bash
# Use cookies from browser
yt-dlp --cookies-from-browser firefox "https://x.com/user/status/TWEET_ID"
yt-dlp --cookies-from-browser chrome "https://x.com/user/status/TWEET_ID"

# Use exported cookies file
yt-dlp --cookies cookies.txt "https://x.com/user/status/TWEET_ID"
```

### Batch download

```bash
# From a file of URLs
yt-dlp -a urls.txt

# All videos from a user's media tab
yt-dlp "https://x.com/username/media"
```

**Note**: yt-dlp handles both `twitter.com` and `x.com` URLs. The Twitter extractor supports guest tokens for public content and cookies for authenticated access.

---

## 4. gallery-dl — Images + Videos + Metadata

### Install

```bash
pip install -U gallery-dl
```

### Download from tweet

```bash
# Download all media from a tweet
gallery-dl "https://x.com/user/status/TWEET_ID"

# Get direct URLs only (no download)
gallery-dl -g "https://x.com/user/status/TWEET_ID"

# Output as JSON
gallery-dl --dump-json "https://x.com/user/status/TWEET_ID"
```

### Authentication (required for most operations)

```bash
# Use browser cookies (recommended)
gallery-dl --cookies-from-browser firefox "https://x.com/user/status/TWEET_ID"

# Username/password
gallery-dl -u "username" -p "password" "https://x.com/user/status/TWEET_ID"
```

### Config file (`~/.config/gallery-dl/config.json`)

```json
{
  "extractor": {
    "twitter": {
      "cookies-from-browser": ["firefox"],
      "text-tweets": true,
      "retweets": false,
      "replies": false,
      "filename": "{tweet_id}_{num}.{extension}"
    }
  }
}
```

### Download user's entire media

```bash
gallery-dl "https://x.com/username"
gallery-dl "https://x.com/username/likes"
gallery-dl "https://x.com/username/media"
```

### Get original quality images

Append `:orig` to Twitter image URLs:
```
https://pbs.twimg.com/media/XXXXX.jpg:orig
```

---

## 5. xurl / xurl-rs — Official X API CLI

`xurl` is the official X Developer Platform CLI tool. `xurl-rs` is a Rust port with agent-native features.

### Install xurl (original, Go)

```bash
brew install --cask xdevplatform/tap/xurl
# or
npm install -g @xdevplatform/xurl
# or
curl -fsSL https://raw.githubusercontent.com/xdevplatform/xurl/main/install.sh | bash
```

### Install xurl-rs (Rust port, recommended)

```bash
brew tap brettdavies/tap && brew install xurl-rs
# or
cargo install xurl-rs
```

### Authentication setup

```bash
# Register your X API app
xurl auth apps add myapp --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET

# OAuth2 (opens browser)
xurl auth oauth2

# Bearer token (app-only, no user context)
xurl auth app --bearer-token YOUR_BEARER_TOKEN
```

### Read tweets

```bash
# Fetch a specific post by ID (xurl-rs uses `xr`)
xr read 1234567890

# Search posts
xr search "topic" -n 20

# View user profile
xr user @handle

# Home timeline
xr timeline

# JSON output (agent-friendly)
xr --output json read 1234567890
xr --output jsonl search "query"
```

### Raw API calls for media

```bash
# Get tweet with media expansions
xurl "/2/tweets/TWEET_ID?tweet.fields=attachments,created_at&media.fields=type,url,variants,preview_image_url&expansions=attachments.media_keys"

# The video download URLs are in: includes.media[].variants[].url
```

**Limitation**: xurl reads tweets and metadata but does not download media files directly. Use the returned URLs with `curl` or `yt-dlp`.

---

## 6. X API v2 — Direct API Access

### Endpoint

```
GET https://api.x.com/2/tweets/{id}
```

### Query parameters for full media

```
tweet.fields=attachments,created_at,text,public_metrics
media.fields=type,duration_ms,height,width,url,preview_image_url,variants
expansions=attachments.media_keys
```

### curl example

```bash
curl -s "https://api.x.com/2/tweets/TWEET_ID?tweet.fields=attachments,created_at,text,public_metrics&media.fields=type,url,variants,preview_image_url&expansions=attachments.media_keys" \
  -H "Authorization: Bearer $TWITTER_BEARER_TOKEN" | jq .
```

### Response structure for video

```json
{
  "data": {
    "id": "...",
    "text": "...",
    "attachments": { "media_keys": ["..."] }
  },
  "includes": {
    "media": [{
      "type": "video",
      "media_key": "...",
      "variants": [
        { "url": "https://video.twimg.com/...", "content_type": "video/mp4", "bit_rate": 2176000 },
        { "url": "https://video.twimg.com/...", "content_type": "video/mp4", "bit_rate": 832000 },
        { "url": "https://video.twimg.com/...", "content_type": "application/x-mpegURL" }
      ],
      "preview_image_url": "https://pbs.twimg.com/..."
    }]
  }
}
```

### Extract highest-quality video URL

```bash
curl -s "https://api.x.com/2/tweets/$TWEET_ID?media.fields=variants&expansions=attachments.media_keys" \
  -H "Authorization: Bearer $TWITTER_BEARER_TOKEN" \
  | jq -r '.includes.media[0].variants | map(select(.content_type=="video/mp4")) | sort_by(.bit_rate) | last | .url'
```

### Auth requirements

- **Bearer Token** (app-only): Read public tweets. Get from X Developer Portal.
- **OAuth 2.0 User Token**: Required for `tweet.read` + `users.read` scopes.
- **Free tier**: 1,500 tweets/month read. Basic tier ($200/mo): 50,000 reads/month.

---

## 7. twscrape (Python) — GraphQL Scraper

### Install

```bash
pip install twscrape
```

### CLI usage

```bash
# Get tweet details
twscrape tweet_details TWEET_ID

# Search tweets
twscrape search "query" --limit=20

# Raw API response (includes media)
twscrape tweet_details TWEET_ID --raw
```

### Python API

```python
import asyncio
from twscrape import API, gather

async def main():
    api = API()

    # Add account (required)
    await api.pool.add_account("user", "pass", "email", "email_pass")
    await api.pool.login_all()

    # Or use cookies (more stable)
    # await api.pool.add_account("user", "pass", "email", "email_pass", cookies="ct0=xxx; auth_token=yyy")

    # Get tweet with media
    tweet = await api.tweet_details(TWEET_ID)
    print(tweet.rawContent)
    print(tweet.json())  # Full JSON with media URLs

asyncio.run(main())
```

### Account management

```bash
# Add accounts from file (username:password:email:email_password:_:cookies)
twscrape add_accounts ./accounts.txt username:password:email:email_password:_:cookies

# Login all
twscrape login_accounts
```

---

## 8. @the-convocation/twitter-scraper (TypeScript/Node)

### Install

```bash
bun add @the-convocation/twitter-scraper
```

### Usage

```typescript
import { Scraper } from '@the-convocation/twitter-scraper';

const scraper = new Scraper();

// Get tweet by ID
const tweet = await scraper.getTweet('1234567890');
console.log(tweet.text);       // Tweet text
console.log(tweet.photos);     // Array of image URLs
console.log(tweet.videos);     // Array of video objects with URLs

// With authentication (for protected content)
await scraper.login('username', 'password', 'email@example.com');

// Or use cookies (recommended - less ban risk)
import { Cookie } from 'tough-cookie';
const cookies = 'ct0=abc; auth_token=xyz'.split(';').map(c => Cookie.parse(c)).filter(Boolean);
await scraper.setCookies(cookies);

// Search
for await (const tweet of scraper.search('keyword', 100)) {
    console.log(tweet.text, tweet.photos, tweet.videos);
}

// User timeline
for await (const tweet of scraper.getTweets('username', 50)) {
    console.log(tweet.text);
}
```

---

## 9. ScrapeBadger MCP Server

Paid API but offers 17 tools for Twitter data.

### Install

```bash
pip install scrapebadger-mcp
```

### MCP config

```json
{
  "mcpServers": {
    "scrapebadger": {
      "command": "uvx",
      "args": ["scrapebadger-mcp"],
      "env": {
        "SCRAPEBADGER_API_KEY": "sb_live_YOUR_KEY"
      }
    }
  }
}
```

### Tools

- `get_twitter_tweet` — Fetch single tweet by ID
- `get_twitter_user_tweets` — Recent tweets from a user
- `search_twitter_tweets` — Search with operators
- `get_twitter_user_profile` — User bio, followers

**Limitation**: Text/metadata only. No direct media file extraction.

---

## 10. Browser Automation — Playwright MCP + browser-use

For authenticated content or when other methods fail.

### Playwright MCP (for Claude/agents)

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest"]
    }
  }
}
```

This gives Claude tools to navigate, screenshot, and extract text from any web page including X.com. Uses accessibility tree snapshots (no vision model needed).

**Use case**: Navigate to `x.com/user/status/ID`, extract text via accessibility tree, take screenshot for visual content.

### browser-use (Python, AI agent browser automation)

```bash
uv init && uv add browser-use && uv sync
```

```python
from browser_use import Agent, Browser
import asyncio

async def extract_tweet():
    browser = Browser()
    agent = Agent(
        task="Go to https://x.com/user/status/TWEET_ID, extract the full tweet text, and list all media URLs visible on the page",
        llm=your_llm,
        browser=browser,
    )
    result = await agent.run()
    return result

asyncio.run(extract_tweet())
```

### Playwright direct (screenshot + download)

```typescript
import { chromium } from 'playwright';

const browser = await chromium.launch();
const context = await browser.newContext({
    storageState: 'twitter-auth.json'  // Pre-saved login cookies
});
const page = await context.newPage();

await page.goto('https://x.com/user/status/TWEET_ID');
await page.waitForSelector('article');

// Screenshot the tweet
await page.screenshot({ path: 'tweet.png', fullPage: false });

// Extract text
const tweetText = await page.evaluate(() => {
    const article = document.querySelector('article');
    return article?.innerText || '';
});

// Extract video source URL from network requests
page.on('response', async (response) => {
    if (response.url().includes('video.twimg.com') && response.url().includes('.mp4')) {
        console.log('Video URL:', response.url());
    }
});

await browser.close();
```

---

## 11. Nitter — Privacy Frontend (Self-Hosted)

Nitter provides a JS-free frontend to Twitter. Still works but now requires real account tokens for self-hosted instances.

```bash
# Scrape via a public Nitter instance (availability varies)
curl -s "https://nitter.net/user/status/TWEET_ID" | grep -oP 'src="(/pic/[^"]+)"'

# For video, Nitter serves direct video URLs in the page source
curl -s "https://nitter.net/user/status/TWEET_ID" | grep -oP 'data-url="([^"]+\.mp4)"'
```

**Status**: Public Nitter instances are unreliable. Self-hosting requires session tokens from real Twitter accounts.

---

## 12. snscrape (Python, archived but functional)

```bash
pip install snscrape

# User tweets as JSONL (includes media URLs)
snscrape --jsonl twitter-user username > tweets.jsonl

# Search
snscrape --jsonl --max-results 100 twitter-search "query" > results.jsonl

# Specific tweet by URL
snscrape --jsonl twitter-tweet TWEET_ID
```

**Note**: May require authentication due to Twitter API changes. Check for forks with updated auth support.

---

## Quick Reference: Method Selection

| Method | Auth Required | Video DL | Images | Text | Agent-Friendly | Cost |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|
| FxTwitter API | No | Yes (URL) | Yes | Yes | Best | Free |
| TweetSave MCP | No | Yes (URL) | Yes | Yes | Best | Free |
| yt-dlp | No (cookies optional) | Yes (file) | Thumbnails | Metadata | Good | Free |
| gallery-dl | Cookies | Yes (file) | Yes (file) | Metadata | Good | Free |
| xurl / xurl-rs | OAuth/Bearer | URLs only | URLs only | Yes | Good | Free* |
| X API v2 | Bearer/OAuth | URLs only | URLs only | Yes | Good | Free-$200/mo |
| twscrape | Account | In JSON | In JSON | Yes | Good | Free |
| twitter-scraper (TS) | Optional | Objects | Arrays | Yes | Good | Free |
| ScrapeBadger MCP | API Key | No | No | Yes | Best | Paid |
| Playwright MCP | Browser cookies | Screenshot | Screenshot | Yes | Good | Free |
| browser-use | Browser cookies | Via agent | Via agent | Yes | Good | Free |

*Free with X API developer account.

---

## Recommended Pipeline for Agent Content Extraction

```bash
# Step 1: Get tweet data (no auth)
TWEET_DATA=$(curl -s "https://api.fxtwitter.com/status/$TWEET_ID")
TWEET_TEXT=$(echo "$TWEET_DATA" | jq -r '.tweet.text')
VIDEO_URL=$(echo "$TWEET_DATA" | jq -r '.tweet.media.videos[0].url // empty')
IMAGE_URLS=$(echo "$TWEET_DATA" | jq -r '.tweet.media.photos[].url // empty')

# Step 2: Download video if present
if [ -n "$VIDEO_URL" ]; then
    yt-dlp -o "%(id)s.%(ext)s" "https://x.com/user/status/$TWEET_ID"
    # or: curl -L "$VIDEO_URL" -o video.mp4
fi

# Step 3: Download images
echo "$IMAGE_URLS" | while read url; do
    [ -n "$url" ] && curl -sL "${url}:orig" -O
done
```
