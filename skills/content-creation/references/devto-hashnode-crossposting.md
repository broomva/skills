# Dev.to + Hashnode Cross-Posting

Cross-post broomva.tech blog articles to Dev.to and Hashnode with canonical URLs
to preserve SEO while reaching developer audiences on both platforms.

## Setup

### Dev.to

1. Go to https://dev.to/settings/extensions → generate an API key
2. Save it:
   ```bash
   echo "YOUR_DEVTO_API_KEY" > ~/.config/blog-post/devto-token
   ```

**API reference:** https://developers.forem.com/api/v1

### Hashnode

1. Go to https://hashnode.com/settings/developer → generate a Personal Access Token
2. Find your publication ID:
   - Go to your Hashnode blog dashboard → Settings → General
   - The publication ID is in the URL: `hashnode.com/{publication-id}/dashboard`
   - Or query: `curl -s -H "Authorization: YOUR_TOKEN" -X POST https://gql.hashnode.com -H "Content-Type: application/json" -d '{"query":"{ me { publications(first:5) { edges { node { id title } } } } }"}'`
3. Save both:
   ```bash
   echo "YOUR_HASHNODE_PAT" > ~/.config/blog-post/hashnode-token
   echo "YOUR_PUBLICATION_ID" > ~/.config/blog-post/hashnode-publication-id
   ```

**API reference:** https://apidocs.hashnode.com

## Usage

```bash
# Cross-post a content package
./publish.sh /broomva/posts/2026-03-20-slug --platform devblogs

# Dev.to only
./publish.sh /broomva/posts/2026-03-20-slug --platform devto

# Hashnode only
./publish.sh /broomva/posts/2026-03-20-slug --platform hashnode

# Everything (includes devto + hashnode)
./publish.sh /broomva/posts/2026-03-20-slug --platform all

# Check credential status
./publish.sh /broomva/posts/2026-03-20-slug --platform status
```

## How It Works

1. **Content source**: Reads `broomva-tech-post.mdx` from the content package (or falls back to the deployed file in `broomva.tech/apps/chat/content/writing/`)
2. **MDX → Markdown conversion**:
   - Strips YAML frontmatter
   - Converts relative image paths (`/images/...`) to absolute URLs (`https://broomva.tech/images/...`)
   - Converts `<video>` tags to markdown image links
3. **Canonical URLs**: Each platform gets the original URL set:
   - Dev.to: `canonical_url` field → `https://broomva.tech/writing/{slug}`
   - Hashnode: `originalArticleURL` field → `https://broomva.tech/writing/{slug}`
4. **Draft vs Published**:
   - Dev.to articles are created as **drafts** — review and publish manually
   - Hashnode articles are published immediately

## SEO Protection

Setting canonical URLs tells search engines the original content lives on broomva.tech:
- Google indexes broomva.tech as the canonical source
- Dev.to (DA 85+) and Hashnode (DA 70+) generate high-quality backlinks
- No duplicate content penalty — both platforms respect `rel="canonical"`

## Platform-Specific Notes

### Dev.to
- Max 4 tags per article (alphanumeric, lowercase)
- Supports full markdown + liquid tags (`{% embed %}`)
- Good for: tutorials, "how I built" posts, showcases
- Add a "Connect with us" CTA at the bottom

### Hashnode
- Supports custom domain publishing (blog.broomva.tech)
- Tags map to Hashnode topic slugs
- GraphQL API at `gql.hashnode.com`
- Good for: deep technical content, architecture posts

## Recommended Posts for Cross-Posting

High-value posts from broomva.tech (per BRO-154):

1. `how-to-create-a-blog-post-with-bstack` — Getting Started with bstack tutorial
2. `modern-control-stack` — Architecture overview of control systems + agent OS
3. `one-binary-to-rule-them-all` — Rust CLI deep-dive
4. `reliable-agentic-systems` — Agent reliability patterns
5. `replacing-openclaw-with-claude-code-channels` — Build log / "how I built"

## Ongoing Cadence

- Cross-post every new blog article within 48 hours of publishing on broomva.tech
- Engage with comments on both platforms
- Use `--platform devblogs` in the publish pipeline after `broomva-tech` deploys
