# Platform contract: Instagram Graph API facts the loop relies on

Read on 2026-11-16 from Meta's own pages. The tag is **HIGH** unless marked
otherwise. When a number here and Meta's docs disagree, the docs win; update this
file and `scripts/reel_loop.py` together.

## Publishing a Reel

Source:
https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/media.md
and https://developers.facebook.com/docs/instagram-platform/content-publishing

1. `POST /<IG_ID>/media` with `media_type=REELS`, `video_url` (public, Meta fetches
   it), `caption`, optional `share_to_feed`, `cover_url`, `thumb_offset`,
   `audio_name`, `collaborators` (≤3), `trial_params`, `is_ai_generated`.
2. Poll the container's `status_code` about once a minute, for at most 5 minutes,
   until `FINISHED`.
3. `POST /<IG_ID>/media_publish` with `creation_id=<container id>`.

**Caption:** "Maximum 2200 characters, 30 hashtags, and 20 @ tags."

**Reels spec:**

- Container: MOV or MP4, moov atom at the front, no edit lists.
- Video: H264 or HEVC, 23–60 fps, at most 1920 columns, 9:16 recommended, VBR at
  most 25 Mbps.
- Audio: AAC, 48 kHz max.
- Duration and size: 3 s to 15 min, at most 300 MB.

**Limits:**

- 400 containers per rolling 24 h.
- Published posts per 24 h: the guide says 100 in one place and 50 in another.
  **Plan for 50.**

**Account:** a professional account (Business or Creator). The two login paths:

- **Instagram Login:** `instagram_business_basic` and
  `instagram_business_content_publish`.
- **Facebook Login:** `instagram_basic`, `instagram_content_publish` and
  `pages_read_engagement`, through a Page token.

## Trial Reels

`trial_params` is optional. It was added in the 2025-12-03 changelog. With it,
`media_type` must be `REELS`. Its `graduation_strategy` is required and takes one of
two values:

- **`MANUAL`:** "the trial reel can be manually graduated in the native app".
- **`SS_PERFORMANCE`:** "the trial reel will be automatically graduated if the trial
  reel performs well".

The reference page documents no API endpoint that graduates a trial reel. It does
not say that none exists. Treat MANUAL as needing a person, in the app.

## AI disclosure

`is_ai_generated` is "a self-disclosure of AI usage in the post". Meta's help pages
ask creators to disclose photorealistic video and realistic-sounding audio, with an
AI voice-over as their example (MED: script-rendered pages, read as search snippets).
The gate sets the flag whenever the card declares synthetic media or
sets it true. It cannot detect media the card does not declare.

## Sending the approved bytes

A Reels container also accepts `upload_type=resumable`: "An optional parameter for
users want to upload video through the rupload protocol". The file is then sent
with `POST https://rupload.facebook.com/ig-api-upload/<version>/<IG_CONTAINER_ID>`,
using headers `offset` and `file_size` and the file as the body. `reel_loop.py
publish` uses only this mode and sends the same bytes it read and gated. A
`video_url` container would let Meta fetch whatever the URL serves later, so it
cannot be bound to an approval; the script does not offer it.

## Insights for our own Reels

Source: https://developers.facebook.com/docs/instagram-platform/reference/instagram-media/insights

- **Metrics:** `views`, `reach`, `likes`, `comments`, `saved`, `shares`, `reposts`,
  `total_interactions`, `ig_reels_avg_watch_time`, `ig_reels_video_view_total_time`,
  and `reels_skip_rate` (the share of views "skipped within the first 3 seconds").
- **Removed:**
  - `plays` and `impressions`: deprecated 2025-01-21, gone in all versions from
    2025-04-21; `views` replaces them.
  - `video_views`: gone.
- **Delay:** "Data may be delayed up to 48 hours." That is why `winners` holds back
  posts younger than 48 h.

## Other creators' Reels (Business Discovery)

Fields: `followers_count`, `media_count`, and per media `like_count`,
`comments_count` and `view_count`. `view_count` is "View count for Instagram Reels,
which includes both paid and organic metrics. Available for Business Discovery API
only" (added 2025-06-16).

Since the 2026-04-22 changelog, `view_count` from Business Discovery "returns
combined Instagram and Facebook views for crossposted video content". This
supersedes the 2025-12-03 note that it stays Instagram-only. As a result, a reel
crossposted to Facebook can look like an outlier against an account whose other
reels were not crossposted. When a ratio looks implausible, check whether the reel
was crossposted.

Limits:

- It only works on known usernames of professional accounts.
- `like_count` is missing when the owner hides likes.
- No shares, saves or insights.
- `media_url` is withheld for licensed audio, and since 2026-07-30 for reels with
  downloads turned off. Treat a withheld `media_url` as "do not download".

Documented for the Facebook Login path, with `instagram_basic`,
`instagram_manage_insights` and `pages_read_engagement`.

## Comment → DM (not used by this skill)

Source: https://developers.facebook.com/docs/instagram-platform/private-replies

- Send `POST /<IG_ID>/messages` with `recipient: {comment_id}`.
- The reply must go out within 7 days of the comment.
- Only one message per commenter. Follow-ups are allowed only after they reply, and
  only within 24 h.

## Scraping

Discovering reels by niche, reading personal accounts, or downloading other
creators' videos is not covered by the official API. Meta's terms forbid automated
collection without permission. Keep any collection away from the publishing
account, and prefer a hand-kept seed list read through Business Discovery.
