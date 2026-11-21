"""Read-only client for ABB Robot Web Services (RWS), standard library only. Only GET requests are ever sent.
Version 1 = IRC5 / RobotStudio RW6 (HTTP, digest auth, ?json=1). Version 2 = OmniCore / RW7 (HTTPS, basic auth, hal+json)."""
import base64, json, os, re, ssl, urllib.error, urllib.request
from urllib.parse import urlsplit

MAX_OUT = 4000
SEG_RE = re.compile(r"^[A-Za-z0-9_\-.:]{1,80}$")


class RwsError(Exception):
    pass


def check_path(path):
    """Only /rw/... and /ctrl/... paths, plain segments, no query string, no '..'."""
    if not isinstance(path, str) or not (path.startswith("/rw/") or path.startswith("/ctrl")) or len(path) > 300:
        raise RwsError("path must start with /rw/ or /ctrl")
    for seg in [s for s in path.split("/") if s]:
        if seg in ("..", ".") or not SEG_RE.match(seg):
            raise RwsError(f"invalid path segment: {seg!r}")
    return path


def check_segment(value, what):
    if not isinstance(value, str) or not SEG_RE.match(value) or value in ("..", "."):
        raise RwsError(f"invalid {what}: {value!r}")
    return value


class Rws:
    def __init__(self, base_url, version=1, verify_tls=True, user=None, password=None):
        u = urlsplit(base_url)
        if u.scheme not in ("http", "https") or not u.hostname:
            raise RwsError("base_url must be http:// or https:// with a host")
        self.base = f"{u.scheme}://{u.netloc}"
        self.version = int(version)
        self.user = user or os.environ.get("RWS_USER", "Default User")
        self.password = password or os.environ.get("RWS_PASSWORD", "robotics")
        ctx = None
        if u.scheme == "https" and not verify_tls:
            ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        handlers = [urllib.request.HTTPCookieProcessor()]
        if ctx:
            handlers.append(urllib.request.HTTPSHandler(context=ctx))
        if self.version == 1:
            pm = urllib.request.HTTPPasswordMgrWithDefaultRealm()
            pm.add_password(None, self.base, self.user, self.password)
            handlers.append(urllib.request.HTTPDigestAuthHandler(pm))
        self.opener = urllib.request.build_opener(*handlers)

    def get(self, path, timeout=10):
        check_path(path)
        url = self.base + path + ("?json=1" if self.version == 1 else "")
        req = urllib.request.Request(url, method="GET")
        if self.version == 2:
            tok = base64.b64encode(f"{self.user}:{self.password}".encode()).decode()
            req.add_header("Authorization", "Basic " + tok)
            req.add_header("Accept", "application/hal+json;v=2.0")
        try:
            with self.opener.open(req, timeout=timeout) as r:
                body = r.read(MAX_OUT * 4).decode(errors="replace")
                status = r.status
        except urllib.error.HTTPError as e:
            return e.code, e.read(500).decode(errors="replace")
        except (urllib.error.URLError, OSError) as e:
            raise RwsError(f"cannot reach {self.base}: {getattr(e, 'reason', e)}")
        try:
            body = json.dumps(json.loads(body))
        except ValueError:
            pass
        return status, body[:MAX_OUT] + (f"\n[cut at {MAX_OUT} characters]" if len(body) > MAX_OUT else "")
