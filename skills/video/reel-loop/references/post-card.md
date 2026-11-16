# Post card: `runs/<date>/card-<n>.json`

One card per render. `reel_loop.py payload` reads it. Only if every gate passes
does it print `{"container": <Graph API create-media params>, "upload": <the
approved file, its size and sha256> | null}`.

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

| Field | Rule enforced by `payload` |
|---|---|
| the card | Must be a JSON object with the field types shown. Any wrong type blocks before any field is trusted. |
| `approval` | `null`, or an object of non-empty strings `by`, `at` and `video_sha256`. `video_sha256` must equal the sha256 of the file passed with `--video`. Written only after a person says yes to that file; the gate cannot verify who wrote it. |
| `synthetic` | An object of true/false values. Any true value, or `is_ai_generated: true`, yields `is_ai_generated: true`. Media the card does not declare cannot be detected. |
| `voice_consent` | Required when `synthetic.voice_clone` is true. It needs a non-empty `speaker`, an ISO `date` not in the future, and a `ref` to a file that exists, resolved relative to the card's folder. |
| `caption` | ≤ 2200 characters, ≤ 30 hashtags, ≤ 20 @ tags. |
| `trial` | `null` for a normal post, or `{"graduation_strategy": "SS_PERFORMANCE" \| "MANUAL"}`. |
| the video | ≤ 300 MB, always checked. H264 or HEVC, 23–60 fps and 3 s to 15 min are checked with `ffprobe`; without it they are reported as UNCHECKED, never as passed. Container layout, audio codec, bitrate and width are not checked. |
| `--video-url` | Optional. Must be https, and is fetched now: it must serve bytes with the approved sha256. Without it, the output is a resumable upload of the local file. |

`source` is the provenance record for the run note. It is never published.
