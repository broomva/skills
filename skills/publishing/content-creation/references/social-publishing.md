# Social Publishing — CLI Tools & MCP Servers

## X/Twitter

### xurl (Official CLI, recommended)

```bash
npm i -g @xdevplatform/xurl
xurl auth apps add broomva --client-id $X_CLIENT_ID --client-secret $X_CLIENT_SECRET
# Opens browser for OAuth 2.0 PKCE, tokens stored in ~/.xurl, auto-refresh
```

**Usage:**
```bash
xurl post "Hello world!"
xurl media upload photo.jpg              # returns MEDIA_ID
xurl post "With image" --media-id MEDIA_ID
xurl reply $TWEET_ID "Thread continues"
xurl search "from:broomva" -n 20        # read own timeline
```

**Scopes needed:** `tweet.read`, `tweet.write`, `users.read`, `media.write`, `offline.access`

### Twitter MCP Server (for Claude Code integration)

```bash
# taazkareem/twitter-mcp-server — most comprehensive
npx @smithery/cli install @taazkareem/twitter-mcp-server
```

Add to `~/.claude/settings.json` MCP config with env vars: `TWITTER_USERNAME`, `TWITTER_PASSWORD`, `TWITTER_EMAIL`.

### API Tiers
- Free: read-only, 1 req/24h
- Basic ($100/mo): 10K reads, posting enabled
- OpenTweet ($5.99/mo): single API key, no OAuth complexity

## LinkedIn

### LinkedIn MCP Server (official OAuth)

```bash
git clone https://github.com/lurenss/linkedin-mcp
cd linkedin-mcp && npm install && npm run build
```

Env vars: `CLIENT_ID`, `CLIENT_SECRET`, `ACCESS_TOKEN` (60-day lifespan with refresh).

**Setup:** Create app at linkedin.com/developers. Add "Share on LinkedIn" product. Request `w_member_social` + `profile` + `openid` scopes.

### Direct API (curl)

```bash
# Post text update
curl -X POST 'https://api.linkedin.com/v2/ugcPosts' \
  -H "Authorization: Bearer $LINKEDIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "author": "urn:li:person:YOUR_ID",
    "lifecycleState": "PUBLISHED",
    "specificContent": {
      "com.linkedin.ugc.ShareContent": {
        "shareCommentary": {"text": "Post content here"},
        "shareMediaCategory": "NONE"
      }
    },
    "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
  }'
```

### Scopes
- `w_member_social` — post, comment, like
- `profile` — read profile info
- `openid` — authentication
- `w_organization_social` — post as company page

## Instagram

### Instagram MCP Server

```bash
# jlbadano/ig-mcp — posting, insights, profile
git clone https://github.com/jlbadano/ig-mcp
# Set INSTAGRAM_ACCESS_TOKEN env var
```

**Requires:** Business or Creator IG account linked to a Facebook Page. Create app at developers.facebook.com.

### Direct API (two-step publish)

```bash
# Step 1: Create media container
curl -X POST "https://graph.facebook.com/v21.0/$IG_USER_ID/media" \
  -d "image_url=https://example.com/photo.jpg" \
  -d "caption=Hello from CLI!" \
  -d "access_token=$META_TOKEN"
# Returns: { "id": "CREATION_ID" }

# Step 2: Publish
curl -X POST "https://graph.facebook.com/v21.0/$IG_USER_ID/media_publish" \
  -d "creation_id=$CREATION_ID" \
  -d "access_token=$META_TOKEN"
```

**Carousel:** Create child containers first, then parent referencing them.

### Permissions
- `instagram_content_publish` — post photos, videos, carousels, reels
- `instagram_manage_comments` — read/write comments
- `instagram_manage_insights` — analytics
- **Limit:** 100 API-published posts per 24 hours

## Multi-Platform Options

### Ayrshare MCP (managed, 13+ platforms)

Covers X, Instagram, LinkedIn, Facebook, TikTok, YouTube, Pinterest, Reddit, Threads, Bluesky, Telegram, and more. Single API key.

```
MCP endpoint: https://www.ayrshare.com/docs/mcp
```

### Postiz (self-hosted, 30+ platforms)

Open-source, Apache 2.0. Full REST API for agent automation.

```bash
# One-click Railway deploy, or:
docker compose up
```

### tayler-id/social-media-mcp (X + LinkedIn + Mastodon)

Single MCP server with built-in AI content generation.

```bash
claude mcp add-json "social-media" '{"command":"node","args":["path/to/build/index.js"],"env":{...}}'
```

## Claude Code MCP Configuration

Add to `~/.claude/settings.json` under `mcpServers`:

```json
{
  "twitter": {
    "command": "npx",
    "args": ["-y", "@taazkareem/twitter-mcp-server"],
    "env": {
      "TWITTER_USERNAME": "...",
      "TWITTER_PASSWORD": "...",
      "TWITTER_EMAIL": "..."
    }
  },
  "linkedin": {
    "command": "node",
    "args": ["/path/to/linkedin-mcp/build/index.js"],
    "env": {
      "CLIENT_ID": "...",
      "CLIENT_SECRET": "...",
      "ACCESS_TOKEN": "..."
    }
  },
  "instagram": {
    "command": "python",
    "args": ["/path/to/ig-mcp/server.py"],
    "env": {
      "INSTAGRAM_ACCESS_TOKEN": "..."
    }
  }
}
```

## Publishing Checklist

- [ ] X thread posted via `xurl` or MCP (5-8 tweets with images)
- [ ] Instagram carousel published via ig-mcp or Graph API
- [ ] LinkedIn post published via linkedin-mcp or REST API
- [ ] Video clip attached to at least one platform post
- [ ] Cross-links between platforms and blog post
