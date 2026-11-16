# Post card: `runs/<date>/card-<n>.json`

One card per render. `reel_loop.py payload` reads it and prints the Graph API
container parameters only if every gate passes.

```json
{
  "account": "my-handle",
  "source": {"url": "https://www.instagram.com/p/XXXX/", "account": "ref-handle", "ratio": 11.4},
  "script": "runs/2026-11-16/script-1.md",
  "caption": "The line people see before ... more. #oneortwo",
  "synthetic": {"voice_clone": true, "generated_visuals": true, "generated_music": false},
  "voice_consent": {"speaker": "the person whose voice it is", "date": "2026-11-16", "ref": "consent/voice.md"},
  "trial": null,
  "share_to_feed": true,
  "cover_url": null,
  "approval": null
}
```

| Field | Rule enforced by `payload` |
|---|---|
| `approval` | Must hold `by`, `at` and `video_sha256` equal to the sha256 of the file passed with `--video`. Written only after a person says yes to that file. |
| `synthetic` | Any true value forces `is_ai_generated: true`, whatever the card says. |
| `voice_consent` | Required with `speaker` and `date` when `synthetic.voice_clone` is true. |
| `caption` | ≤ 2200 characters, ≤ 30 hashtags, ≤ 20 @ tags. |
| `trial` | `null` for a normal post, or `{"graduation_strategy": "SS_PERFORMANCE" \| "MANUAL"}`. |
| the video | H264 or HEVC, 23–60 fps, 3 s to 15 min, ≤ 300 MB. With no `ffprobe`, the check is reported as UNCHECKED, never as passed. |

`source` is the provenance record for the run note. It is never published.
