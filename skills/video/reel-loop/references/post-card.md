# Post card: `runs/<date>/card-<n>.json`

One card per render. `platform` is optional and defaults to `"instagram"`, so
existing cards remain Instagram cards. `reel_loop.py payload` (dry run) and
`reel_loop.py publish` read the video once and run the same platform gate on those
bytes. An Instagram payload prints `{"container", "sha256", "file_size"}`; a
YouTube payload prints `{"platform", "insert_body", "sha256", "file_size"}`.
Only if every gate passes can `publish` send those exact bytes.

```json
{
  "account": "my-handle",
  "source": {"url": "https://www.instagram.com/p/XXXX/", "account": "ref-handle", "ratio": 11.4},
  "script": "runs/2026-11-16/script-1.md",
  "caption": "The line people see before ... more. #oneortwo",
  "synthetic": {"voice_clone": true, "generated_visuals": true, "generated_music": false},
  "voice_consent": {"speaker": "the person whose voice it is", "date": "2026-11-16", "ref": "../../consent/voice.md"},
  "trial": null,
  "share_to_feed": true,
  "cover_url": null,
  "approval": null
}
```

| Field | Rule enforced by the gate |
|---|---|
| `platform` | Optional: `"instagram"` (the default) or `"youtube"`. Any other value blocks. |
| the card | Must be a JSON object. The gating and published fields below must have the types shown; any wrong type blocks before any field is trusted. `null` on an optional field means absent (`share_to_feed: null` publishes as true). `account`, `source` and `script` are provenance, never published and not checked. |
| `approval` | `null`, or an object of non-empty strings `by`, `at` and `video_sha256`. `video_sha256` must equal the sha256 of the file passed with `--video`. A YouTube approval also requires `platform: "youtube"`, `channel_id` equal to publish's `--channel-id`, and the `privacy_status` and `made_for_kids` it approves, equal to the card's (so changing visibility or audience needs a new approval). An Instagram approval may name `platform: "instagram"` and `ig_user_id` equal to `--ig-user-id`, and never a `channel_id`; those two fields stay optional so existing approvals remain valid. This binds an approval to the bytes, platform and destination. Written only after a person says yes to that file; the gate cannot verify who wrote it. |
| `synthetic` | An object of true/false values. Any true value, or `is_ai_generated: true`, yields `is_ai_generated: true`. Media the card does not declare cannot be detected. |
| `voice_consent` | Required when `synthetic.voice_clone` is true. It needs a non-empty `speaker`, an ISO `date` not in the future, and a `ref` to a file that exists, resolved relative to the card's folder. |
| `caption` | ≤ 2200 characters, ≤ 30 hashtags, ≤ 20 @ tags. |
| `trial` | `null` for a normal post, or `{"graduation_strategy": "SS_PERFORMANCE" \| "MANUAL"}`. |
| the video | Read once; must exist, be a regular non-empty file and be ≤ 300 MB, always checked. H264 or HEVC, 23–60 fps and 3 s to 15 min are checked with `ffprobe`; without it they are reported as UNCHECKED, never as passed. Container layout, audio codec, bitrate and width are not checked. |

`source` is the provenance record for the run note. It is never published.

## YouTube card

Set `platform` to `"youtube"` and add this object. `title` is required (1–100
characters, without `<` or `>`). `description`, if present, is at most 5,000
UTF-8 bytes and also has no angle brackets. `tags` is an optional string list with
at most 500 characters in total; `category_id`, if present, is digits only.
`privacy_status` is `private`, `unlisted` or `public` and defaults to `private`.
`made_for_kids` is required and must be a JSON boolean. `contains_synthetic_media`
is optional, but is forced true when `synthetic` contains any true value or
`is_ai_generated` is true.

```json
{
  "platform": "youtube",
  "account": "my-handle",
  "script": "runs/2026-11-18/script-1.md",
  "synthetic": {"generated_visuals": true},
  "youtube": {
    "title": "The one decision that saved my workflow",
    "description": "A concise, accessible explanation.",
    "tags": ["workflow", "shorts"],
    "category_id": "27",
    "privacy_status": "private",
    "made_for_kids": false,
    "contains_synthetic_media": true
  },
  "approval": {
    "by": "owner",
    "at": "2026-11-18T09:00:00Z",
    "video_sha256": "SHA256_OF_EXACT_FINAL_MP4_BYTES",
    "platform": "youtube",
    "channel_id": "UC0123456789ABCDEFGHIJKL",
    "privacy_status": "private",
    "made_for_kids": false
  }
}
```

On probed bytes, a YouTube Short must be vertical or square and 1–180 seconds.
Without `ffprobe` these checks are reported as UNCHECKED; an `ffprobe` error
blocks. `publish` verifies the token belongs to `--channel-id`, opens a Google
resumable session, and sends the read-once bytes only to Google's validated upload
host. `--no-go-live` stops after Google accepts that session and sends no bytes.

## Lead funnel

Add a separate `funnel` object to the published post's card. Publish ignores this
object; its existing video approval is unchanged.

```json
{
  "account": "broomva.tech",
  "funnel": {
    "media_id": "NUMERIC_PUBLISHED_MEDIA_ID",
    "keyword": "WORKSPACE",
    "approval": {
      "by": "owner",
      "at": "2026-11-17T12:00:00Z",
      "template_sha256": "SHA256_OF_EXACT_TEMPLATE_FILE_BYTES",
      "binding_sha256": "SHA256_OF_MEDIA_KEYWORD_ACCOUNT_AND_TEMPLATE"
    }
  }
}
```

The approval covers four things together: which post (`media_id`), which keyword,
which account (`--ig-user-id`) and the exact template bytes. The owner reviews the
UTF-8 template file (including the playbook link), sets `media_id` and `keyword`,
then runs:

```sh
python3 scripts/reel_loop.py funnel card.json --template /path/to/act-one.txt --ig-user-id NUMERIC_IG_ID --print-binding
```

It reads no comments and sends nothing. It prints the four values and their
`template_sha256` and `binding_sha256`; after checking the four values, the owner
records both hashes with `by` and `at`. Changing the post, the keyword, the account
or even one newline of the template blocks the funnel until it is approved again.
The tool checks the fields and hashes, but cannot authenticate the approver. The
file is read once and sent as literal text; there is no substitution or interpolation.

Keyword is a single Unicode word. Matching is case insensitive with Unicode word
boundaries: `WORKSPACE!` matches; `workspaces`, `myworkspace`, and `workspace_1`
do not. The media and account IDs must be numeric. `account` is required: the
account's own comments are excluded by its IG user ID or by this handle (Meta's
`from.id` is an Instagram-scoped ID, which can differ from the account's user ID).
Comments with no author identity, and comments marked `hidden`, are skipped.
