"""Make an animated GIF of the dashboard replaying a recorded flight, one frame per flight second.
Needs Google Chrome (headless), ffmpeg and websocket-client (pip install websocket-client). Not needed to run the project.

  python scripts/live/make_demo_gif.py results/gazebo/live_engine_demo.csv docs/demo_dashboard.gif [--fps 5] [--dark]
"""
import argparse, base64, csv, json, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
import websocket
sys.path.insert(0, str(Path(__file__).parent))
import dashboard


def render_dashboard(rows, outdir, title, width=900, height=1060, dark=False):
    """One PNG per row (flight second) of the dashboard as it looked at that second. Returns the file list."""
    hub = dashboard.Hub(mode="replay", title=title)
    srv = dashboard.serve(hub, 0)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    chrome = subprocess.Popen(["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", "--remote-debugging-port=9334",
                               "--remote-allow-origins=*", f"--window-size={width},{height}", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    files = []
    try:
        for _ in range(40):
            try:
                tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9334/json")); break
            except Exception:
                time.sleep(0.5)
        ws = websocket.create_connection(tabs[0]["webSocketDebuggerUrl"], timeout=30)
        n = [0]

        def call(method, **params):
            n[0] += 1
            ws.send(json.dumps({"id": n[0], "method": method, "params": params}))
            while True:
                m = json.loads(ws.recv())
                if m.get("id") == n[0]:
                    return m
        call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=False)
        if dark:
            call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark"}])
        call("Page.navigate", url=url); time.sleep(3)
        cut = None
        for i, r in enumerate(rows):
            r = dict(r)
            fs = dashboard.clean(r.get("fault_sec"))
            if fs is not None and cut is None and (dashboard.clean(r.get("t")) or 0) + 1 > fs:
                cut = fs; hub.push_cut(fs)
            r["alarm"] = str(r.get("alarm")).lower() == "true"
            hub.push_row(r); time.sleep(0.3)
            shot = call("Page.captureScreenshot", format="png")
            f = outdir / f"{i:04d}.png"; f.write_bytes(base64.b64decode(shot["result"]["data"])); files.append(f)
    finally:
        chrome.kill(); srv.shutdown()
    return files


def trim_after_touchdown(rows, keep=6):
    """The model never saw a plane sitting on the ground, so stop shortly after touchdown."""
    down = next((i for i, r in enumerate(rows) if (dashboard.clean(r.get("hud_altitude")) or 99) < 1.0), None)
    return rows if down is None else rows[:down + keep]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("csv"); ap.add_argument("gif")
    ap.add_argument("--fps", type=float, default=5); ap.add_argument("--width", type=int, default=900)
    ap.add_argument("--height", type=int, default=1060); ap.add_argument("--dark", action="store_true")
    ap.add_argument("--title", default=None)
    ap.add_argument("--keep-ground", action="store_true", help="keep the seconds after the plane is on the ground (by default the GIF stops 5 s after touchdown)")
    a = ap.parse_args()
    rows = list(csv.DictReader(open(a.csv)))
    if not a.keep_ground:
        rows = trim_after_touchdown(rows)
    tmp = Path(tempfile.mkdtemp())
    render_dashboard(rows, tmp, a.title or "UAV fault detector: replay of " + Path(a.csv).name, a.width, a.height, a.dark)
    last = len(rows) - 1
    for k in range(1, int(a.fps * 3)):            # hold the last frame for about 3 s
        (tmp / f"{last + k:04d}.png").write_bytes((tmp / f"{last:04d}.png").read_bytes())
    vf = f"fps={a.fps},scale={min(a.width, 720)}:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=64[p];[s1][p]paletteuse=dither=none"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(a.fps), "-i", str(tmp / "%04d.png"), "-vf", vf, a.gif], check=True)
    print(f"{len(rows)} frames -> {a.gif} ({Path(a.gif).stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
