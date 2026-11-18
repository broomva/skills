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

## YouTube Shorts (platform mode)

Read from Google's pages on 2026-11-18; re-read them before relying on a number:
[videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert),
[resumable upload protocol](https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol),
[video resource](https://developers.google.com/youtube/v3/docs/videos#status),
[quota costs](https://developers.google.com/youtube/v3/determine_quota_cost),
[Shorts length](https://support.google.com/youtube/answer/15424877).

**Calls, in order.**
1. `GET /youtube/v3/channels?part=id&mine=true` must return exactly the requested
   `--channel-id`, so a token for another channel uploads nothing.
2. `POST https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status`
   with the metadata as JSON and `X-Upload-Content-Length` / `X-Upload-Content-Type`.
   Google returns the session URI in the `Location` header. The adapter accepts it
   only on `https://www.googleapis.com/upload/youtube/v3/videos`; any other host gets
   neither the bytes nor the token. No HTTP redirect is followed anywhere, because
   urllib would carry the `Authorization` header to the redirect target.
3. One `PUT` of the gated bytes to that session. `201 Created` returns the video
   resource. A `308 Resume Incomplete` or any failure is reported, never retried: a
   blind retry can create a second video.

**Quota.** `videos.insert` has its own bucket: "100 calls per day", "1 unit" each.
It no longer draws on the 10,000-unit default, which covers the other endpoints
(`channels.list` and `videos.list` cost 1 unit each).

**Visibility.** Google's page now says: "Videos uploaded from unverified API
projects are not restricted to private viewing mode." Uploads "might default to
private based on creator account settings". The adapter still defaults
`privacyStatus` to `private`; `public` is a field the approved card sets.

**Metadata limits, as Google states them.**
- `snippet.title`: at most 100 characters, no `<` or `>`.
- `snippet.description`: at most 5000 bytes.
- `snippet.tags`: at most 500 characters in total. The commas between tags count,
  and a tag with a space counts as if wrapped in quotes.
- `status.privacyStatus`: `private`, `public` or `unlisted`.
- `status.selfDeclaredMadeForKids`: the card must set it; it is never defaulted.
- `status.containsSyntheticMedia`: discloses realistic altered or synthetic
  content. It is true whenever the card declares synthetic media or `is_ai_generated`.

**Shorts.** Google's notice reads "YouTube Shorts up to three minutes in length",
with "a square or vertical aspect ratio". The adapter checks both on the probed bytes
(1-180 s, width <= height).

**Token.** An explicit `--credentials` file wins; otherwise `YT_ACCESS_TOKEN` is used when
set, then `YT_CREDENTIALS_FILE`. A file is refreshed. That file must be a regular file owned
by the current user, mode 0600 or stricter, with `client_id`, `client_secret` and
`refresh_token`. The refresh goes only to `https://oauth2.googleapis.com/token`, and a
different `token_uri` is refused. The access token, refresh token and client secret
never appear in output or errors. The file is opened once without following a
symlink, and its type, owner and mode are checked on that open descriptor.

**Scopes.** Publishing needs `https://www.googleapis.com/auth/youtube.upload` for the
upload and `https://www.googleapis.com/auth/youtube.readonly` for the channel check
(`channels.list mine=true`) and for `stats` (`videos.list`). A token with only
`youtube.upload` fails the channel check closed, with HTTP 403, and uploads nothing.

**Orientation.** The probe reports the displayed size: a 90 or 270 degree rotation
(display-matrix side data or the legacy `rotate` tag) swaps width and height, so a
landscape video stored as portrait is not taken for a Short.

## TikTok (documentation only)

**Unverified locally:** TikTok's Content Posting API and audit rules were not
confirmed from a primary source during this offline change. The operating rule is
therefore conservative: unaudited clients may post only privately, and the audit
is not designed for self-managed posting. This skill has no TikTok publisher. A
TikTok post is a human click (or the Higgsfield widget), never an automatic upload.

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

## Lead funnel (polling comments → one private reply)

Verified 2026-11-17 against Meta's [private reply guide](https://developers.facebook.com/documentation/instagram-platform/private-replies)
and [IG Comment reference](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-comment).

The funnel uses Facebook Login and `graph.facebook.com`, matching publish. The
comment reference documents `from` (the commenter's Instagram-scoped ID and
username) and `hidden`. Read `GET /<media-id>/comments?fields=id,text,timestamp,from,hidden`. Access requires the
app's approved comment permissions; the guide lists `instagram_basic`,
`instagram_manage_comments`, and `pages_read_engagement` for Facebook Login, with
additional ad permissions for some Business Manager roles. Confirm app permissions
and token suitability before the owner's first live test; Instagram Login's
`graph.instagram.com` path is not implemented here.

Send `POST /<IG_USER_ID>/messages` with JSON
`{"recipient":{"comment_id":"<id>"},"message":{"text":"<approved text>"}}`.
Meta restricts private replies to seven days after the comment and a single
initial message; subsequent messaging requires the recipient's response (and has
a 24-hour response window). The guide says one message can be sent to the
commenter, so this tool sends at most one reply per commenter per post (commenters
are recognised by a keyed hash of `from.id`). It replies only to comments younger
than 6.9 days, leaving margin for clock skew, and implements no follow-ups. It is for posts
and Reels, not Live broadcasts, which have a separate timing restriction.

Pagination uses only the returned `after` cursor on the fixed Graph host, never
`paging.next` URLs. Each invocation reads at most `--max-pages` (default 10,
maximum 100), with 100 comments requested per page. A truncated result is reported;
later polling starts from the first page, so high-volume posts may require a
larger bound. There is no webhook server or send retry loop. The first
unsuccessful send stops the run: an HTTP 4xx is a definite rejection (`failed`);
a timeout, network error, 5xx or a reply without a message id is `uncertain` and
needs a human to check Instagram before anything is sent again.

## Scraping

Discovering reels by niche, reading personal accounts, or downloading other
creators' videos is not covered by the official API. Meta's terms forbid automated
collection without permission. Keep any collection away from the publishing
account, and prefer a hand-kept seed list read through Business Discovery.
