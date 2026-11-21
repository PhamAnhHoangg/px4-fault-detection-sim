"""Live dashboard for the fault detector: a small web server (standard library only) that streams the per-second
rows to a browser page with live charts. Used two ways:

  1. inside live_detector.py:   --serve 8000          (then open http://localhost:8000)
  2. replay of a saved run:     python dashboard.py --replay results/sih/live_sih.csv    (no simulator needed)

The page shows the alarm state, the fault probability and three flight signals, with a hover read-out and a table view.
It listens on 127.0.0.1 only unless you pass --host 0.0.0.0."""
import argparse, json, math, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HTML = Path(__file__).with_name("dashboard.html")
FIELDS = ["t", "prob", "alarm", "alt_error", "hud_altitude", "vel_lin_z", "xtrack_error", "roll_gap", "pitch_gap", "yaw_gap"]


def clean(v):
    if isinstance(v, bool) or v is None:
        return v
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


class Hub:
    """Keeps the history and wakes the browser connections when something new arrives."""
    def __init__(self, threshold=0.5, mode="live", title="UAV fault detector"):
        self.rows, self.cut_t, self.gen = [], None, 0
        self.meta = {"threshold": threshold, "mode": mode, "title": title}
        self.cond = threading.Condition()

    def push_row(self, row):
        r = {k: clean(row.get(k)) for k in FIELDS}
        r["alarm"] = bool(row.get("alarm"))
        with self.cond:
            self.rows.append(r); self.cond.notify_all()

    def push_cut(self, t):
        with self.cond:
            self.cut_t = float(t); self.cond.notify_all()

    def reset(self):
        with self.cond:
            self.rows, self.cut_t = [], None; self.gen += 1; self.cond.notify_all()


def make_handler(hub):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, code, body, ctype):
            self.send_response(code); self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store"); self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                self._send(200, HTML.read_bytes(), "text/html; charset=utf-8")
            elif path == "/state.json":
                with hub.cond:
                    body = json.dumps({"meta": hub.meta, "cut_t": hub.cut_t, "rows": hub.rows}).encode()
                self._send(200, body, "application/json")
            elif path == "/events":
                self._events()
            else:
                self._send(404, b"not found", "text/plain")

        def _events(self):
            self.send_response(200); self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store"); self.send_header("Connection", "keep-alive"); self.end_headers()

            def ev(name, data):
                self.wfile.write(f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()); self.wfile.flush()
            try:
                sent, gen, cut_sent = 0, -1, None
                last_beat = time.time()
                while True:
                    with hub.cond:
                        if gen == hub.gen and sent >= len(hub.rows) and cut_sent == hub.cut_t:
                            hub.cond.wait(timeout=5)
                        g, rows, cut = hub.gen, list(hub.rows), hub.cut_t
                    if g != gen:
                        ev("reset", hub.meta); gen, sent, cut_sent = g, 0, None
                    for r in rows[sent:]:
                        ev("row", r)
                    sent = len(rows)
                    if cut != cut_sent:
                        if cut is not None:
                            ev("cut", {"t": cut})
                        cut_sent = cut
                    if time.time() - last_beat > 10:
                        self.wfile.write(b": keep-alive\n\n"); self.wfile.flush(); last_beat = time.time()
            except (BrokenPipeError, ConnectionResetError, OSError):
                return
    return H


def serve(hub, port=8000, host="127.0.0.1", tries=20):
    """Start the page server. If the port is taken, try the next ones (port 0 = any free port)."""
    for p in ([port] if port == 0 else range(port, port + tries)):
        try:
            srv = ThreadingHTTPServer((host, p), make_handler(hub))
            break
        except OSError:
            continue
    else:
        raise OSError(f"ports {port} to {port + tries - 1} are all in use")
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def open_tab(url):
    """Open the page in a browser tab. In WSL this opens the Windows browser."""
    import os, shutil, subprocess, webbrowser
    try:
        if "microsoft" in open("/proc/version").read().lower():
            # full paths too: some WSL setups do not put Windows programs on PATH
            for cmd in (["wslview", url], ["explorer.exe", url], ["/mnt/c/Windows/explorer.exe", url],
                        ["cmd.exe", "/c", "start", "", url], ["/mnt/c/Windows/System32/cmd.exe", "/c", "start", "", url]):
                if shutil.which(cmd[0]) or os.path.isfile(cmd[0]):
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd="/")
                    return True
    except OSError:
        pass
    try:
        return webbrowser.open_new_tab(url)
    except Exception:
        return False


def replay(hub, csv_path, speed=1.0, loop=False):
    import csv
    rows = list(csv.DictReader(open(csv_path)))
    while True:
        hub.reset(); cut = None
        for r in rows:
            fs = clean(r.get("fault_sec"))
            if fs is not None and cut is None and (clean(r.get("t")) or 0) + 1 > fs:
                cut = fs; hub.push_cut(fs)
            r["alarm"] = str(r.get("alarm")).lower() == "true"
            hub.push_row(r); time.sleep(1.0 / speed)
        if not loop:
            return
        time.sleep(3)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--replay", required=True, help="CSV written by live_detector.py --csv")
    ap.add_argument("--port", type=int, default=8000); ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--speed", type=float, default=1.0, help="1 = real time, 4 = four times faster")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--no-open", action="store_true", help="do not open a browser tab")
    a = ap.parse_args()
    hub = Hub(mode="replay", title="UAV fault detector: replay of " + Path(a.replay).name)
    srv = serve(hub, a.port, a.host)
    url = f"http://localhost:{srv.server_address[1]}"
    print(f"dashboard: {url}  (Ctrl+C to stop)", flush=True)
    if not a.no_open:
        open_tab(url)
    try:
        replay(hub, a.replay, a.speed, a.loop)
        print("replay finished; the page keeps the last state. Ctrl+C to stop.", flush=True)
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
