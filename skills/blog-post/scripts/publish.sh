#!/usr/bin/env bash
# publish.sh — Publish a blog-post content package to configured platforms
# Usage: ./publish.sh /path/to/posts/YYYY-MM-DD-slug [--platform x|linkedin|instagram|broomva-tech|devto|hashnode|devblogs|all]
#
# Reads content files from the package directory and publishes to each
# platform using native CLI tools (xurl, curl, git). No third-party services.
#
# Dev.to + Hashnode cross-posting:
#   - Converts MDX → clean markdown (strips frontmatter, absolutizes image URLs)
#   - Sets canonical_url (Dev.to) / originalArticleURL (Hashnode) → broomva.tech
#   - Dev.to articles are created as drafts (set published: true when ready)
#   - Use --platform devblogs to publish to both Dev.to and Hashnode

set -euo pipefail

PACKAGE_DIR="${1:?Usage: publish.sh /path/to/posts/YYYY-MM-DD-slug [--platform x|all]}"
PLATFORM="${2:---platform}"
TARGET="${3:-all}"

# Handle --platform flag
if [ "$PLATFORM" = "--platform" ]; then
    PLATFORM="$TARGET"
else
    PLATFORM="all"
fi

CONFIG_DIR="$HOME/.config/blog-post"
mkdir -p "$CONFIG_DIR"

# ── Helpers ──────────────────────────────────────────────────────────────────

log()  { echo "  📤 $*"; }
ok()   { echo "  ✅ $*"; }
skip() { echo "  ⏭️  $*"; }
fail() { echo "  ❌ $*"; }

# ── Connector Checks ────────────────────────────────────────────────────────

check_x() {
    xurl whoami >/dev/null 2>&1
}

check_linkedin() {
    [ -f "$CONFIG_DIR/linkedin-token" ] && [ -f "$CONFIG_DIR/linkedin-urn" ]
}

check_instagram() {
    [ -f "$CONFIG_DIR/instagram-token" ] && [ -f "$CONFIG_DIR/instagram-user-id" ]
}

check_devto() {
    [ -f "$CONFIG_DIR/devto-token" ]
}

check_hashnode() {
    [ -f "$CONFIG_DIR/hashnode-token" ] && [ -f "$CONFIG_DIR/hashnode-publication-id" ]
}

# ── Status Report ────────────────────────────────────────────────────────────

status_report() {
    echo ""
    echo "📋 Platform Status:"
    check_x       && echo "  ✅ X (xurl)" || echo "  ❌ X — run: xurl auth oauth2"
    check_linkedin && echo "  ✅ LinkedIn"  || echo "  ❌ LinkedIn — see references/publishing-automation.md"
    check_instagram && echo "  ✅ Instagram" || echo "  ❌ Instagram — see references/publishing-automation.md"
    check_devto     && echo "  ✅ Dev.to"     || echo "  ❌ Dev.to — save API key to ~/.config/blog-post/devto-token"
    check_hashnode  && echo "  ✅ Hashnode"    || echo "  ❌ Hashnode — save PAT to ~/.config/blog-post/hashnode-token + publication ID"
    echo "  ✅ broomva.tech (git)"
    echo ""
}

# ── X Publishing ─────────────────────────────────────────────────────────────

publish_x_post() {
    if [ ! -f "$PACKAGE_DIR/x-post.md" ]; then skip "X post: no x-post.md"; return; fi
    if ! check_x; then skip "X post: not authenticated (run xurl auth oauth2)"; return; fi

    log "Publishing X post..."

    # Extract post text (between ## Post and ## lines, skip blanks)
    POST_TEXT=$(sed -n '/^## Post/,/^## /{/^## /d; /^$/d; p;}' "$PACKAGE_DIR/x-post.md" | head -5)

    if [ -z "$POST_TEXT" ]; then
        # Fallback: take first non-header, non-blank line
        POST_TEXT=$(grep -v '^#\|^$\|^-' "$PACKAGE_DIR/x-post.md" | head -1)
    fi

    # Check for image
    if [ -f "$PACKAGE_DIR/media/thumbnails/x-card.png" ]; then
        RESULT=$(xurl post "$POST_TEXT" --media "$PACKAGE_DIR/media/thumbnails/x-card.png" 2>&1)
    elif [ -f "$PACKAGE_DIR/media/png/hero-social-card-opt.png" ]; then
        RESULT=$(xurl post "$POST_TEXT" --media "$PACKAGE_DIR/media/png/hero-social-card-opt.png" 2>&1)
    else
        RESULT=$(xurl post "$POST_TEXT" 2>&1)
    fi

    TWEET_ID=$(echo "$RESULT" | jq -r '.data.id // empty' 2>/dev/null)
    if [ -n "$TWEET_ID" ]; then
        ok "X post published: https://x.com/i/status/$TWEET_ID"
    else
        fail "X post failed: $RESULT"
    fi
}

publish_x_thread() {
    if [ ! -f "$PACKAGE_DIR/x-thread.md" ]; then skip "X thread: no x-thread.md"; return; fi
    if ! check_x; then skip "X thread: not authenticated (run xurl auth oauth2)"; return; fi

    log "Publishing X thread..."

    PREV_ID=""
    TWEET_NUM=0
    FIRST_URL=""

    # Parse tweets from x-thread.md (split on ### N/N headers)
    while IFS= read -r tweet_text; do
        [ -z "$tweet_text" ] && continue
        TWEET_NUM=$((TWEET_NUM + 1))

        # Check for image reference in tweet
        IMAGE=""
        if echo "$tweet_text" | grep -q "📸"; then
            IMAGE_REF=$(echo "$tweet_text" | grep -o "📸.*" | sed 's/📸 Image: //;s/📸 //')
            tweet_text=$(echo "$tweet_text" | grep -v "📸")
        fi

        # Resolve image path
        if [ -n "${IMAGE_REF:-}" ]; then
            for candidate in \
                "$PACKAGE_DIR/media/png/$IMAGE_REF" \
                "$PACKAGE_DIR/media/$IMAGE_REF" \
                "$PACKAGE_DIR/$IMAGE_REF"; do
                if [ -f "$candidate" ]; then IMAGE="$candidate"; break; fi
            done
        fi

        # Clean whitespace
        tweet_text=$(echo "$tweet_text" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | tr -s ' ')

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

        PREV_ID=$(echo "$RESULT" | jq -r '.data.id // empty' 2>/dev/null)
        if [ -n "$PREV_ID" ]; then
            [ -z "$FIRST_URL" ] && FIRST_URL="https://x.com/i/status/$PREV_ID"
            echo "    Tweet $TWEET_NUM posted: $PREV_ID"
        else
            fail "Tweet $TWEET_NUM failed: $RESULT"
            return 1
        fi

        # Rate limit courtesy (avoid hitting X API limits)
        sleep 1
    done < <(awk '
        /^### [0-9]+\/[0-9]+/ {
            if (tweet != "") print tweet
            tweet = ""
            next
        }
        /^## Thread Strategy|^## Thread \(/ { next }
        /^# X Thread/ { next }
        /^- \*\*/ { next }
        { tweet = (tweet == "") ? $0 : tweet " " $0 }
        END { if (tweet != "") print tweet }
    ' "$PACKAGE_DIR/x-thread.md")

    if [ -n "$FIRST_URL" ]; then
        ok "X thread published ($TWEET_NUM tweets): $FIRST_URL"
    fi
}

# ── LinkedIn Publishing ──────────────────────────────────────────────────────

publish_linkedin() {
    if [ ! -f "$PACKAGE_DIR/linkedin-post.md" ]; then skip "LinkedIn: no linkedin-post.md"; return; fi
    if ! check_linkedin; then skip "LinkedIn: no credentials (see references/publishing-automation.md)"; return; fi

    log "Publishing LinkedIn post..."

    TOKEN=$(cat "$CONFIG_DIR/linkedin-token")
    URN=$(cat "$CONFIG_DIR/linkedin-urn")

    # Extract post body (between ## Post and ## Post Metadata)
    POST_BODY=$(sed -n '/^## Post$/,/^## Post Metadata$/{ /^## /d; p; }' "$PACKAGE_DIR/linkedin-post.md" | sed '/^$/{ N; /^\n$/d; }')

    RESULT=$(curl -s -w "\n%{http_code}" -X POST "https://api.linkedin.com/v2/posts" \
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
        }" 2>&1)

    HTTP_CODE=$(echo "$RESULT" | tail -1)
    BODY=$(echo "$RESULT" | sed '$d')

    if [ "$HTTP_CODE" = "201" ] || [ "$HTTP_CODE" = "200" ]; then
        POST_URN=$(echo "$BODY" | jq -r '.id // empty' 2>/dev/null)
        ok "LinkedIn post published${POST_URN:+ ($POST_URN)}"
    else
        fail "LinkedIn post failed (HTTP $HTTP_CODE): $BODY"
    fi
}

# ── Instagram Publishing ─────────────────────────────────────────────────────

publish_instagram() {
    if [ ! -f "$PACKAGE_DIR/instagram-post.md" ]; then skip "Instagram: no instagram-post.md"; return; fi
    if ! check_instagram; then skip "Instagram: no credentials (see references/publishing-automation.md)"; return; fi

    log "Publishing Instagram post..."

    IG_TOKEN=$(cat "$CONFIG_DIR/instagram-token")
    IG_USER=$(cat "$CONFIG_DIR/instagram-user-id")

    # Instagram requires publicly hosted image URLs
    # Check if hero is deployed to broomva.tech
    SLUG=$(basename "$PACKAGE_DIR" | sed 's/^[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}-//')
    IMAGE_URL="https://broomva.tech/images/writing/$SLUG/hero-social-card-opt.png"

    # Extract caption
    CAPTION=$(sed -n '/^## Caption$/,/^## /{ /^## /d; p; }' "$PACKAGE_DIR/instagram-post.md")

    CONTAINER=$(curl -s -X POST "https://graph.instagram.com/v19.0/$IG_USER/media" \
        -d "image_url=$IMAGE_URL" \
        -d "caption=$(echo "$CAPTION" | head -50 | jq -Rs .)" \
        -d "access_token=$IG_TOKEN" | jq -r '.id // empty')

    if [ -n "$CONTAINER" ]; then
        RESULT=$(curl -s -X POST "https://graph.instagram.com/v19.0/$IG_USER/media_publish" \
            -d "creation_id=$CONTAINER" \
            -d "access_token=$IG_TOKEN")
        ok "Instagram post published"
    else
        fail "Instagram post failed: could not create media container"
    fi
}

# ── Instagram Reel Publishing ─────────────────────────────────────────────────

publish_instagram_reel() {
    if ! check_instagram; then skip "Instagram Reel: no credentials"; return; fi

    log "Publishing Instagram Reel..."

    IG_TOKEN=$(cat "$CONFIG_DIR/instagram-token")
    IG_USER=$(cat "$CONFIG_DIR/instagram-user-id")

    SLUG=$(basename "$PACKAGE_DIR" | sed 's/^[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}-//')

    # Find reel video (check multiple locations)
    VIDEO_URL=""
    for candidate in \
        "https://broomva.tech/images/writing/$SLUG/reel-vertical.mp4" \
        "https://broomva.tech/videos/$SLUG/reel.mp4"; do
        HTTP=$(curl -s -o /dev/null -w "%{http_code}" "$candidate")
        if [ "$HTTP" = "200" ]; then
            VIDEO_URL="$candidate"
            break
        fi
    done

    if [ -z "$VIDEO_URL" ]; then
        skip "Instagram Reel: no publicly hosted video found"
        return
    fi

    # Extract reel caption from instagram-reel.md or instagram-post.md
    CAPTION=""
    if [ -f "$PACKAGE_DIR/instagram-reel.md" ]; then
        CAPTION=$(sed -n '/^## Caption\|^##.*CTA/,/^## /{ /^## /d; p; }' "$PACKAGE_DIR/instagram-reel.md" | head -30)
    fi
    if [ -z "$CAPTION" ] && [ -f "$PACKAGE_DIR/instagram-post.md" ]; then
        CAPTION=$(sed -n '/^## Caption$/,/^## /{ /^## /d; p; }' "$PACKAGE_DIR/instagram-post.md" | head -30)
    fi

    # Create REELS container
    CONTAINER=$(curl -s -X POST "https://graph.instagram.com/v19.0/$IG_USER/media" \
        --data-urlencode "media_type=REELS" \
        --data-urlencode "video_url=$VIDEO_URL" \
        --data-urlencode "caption=$CAPTION" \
        --data-urlencode "share_to_feed=true" \
        --data-urlencode "access_token=$IG_TOKEN" | jq -r '.id // empty')

    if [ -z "$CONTAINER" ]; then
        fail "Instagram Reel: container creation failed"
        return
    fi

    # Poll for FINISHED status
    for i in $(seq 1 30); do
        sleep 10
        STATUS=$(curl -s "https://graph.instagram.com/v19.0/$CONTAINER?fields=status_code&access_token=$IG_TOKEN" | jq -r '.status_code // empty')
        if [ "$STATUS" = "FINISHED" ]; then
            RESULT=$(curl -s -X POST "https://graph.instagram.com/v19.0/$IG_USER/media_publish" \
                -d "creation_id=$CONTAINER" -d "access_token=$IG_TOKEN")
            POST_ID=$(echo "$RESULT" | jq -r '.id // empty')
            if [ -n "$POST_ID" ]; then
                ok "Instagram Reel published: $POST_ID"
                return
            fi
        elif [ "$STATUS" = "ERROR" ]; then
            fail "Instagram Reel: video processing failed"
            return
        fi
    done
    fail "Instagram Reel: timed out waiting for video processing"
}

# ── MDX → Markdown Converter ─────────────────────────────────────────────────
# Converts broomva.tech MDX to platform-compatible markdown:
# - Strips YAML frontmatter
# - Converts relative image paths to absolute broomva.tech URLs
# - Converts <video> tags to linked images or removes them
# - Strips JSX/MDX-specific syntax

mdx_to_markdown() {
    local MDX_FILE="$1"
    local SLUG="$2"
    local BASE_URL="https://broomva.tech"

    # Strip frontmatter (everything between first --- and second ---)
    local BODY
    BODY=$(awk 'BEGIN{f=0} /^---$/{f++; next} f>=2{print}' "$MDX_FILE")

    # Convert relative image paths to absolute URLs
    # /images/writing/slug/file.png → https://broomva.tech/images/writing/slug/file.png
    BODY=$(echo "$BODY" | sed "s|](/images/|](${BASE_URL}/images/|g")
    BODY=$(echo "$BODY" | sed "s|](/audio/|](${BASE_URL}/audio/|g")
    BODY=$(echo "$BODY" | sed "s|src=\"/images/|src=\"${BASE_URL}/images/|g")

    # Convert <video> tags to markdown image links (platforms don't support <video>)
    # <video src="URL" ...> → ![Video](URL)
    BODY=$(echo "$BODY" | sed -E 's|<video[^>]*src="([^"]*)"[^>]*>(\s*</video>)?|![Video](\1)|g')

    # Remove any remaining self-closing HTML video tags
    BODY=$(echo "$BODY" | sed '/<\/video>/d')

    echo "$BODY"
}

# Extract frontmatter field value
frontmatter_field() {
    local FILE="$1"
    local FIELD="$2"
    sed -n "/^---$/,/^---$/{ s/^${FIELD}: *//p; }" "$FILE" | sed 's/^"//;s/"$//' | head -1
}

# Extract frontmatter tags as comma-separated list
frontmatter_tags() {
    local FILE="$1"
    awk '/^tags:/,/^[a-z]/' "$FILE" | grep '^ *- ' | sed 's/^ *- //' | paste -sd',' -
}

# ── Dev.to Publishing ────────────────────────────────────────────────────────

publish_devto() {
    # Find the MDX source: prefer package broomva-tech-post.mdx, fallback to deployed file
    local MDX_FILE=""
    local SLUG
    SLUG=$(basename "$PACKAGE_DIR" | sed 's/^[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}-//')

    if [ -f "$PACKAGE_DIR/broomva-tech-post.mdx" ]; then
        MDX_FILE="$PACKAGE_DIR/broomva-tech-post.mdx"
    elif [ -f "$HOME/broomva/broomva.tech/apps/chat/content/writing/$SLUG.mdx" ]; then
        MDX_FILE="$HOME/broomva/broomva.tech/apps/chat/content/writing/$SLUG.mdx"
    fi

    if [ -z "$MDX_FILE" ]; then skip "Dev.to: no MDX source found for $SLUG"; return; fi
    if ! check_devto; then skip "Dev.to: no API key (save to ~/.config/blog-post/devto-token)"; return; fi

    log "Publishing to Dev.to..."

    local DEVTO_TOKEN
    DEVTO_TOKEN=$(cat "$CONFIG_DIR/devto-token")

    local TITLE TAGS BODY CANONICAL_URL
    TITLE=$(frontmatter_field "$MDX_FILE" "title")
    TAGS=$(frontmatter_tags "$MDX_FILE")
    BODY=$(mdx_to_markdown "$MDX_FILE" "$SLUG")
    CANONICAL_URL="https://broomva.tech/writing/$SLUG"

    # Dev.to allows max 4 tags, each alphanumeric/lowercase
    local DEVTO_TAGS
    DEVTO_TAGS=$(echo "$TAGS" | tr ',' '\n' | sed 's/-//g' | head -4 | paste -sd',' -)

    # Build JSON payload
    local PAYLOAD
    PAYLOAD=$(jq -n \
        --arg title "$TITLE" \
        --arg body "$BODY" \
        --arg canonical "$CANONICAL_URL" \
        --arg tags "$DEVTO_TAGS" \
        '{
            article: {
                title: $title,
                body_markdown: $body,
                canonical_url: $canonical,
                published: false,
                tags: ($tags | split(","))
            }
        }')

    local RESULT HTTP_CODE
    RESULT=$(curl -s -w "\n%{http_code}" -X POST "https://dev.to/api/articles" \
        -H "Content-Type: application/json" \
        -H "api-key: $DEVTO_TOKEN" \
        -d "$PAYLOAD" 2>&1)

    HTTP_CODE=$(echo "$RESULT" | tail -1)
    local RESPONSE_BODY
    RESPONSE_BODY=$(echo "$RESULT" | sed '$d')

    if [ "$HTTP_CODE" = "201" ]; then
        local ARTICLE_URL
        ARTICLE_URL=$(echo "$RESPONSE_BODY" | jq -r '.url // empty' 2>/dev/null)
        local ARTICLE_ID
        ARTICLE_ID=$(echo "$RESPONSE_BODY" | jq -r '.id // empty' 2>/dev/null)
        ok "Dev.to: draft created${ARTICLE_URL:+ — $ARTICLE_URL} (id: $ARTICLE_ID)"
        ok "  → canonical_url: $CANONICAL_URL"
        ok "  → Set published: true on Dev.to when ready to go live"
    else
        fail "Dev.to: failed (HTTP $HTTP_CODE): $RESPONSE_BODY"
    fi
}

# ── Hashnode Publishing ──────────────────────────────────────────────────────

publish_hashnode() {
    local MDX_FILE=""
    local SLUG
    SLUG=$(basename "$PACKAGE_DIR" | sed 's/^[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}-//')

    if [ -f "$PACKAGE_DIR/broomva-tech-post.mdx" ]; then
        MDX_FILE="$PACKAGE_DIR/broomva-tech-post.mdx"
    elif [ -f "$HOME/broomva/broomva.tech/apps/chat/content/writing/$SLUG.mdx" ]; then
        MDX_FILE="$HOME/broomva/broomva.tech/apps/chat/content/writing/$SLUG.mdx"
    fi

    if [ -z "$MDX_FILE" ]; then skip "Hashnode: no MDX source found for $SLUG"; return; fi
    if ! check_hashnode; then skip "Hashnode: no credentials (save PAT + publication ID to ~/.config/blog-post/)"; return; fi

    log "Publishing to Hashnode..."

    local HASHNODE_TOKEN HASHNODE_PUB_ID
    HASHNODE_TOKEN=$(cat "$CONFIG_DIR/hashnode-token")
    HASHNODE_PUB_ID=$(cat "$CONFIG_DIR/hashnode-publication-id")

    local TITLE TAGS BODY CANONICAL_URL
    TITLE=$(frontmatter_field "$MDX_FILE" "title")
    TAGS=$(frontmatter_tags "$MDX_FILE")
    BODY=$(mdx_to_markdown "$MDX_FILE" "$SLUG")
    CANONICAL_URL="https://broomva.tech/writing/$SLUG"

    # Build tags array for Hashnode GraphQL (each tag needs a slug and name)
    local TAGS_JSON
    TAGS_JSON=$(echo "$TAGS" | tr ',' '\n' | head -5 | jq -R '{slug: ., name: .}' | jq -s '.')

    # Hashnode uses a GraphQL API
    local GQL_QUERY
    GQL_QUERY=$(cat <<'GQLEOF'
mutation PublishPost($input: PublishPostInput!) {
  publishPost(input: $input) {
    post {
      id
      url
      slug
      title
    }
  }
}
GQLEOF
)

    local GQL_VARIABLES
    GQL_VARIABLES=$(jq -n \
        --arg pubId "$HASHNODE_PUB_ID" \
        --arg title "$TITLE" \
        --arg body "$BODY" \
        --arg slug "$SLUG" \
        --arg canonical "$CANONICAL_URL" \
        --argjson tags "$TAGS_JSON" \
        '{
            input: {
                publicationId: $pubId,
                title: $title,
                contentMarkdown: $body,
                slug: $slug,
                originalArticleURL: $canonical,
                tags: $tags
            }
        }')

    local PAYLOAD
    PAYLOAD=$(jq -n \
        --arg query "$GQL_QUERY" \
        --argjson variables "$GQL_VARIABLES" \
        '{query: $query, variables: $variables}')

    local RESULT HTTP_CODE
    RESULT=$(curl -s -w "\n%{http_code}" -X POST "https://gql.hashnode.com" \
        -H "Content-Type: application/json" \
        -H "Authorization: $HASHNODE_TOKEN" \
        -d "$PAYLOAD" 2>&1)

    HTTP_CODE=$(echo "$RESULT" | tail -1)
    local RESPONSE_BODY
    RESPONSE_BODY=$(echo "$RESULT" | sed '$d')

    local POST_URL
    POST_URL=$(echo "$RESPONSE_BODY" | jq -r '.data.publishPost.post.url // empty' 2>/dev/null)
    local ERRORS
    ERRORS=$(echo "$RESPONSE_BODY" | jq -r '.errors[0].message // empty' 2>/dev/null)

    if [ -n "$POST_URL" ]; then
        ok "Hashnode: published — $POST_URL"
        ok "  → originalArticleURL: $CANONICAL_URL"
    elif [ -n "$ERRORS" ]; then
        fail "Hashnode: $ERRORS"
    else
        fail "Hashnode: failed (HTTP $HTTP_CODE): $RESPONSE_BODY"
    fi
}

# ── broomva.tech Publishing ──────────────────────────────────────────────────

publish_broomva_tech() {
    if [ ! -f "$PACKAGE_DIR/broomva-tech-post.mdx" ]; then skip "broomva.tech: no broomva-tech-post.mdx"; return; fi

    log "Publishing to broomva.tech..."

    SLUG=$(basename "$PACKAGE_DIR" | sed 's/^[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}-//')
    BROOMVA_TECH="$HOME/broomva/broomva.tech"

    if [ ! -d "$BROOMVA_TECH" ]; then
        fail "broomva.tech repo not found at $BROOMVA_TECH"
        return
    fi

    # Copy post
    cp "$PACKAGE_DIR/broomva-tech-post.mdx" "$BROOMVA_TECH/apps/chat/content/writing/$SLUG.mdx"

    # Copy images
    if [ -d "$PACKAGE_DIR/media/png" ] && [ "$(ls -A "$PACKAGE_DIR/media/png" 2>/dev/null)" ]; then
        mkdir -p "$BROOMVA_TECH/apps/chat/public/images/writing/$SLUG/"
        cp "$PACKAGE_DIR/media/png/"* "$BROOMVA_TECH/apps/chat/public/images/writing/$SLUG/"
    fi

    # Copy audio
    if [ -f "$PACKAGE_DIR/media/mp3/narration.mp3" ]; then
        mkdir -p "$BROOMVA_TECH/apps/chat/public/audio/writing/"
        cp "$PACKAGE_DIR/media/mp3/narration.mp3" "$BROOMVA_TECH/apps/chat/public/audio/writing/$SLUG.mp3"
    fi

    ok "broomva.tech: files copied to $BROOMVA_TECH (create PR manually or via agent)"
}

# ── Main ─────────────────────────────────────────────────────────────────────

if [ ! -d "$PACKAGE_DIR" ]; then
    echo "Error: Package directory not found: $PACKAGE_DIR"
    exit 1
fi

echo ""
echo "📦 Publishing content package: $(basename "$PACKAGE_DIR")"
status_report

case "$PLATFORM" in
    all)
        publish_broomva_tech
        publish_x_thread
        publish_x_post
        publish_linkedin
        publish_instagram
        publish_instagram_reel
        publish_devto
        publish_hashnode
        ;;
    x)
        publish_x_thread
        publish_x_post
        ;;
    x-post)
        publish_x_post
        ;;
    x-thread)
        publish_x_thread
        ;;
    linkedin)
        publish_linkedin
        ;;
    instagram)
        publish_instagram
        ;;
    instagram-reel)
        publish_instagram_reel
        ;;
    broomva-tech)
        publish_broomva_tech
        ;;
    devto)
        publish_devto
        ;;
    hashnode)
        publish_hashnode
        ;;
    devblogs)
        publish_devto
        publish_hashnode
        ;;
    status)
        # Just show status (already printed above)
        ;;
    *)
        echo "Unknown platform: $PLATFORM"
        echo "Options: all, x, x-post, x-thread, linkedin, instagram, broomva-tech, devto, hashnode, devblogs, status"
        exit 1
        ;;
esac

echo ""
echo "Done."
