"""Core of the screen-recorder MCP: window lookup, ffmpeg command lines and recording control.
No MCP code in here, so it can be tested without the MCP package.

Windows is the main target (ffmpeg gdigrab). Linux (x11grab) works for full screen and regions, which is how the
tests run. Nothing here has been run against a real Windows desktop yet: see README.md."""
import atexit, os, re, shutil, subprocess, sys, threading, time
from dataclasses import dataclass
from pathlib import Path

IS_WIN = sys.platform == "win32"
OUT_DIR = Path(os.environ.get("SCREEN_RECORDER_DIR") or (Path.home() / "Videos" / "claude-recordings"))
MAX_SECONDS_LIMIT = 3600


class RecorderError(Exception):
    pass


@dataclass
class Rect:
    x: int
    y: int
    w: int
    h: int

    def even(self):  # libx264 with yuv420p needs even sizes
        return Rect(self.x, self.y, self.w - self.w % 2, self.h - self.h % 2)


def find_ffmpeg():
    path = os.environ.get("FFMPEG_PATH") or shutil.which("ffmpeg")
    if not path:
        raise RecorderError("ffmpeg not found. Install it (Windows: winget install Gyan.FFmpeg) and restart Claude Desktop, "
                            "or set FFMPEG_PATH to ffmpeg.exe.")
    return path


def safe_name(name):
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", (name or "").strip()).strip("_")[:60]
    return name or time.strftime("rec-%Y%m%d-%H%M%S")


def parse_target(target):
    """'screen' | 'window:<part of the title>' | 'region:x,y,w,h'  ->  (kind, value)"""
    t = (target or "screen").strip()
    if t.lower() == "screen":
        return "screen", None
    if t.lower().startswith("window:"):
        title = t[7:].strip()
        if not title:
            raise RecorderError("window: needs part of a window title, for example window:Gazebo")
        return "window", title
    if t.lower().startswith("region:"):
        try:
            x, y, w, h = (int(v) for v in t[7:].split(","))
        except ValueError:
            raise RecorderError("region must look like region:x,y,width,height, for example region:0,0,1280,720")
        if w < 16 or h < 16:
            raise RecorderError("region is too small")
        return "region", Rect(x, y, w, h)
    raise RecorderError("target must be 'screen', 'window:<title>' or 'region:x,y,w,h'")


# ---------- windows (Windows only) ----------
def list_windows():
    """Visible, non-minimised top-level windows with a title: [{title, x, y, w, h}]."""
    if not IS_WIN:
        raise RecorderError("listing windows is only implemented on Windows. Use target 'screen' or 'region:x,y,w,h' here.")
    import ctypes
    from ctypes import wintypes
    user32, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
    try:
        user32.SetProcessDPIAware()  # so coordinates are real pixels, the same ones gdigrab uses
    except Exception:
        pass
    out = []
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        r = wintypes.RECT()
        # frame bounds without the invisible resize border; fall back to the plain window rectangle
        if dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r)) != 0:
            user32.GetWindowRect(hwnd, ctypes.byref(r))
        w, h = r.right - r.left, r.bottom - r.top
        if w > 0 and h > 0:
            out.append({"title": buf.value, "x": r.left, "y": r.top, "w": w, "h": h})
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return out


def find_window(part):
    wins = [w for w in list_windows() if part.lower() in w["title"].lower()]
    if not wins:
        raise RecorderError(f"no visible window with '{part}' in its title. Call list_windows to see the titles.")
    wins.sort(key=lambda w: w["w"] * w["h"], reverse=True)
    return wins[0]


def resolve_rect(target):
    kind, val = parse_target(target)
    if kind == "screen":
        return None
    if kind == "region":
        return val.even()
    w = find_window(val)
    return Rect(w["x"], w["y"], w["w"], w["h"]).even()


# ---------- ffmpeg ----------
def build_input_args(rect, fps, platform=None):
    plat = platform or ("win32" if IS_WIN else "linux")
    if plat == "win32":
        a = ["-f", "gdigrab", "-framerate", str(fps), "-draw_mouse", "1"]
        if rect:
            a += ["-offset_x", str(rect.x), "-offset_y", str(rect.y), "-video_size", f"{rect.w}x{rect.h}"]
        return a + ["-i", "desktop"]
    disp = os.environ.get("DISPLAY", ":0")
    a = ["-f", "x11grab", "-framerate", str(fps), "-draw_mouse", "1"]
    if rect:
        return a + ["-video_size", f"{rect.w}x{rect.h}", "-i", f"{disp}+{rect.x},{rect.y}"]
    return a + ["-i", disp]


def build_record_cmd(ffmpeg, rect, fps, out, platform=None):
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"] + build_input_args(rect, fps, platform) + \
           ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", str(out)]


def build_shot_cmd(ffmpeg, rect, out, platform=None):
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"] + build_input_args(rect, 1, platform) + \
           ["-frames:v", "1", str(out)]


def screenshot(target="screen", name=None):
    ffmpeg = find_ffmpeg()
    rect = resolve_rect(target)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{safe_name(name) if name else time.strftime('shot-%Y%m%d-%H%M%S')}.png"
    r = subprocess.run(build_shot_cmd(ffmpeg, rect, out), capture_output=True, text=True, timeout=30)
    if r.returncode != 0 or not out.exists():
        raise RecorderError(f"screenshot failed: {r.stderr.strip()[-300:]}")
    return out


class Recording:
    def __init__(self, rec_id, path, proc, target, started, timer):
        self.id, self.path, self.proc, self.target, self.started, self.timer = rec_id, path, proc, target, started, timer


_recordings = {}
_lock = threading.Lock()


def start_recording(target="screen", fps=30, name=None, max_seconds=600):
    fps = int(fps)
    if not 1 <= fps <= 60:
        raise RecorderError("fps must be between 1 and 60")
    max_seconds = int(max_seconds)
    if not 1 <= max_seconds <= MAX_SECONDS_LIMIT:
        raise RecorderError(f"max_seconds must be between 1 and {MAX_SECONDS_LIMIT}")
    ffmpeg = find_ffmpeg()
    rect = resolve_rect(target)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_id = safe_name(name)
    path = OUT_DIR / f"{rec_id}.mp4"
    with _lock:
        if rec_id in _recordings:
            raise RecorderError(f"a recording called {rec_id} is already running")
        if path.exists():
            path = OUT_DIR / f"{rec_id}-{time.strftime('%H%M%S')}.mp4"
        proc = subprocess.Popen(build_record_cmd(ffmpeg, rect, fps, path), stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        time.sleep(0.8)  # ffmpeg exits at once if the capture could not start
        if proc.poll() is not None:
            err = proc.stderr.read().decode(errors="replace").strip()[-400:]
            raise RecorderError(f"ffmpeg stopped right away: {err}")
        timer = threading.Timer(max_seconds, lambda: stop_recording(rec_id, quiet=True))
        timer.daemon = True; timer.start()
        _recordings[rec_id] = Recording(rec_id, path, proc, target, time.time(), timer)
    return {"id": rec_id, "file": str(path), "target": target, "rect": None if rect is None else vars(rect),
            "fps": fps, "auto_stop_after_s": max_seconds}


def stop_recording(rec_id=None, quiet=False):
    with _lock:
        if rec_id is None:
            if len(_recordings) != 1:
                if quiet:
                    return None
                raise RecorderError(f"{len(_recordings)} recordings running: {list(_recordings)}. Give the id.")
            rec_id = next(iter(_recordings))
        rec = _recordings.pop(rec_id, None)
    if rec is None:
        if quiet:
            return None
        raise RecorderError(f"no running recording called {rec_id}")
    rec.timer.cancel()
    try:  # 'q' makes ffmpeg finish the mp4 properly
        rec.proc.stdin.write(b"q"); rec.proc.stdin.flush()
    except Exception:
        pass
    try:
        rec.proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        rec.proc.kill()
    for stream in (rec.proc.stdin, rec.proc.stderr):
        try:
            stream.close()
        except Exception:
            pass
    secs = time.time() - rec.started
    size = rec.path.stat().st_size if rec.path.exists() else 0
    return {"id": rec.id, "file": str(rec.path), "seconds": round(secs, 1), "size_mb": round(size / 1e6, 2),
            "ok": size > 0}


def status():
    return [{"id": r.id, "file": str(r.path), "target": r.target, "seconds": round(time.time() - r.started, 1)}
            for r in _recordings.values()]


def list_recordings():
    if not OUT_DIR.exists():
        return []
    files = sorted(OUT_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"file": str(f), "size_mb": round(f.stat().st_size / 1e6, 2)} for f in files[:30]]


@atexit.register
def _stop_all():
    for rid in list(_recordings):
        try:
            stop_recording(rid, quiet=True)
        except Exception:
            pass
