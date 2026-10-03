"""Route urllib.request.urlopen to fake_anthropic. Anything else is refused, so a test cannot reach
the network even by mistake."""

import io
import json
import urllib.error
import urllib.request

import fake_anthropic

TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
PROFILE_URL = "https://api.anthropic.com/api/oauth/profile"
MESSAGES_URL = "https://api.anthropic.com/v1/messages"


class _Resp:
    def __init__(self, status, body, headers=None):
        self.status = status
        self._body = json.dumps(body).encode("utf-8")
        self.headers = headers or {}

    def read(self):
        return self._body

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _bearer(req):
    h = req.get_header("Authorization") or ""
    return h[len("Bearer "):] if h.startswith("Bearer ") else None


def fake_urlopen(req, data=None, timeout=None, **kw):
    if isinstance(req, str):
        req = urllib.request.Request(req, data=data)
    url = req.full_url.split("?", 1)[0]
    if url == TOKEN_URL:
        body = json.loads((req.data or b"{}").decode("utf-8"))
        if body.get("grant_type") != "refresh_token":
            status, payload = 400, {"error": "unsupported_grant_type"}
        else:
            status, payload = fake_anthropic.token_refresh(body.get("refresh_token"))
    elif url == USAGE_URL:
        status, payload = fake_anthropic.usage(_bearer(req))
    elif url == PROFILE_URL:
        status, payload = fake_anthropic.profile(_bearer(req))
    elif url == MESSAGES_URL:
        status, payload = fake_anthropic.messages(_bearer(req))
    else:
        raise urllib.error.URLError("fake net: blocked request to %s" % url)
    if status >= 400:
        raise urllib.error.HTTPError(url, status, "fake %d" % status, {}, io.BytesIO(json.dumps(payload).encode("utf-8")))
    return _Resp(status, payload)


def blocked_urlopen(req, *a, **kw):
    url = req if isinstance(req, str) else getattr(req, "full_url", repr(req))
    raise urllib.error.URLError("test guard: network is blocked (%s)" % url)


def install():
    urllib.request.urlopen = fake_urlopen
