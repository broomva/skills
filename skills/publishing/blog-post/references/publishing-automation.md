# Publishing Automation

## Overview

Distribution uses native CLI tools and REST APIs — no third-party services. Each platform connector is independent; the skill gracefully degrades when a connector is unavailable.

## X/Twitter via xurl

### Setup (one-time)
```bash
# 1. Register app (needs X Developer Portal credentials)
xurl auth apps add broomva --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET

# 2. Set as default
xurl auth default broomva

# 3. OAuth2 flow (opens browser)
xurl auth oauth2

# 4. Verify
xurl whoami
```

### Posting a Single Tweet
```bash
# Read the post content (first non-header, non-metadata line)
POST_TEXT=$(sed -n '/^## Post/,/^## /{ /^## /d; /^$/d; p; }' x-post.md | head -1)

# Post with optional image
if [ -f media/thumbnails/x-card.png ]; then
    xurl post "$POST_TEXT" --media media/thumbnails/x-card.png
else
    xurl post "$POST_TEXT"
fi
```

### Posting a Thread

Threads are reply chains. The first tweet is a standalone post; subsequent tweets reply to the previous one.

**Parsing x-thread.md**:
The file uses `### N/N` headers to delimit tweets. Lines starting with `📸 Image:` indicate media attachments.

```bash
#!/bin/bash
# publish-thread.sh — Parse x-thread.md and post as thread
THREAD_FILE="$1"
MEDIA_DIR="$(dirname "$THREAD_FILE")/media"
PREV_ID=""

# Extract tweets between ### headers
awk '/^### [0-9]+\/[0-9]+/{if(tweet)print tweet; tweet=""; next} {tweet=tweet" "$0} END{if(tweet)print tweet}' "$THREAD_FILE" | while IFS= read -r tweet_text; do
    # Clean up whitespace
    tweet_text=$(echo "$tweet_text" | sed 's/^ *//;s/ *$//' | tr -s ' ')

    # Check for image reference
    IMAGE=""
    if echo "$tweet_text" | grep -q "📸 Image:"; then
        IMAGE_REF=$(echo "$tweet_text" | grep -o "📸 Image: .*" | sed 's/📸 Image: //')
        # Remove image line from tweet text
        tweet_text=$(echo "$tweet_text" | grep -v "📸 Image:")
        # Resolve image path
        if [ -f "$MEDIA_DIR/png/$IMAGE_REF" ]; then
            IMAGE="$MEDIA_DIR/png/$IMAGE_REF"
        elif [ -f "$IMAGE_REF" ]; then
            IMAGE="$IMAGE_REF"
        fi
    fi

    # Post or reply
    if [ -z "$PREV_ID" ]; then
        # First tweet
        if [ -n "$IMAGE" ]; then
            RESULT=$(xurl post "$tweet_text" --media "$IMAGE" 2>&1)
        else
            RESULT=$(xurl post "$tweet_text" 2>&1)
        fi
    else
        # Reply to previous
        if [ -n "$IMAGE" ]; then
            RESULT=$(xurl reply "$PREV_ID" "$tweet_text" --media "$IMAGE" 2>&1)
        else
            RESULT=$(xurl reply "$PREV_ID" "$tweet_text" 2>&1)
        fi
    fi

    # Extract tweet ID from response
    PREV_ID=$(echo "$RESULT" | jq -r '.data.id // empty' 2>/dev/null)
    if [ -z "$PREV_ID" ]; then
        echo "ERROR: Failed to post tweet. Response: $RESULT"
        exit 1
    fi
    echo "Posted tweet $PREV_ID"
done
```

### xurl Command Reference

| Command | Usage |
|---------|-------|
| `xurl post "text"` | Post a tweet |
| `xurl post "text" --media file.png` | Post with image |
| `xurl reply ID "text"` | Reply to a tweet |
| `xurl read ID` | Read a tweet |
| `xurl search "query" -n 20` | Search posts |
| `xurl whoami` | Check auth status |
| `xurl media upload file.mp4` | Upload media (video/image) |
| `xurl like ID` | Like a post |
| `xurl repost ID` | Repost/retweet |
| `xurl delete ID` | Delete a post |

## LinkedIn via REST API

### Setup (one-time)
1. Create app at [linkedin.com/developers](https://linkedin.com/developers)
2. Add product: "Share on LinkedIn" → grants `w_member_social` scope
3. OAuth2 flow:

```bash
# 1. Get authorization code (open in browser)
CLIENT_ID="your_client_id"
REDIRECT_URI="http://localhost:8080/callback"
open "https://www.linkedin.com/oauth/v2/authorization?response_type=code&client_id=$CLIENT_ID&redirect_uri=$REDIRECT_URI&scope=openid%20profile%20w_member_social"

# 2. Exchange code for token (after browser redirect)
CODE="paste_code_from_redirect_url"
CLIENT_SECRET="your_client_secret"
curl -s -X POST "https://www.linkedin.com/oauth/v2/accessToken" \
  -d "grant_type=authorization_code&code=$CODE&redirect_uri=$REDIRECT_URI&client_id=$CLIENT_ID&client_secret=$CLIENT_SECRET" \
  | jq -r '.access_token' > ~/.config/blog-post/linkedin-token

# 3. Get your member URN
curl -s -H "Authorization: Bearer $(cat ~/.config/blog-post/linkedin-token)" \
  "https://api.linkedin.com/v2/userinfo" \
  | jq -r '.sub' > ~/.config/blog-post/linkedin-urn
```

### Posting (Posts API v2 — current as of 2024+)

> **Note**: The `/v2/ugcPosts` endpoint was deprecated in 2024. Use `/v2/posts` instead.

```bash
TOKEN=$(cat ~/.config/blog-post/linkedin-token)
URN=$(cat ~/.config/blog-post/linkedin-urn)

# Extract post body (skip markdown headers and metadata sections)
POST_BODY=$(sed -n '/^## Post$/,/^## Post Metadata$/{ /^## /d; p; }' linkedin-post.md | sed '/^$/d')

curl -s -X POST "https://api.linkedin.com/v2/posts" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "LinkedIn-Version: 202401" \
  -H "X-Restli-Protocol-Version: 2.0.0" \
  -d "{
    \"author\": \"urn:li:person:$URN\",
    \"commentary\": $(echo "$POST_BODY" | jq -Rs .),
    \"visibility\": \"PUBLIC\",
    \"distribution\": {
      \"feedDistribution\": \"MAIN_FEED\",
      \"targetEntities\": [],
      \"thirdPartyDistributionChannels\": []
    },
    \"lifecycleState\": \"PUBLISHED\",
    \"isReshareDisabledByAuthor\": false
  }"
```

### Posting with Image
```bash
# 1. Initialize image upload
INIT_RESPONSE=$(curl -s -X POST "https://api.linkedin.com/v2/images?action=initializeUpload" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "LinkedIn-Version: 202401" \
  -d "{
    \"initializeUploadRequest\": {
      \"owner\": \"urn:li:person:$URN\"
    }
  }")

UPLOAD_URL=$(echo "$INIT_RESPONSE" | jq -r '.value.uploadUrl')
IMAGE_URN=$(echo "$INIT_RESPONSE" | jq -r '.value.image')

# 2. Upload image binary
curl -s -X PUT "$UPLOAD_URL" \
  -H "Authorization: Bearer $TOKEN" \
  --upload-file media/thumbnails/linkedin-card.png

# 3. Create post with image
curl -s -X POST "https://api.linkedin.com/v2/posts" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "LinkedIn-Version: 202401" \
  -H "X-Restli-Protocol-Version: 2.0.0" \
  -d "{
    \"author\": \"urn:li:person:$URN\",
    \"commentary\": $(echo "$POST_BODY" | jq -Rs .),
    \"visibility\": \"PUBLIC\",
    \"distribution\": {
      \"feedDistribution\": \"MAIN_FEED\",
      \"targetEntities\": [],
      \"thirdPartyDistributionChannels\": []
    },
    \"content\": {
      \"media\": {
        \"title\": \"Post image\",
        \"id\": \"$IMAGE_URN\"
      }
    },
    \"lifecycleState\": \"PUBLISHED\",
    \"isReshareDisabledByAuthor\": false
  }"
```

## Instagram via Instagram Business Login API

> **Note**: Uses the Instagram Graph API via `graph.instagram.com` (not the legacy Facebook Graph API approach).

### Setup (one-time)
1. Convert Instagram to Business/Creator account
2. Create Meta app at [developers.facebook.com](https://developers.facebook.com) → Business type
3. Add **"Manage messaging & content on Instagram"** use case
4. Add `instagram_business_content_publish` permission (Step 1 → Go to permissions and features)
5. Set up Instagram Business Login (Step 4) → add redirect URI: `https://broomva.tech/api/auth/callback`
6. Add Instagram accounts as **Instagram Testers** (App roles → Roles → Add People → Instagram Tester)
7. Accept tester invitations on Instagram (Settings → Apps and websites → Tester Invites)
8. Run OAuth flow:

```bash
# 1. Open authorization URL in browser
IG_APP_ID="your_instagram_app_id"
open "https://www.instagram.com/oauth/authorize?force_reauth=true&client_id=$IG_APP_ID&redirect_uri=https://broomva.tech/api/auth/callback&response_type=code&scope=instagram_business_basic%2Cinstagram_business_manage_messages%2Cinstagram_business_manage_comments%2Cinstagram_business_content_publish%2Cinstagram_business_manage_insights"

# 2. After authorization, extract code from redirect URL and exchange for short-lived token
CODE="paste_code_from_redirect_url"
IG_APP_SECRET="your_instagram_app_secret"
curl -s -X POST "https://api.instagram.com/oauth/access_token" \
  --data-urlencode "client_id=$IG_APP_ID" \
  --data-urlencode "client_secret=$IG_APP_SECRET" \
  --data-urlencode "grant_type=authorization_code" \
  --data-urlencode "redirect_uri=https://broomva.tech/api/auth/callback" \
  --data-urlencode "code=$CODE" | jq .
# Response includes: access_token, user_id, permissions

# 3. Exchange short-lived token for long-lived token (60 days)
SHORT_TOKEN="short_lived_token_from_step_2"
curl -s "https://graph.instagram.com/access_token?grant_type=ig_exchange_token&client_secret=$IG_APP_SECRET&access_token=$SHORT_TOKEN" \
  | jq -r '.access_token' > ~/.config/blog-post/instagram-token

# 4. Save user ID (from step 2 response)
echo -n "user_id_from_step_2" > ~/.config/blog-post/instagram-user-id

# 5. Verify
curl -s "https://graph.instagram.com/v19.0/me?fields=id,username,name,account_type&access_token=$(cat ~/.config/blog-post/instagram-token)" | jq .
```

### Posting (image must be publicly accessible URL)
```bash
IG_TOKEN=$(cat ~/.config/blog-post/instagram-token)
IG_USER=$(cat ~/.config/blog-post/instagram-user-id)
IMAGE_URL="https://broomva.tech/images/writing/{slug}/hero.png"
CAPTION=$(sed -n '/^## Caption$/,/^## /{ /^## /d; p; }' instagram-post.md)

# Create media container → publish (two-step process)
CONTAINER=$(curl -s -X POST "https://graph.instagram.com/v19.0/$IG_USER/media" \
  --data-urlencode "image_url=$IMAGE_URL" \
  --data-urlencode "caption=$CAPTION" \
  --data-urlencode "access_token=$IG_TOKEN" | jq -r '.id')

curl -s -X POST "https://graph.instagram.com/v19.0/$IG_USER/media_publish" \
  -d "creation_id=$CONTAINER" \
  -d "access_token=$IG_TOKEN"
```

### Token Refresh (before 60-day expiry)
```bash
# Refresh long-lived token (must be done before expiry, extends another 60 days)
curl -s "https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=$(cat ~/.config/blog-post/instagram-token)" \
  | jq -r '.access_token' > ~/.config/blog-post/instagram-token
```

## Connector Status Check

Before publishing, verify which platforms are available:

```bash
# X — check xurl auth
xurl whoami >/dev/null 2>&1 && echo "✅ X: ready" || echo "❌ X: run 'xurl auth oauth2'"

# LinkedIn — check token file
[ -f ~/.config/blog-post/linkedin-token ] && echo "✅ LinkedIn: ready" || echo "❌ LinkedIn: setup needed"

# Instagram — check token file
[ -f ~/.config/blog-post/instagram-token ] && echo "✅ Instagram: ready" || echo "❌ Instagram: setup needed"

# broomva.tech — always available
echo "✅ broomva.tech: ready (git)"
```

## Credential Security

- All tokens stored in `~/.config/blog-post/` — never in the repo
- Conversation bridge redacts `--client-secret`, `--client-id`, bearer tokens, and high-entropy strings
- Never log full API responses containing tokens
- LinkedIn tokens expire after 60 days — refresh via `curl` with refresh_token
- Instagram long-lived tokens last 60 days — renew before expiry
