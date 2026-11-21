"""Save camera frames from Gazebo to PNG files named <simulation time in ms>.png.
Run it with the SYSTEM python (the Gazebo Python bindings are installed there), not the venv:

  /usr/bin/python3 scripts/vision/record_frames.py --out out/frames_e1 --seconds 120 [--fps 10] [--topic /cessna_cam]

It needs no extra packages: PNG files are written with the standard library. Stop early with Ctrl+C.
Assumption (to be checked): in PX4 SITL with Gazebo, PX4's clock follows the simulation clock, so these names match
the boot_s column of live_detector.py --csv.
"""
import argparse, struct, sys, threading, time, zlib
from pathlib import Path


def write_png(path, width, height, rgb):
    raw = b"".join(b"\x00" + rgb[y * width * 3:(y + 1) * width * 3] for y in range(height))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 3)) + chunk(b"IEND", b""))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True); ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--fps", type=float, default=10); ap.add_argument("--topic", default="/cessna_cam")
    a = ap.parse_args()
    try:
        from gz.transport13 import Node
        from gz.msgs10.image_pb2 import Image
    except ImportError as e:
        sys.exit(f"Gazebo Python bindings missing ({e}); run with /usr/bin/python3")
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    state = {"last": -1.0, "n": 0, "skipped_format": 0}
    lock = threading.Lock()

    def on_image(msg):
        t = msg.header.stamp.sec + msg.header.stamp.nsec / 1e9
        with lock:
            if t - state["last"] < 1.0 / a.fps:
                return
            state["last"] = t
        if msg.pixel_format_type != 3 or len(msg.data) != msg.width * msg.height * 3:   # 3 = RGB_INT8
            state["skipped_format"] += 1
            return
        write_png(out / f"{int(round(t * 1000))}.png", msg.width, msg.height, msg.data)
        state["n"] += 1

    node = Node()
    if not node.subscribe(Image, a.topic, on_image):
        sys.exit(f"could not subscribe to {a.topic}")
    print(f"recording {a.topic} to {out} for {a.seconds:.0f} s (Ctrl+C to stop)", flush=True)
    end = time.time() + a.seconds
    try:
        while time.time() < end:
            time.sleep(1)
            if state["n"] == 0 and time.time() > end - a.seconds + 10:
                print("no frames after 10 s: is the camera model running? check: gz topic -l | grep cessna_cam", flush=True)
                end = time.time()
    except KeyboardInterrupt:
        pass
    print(f"saved {state['n']} frames" + (f", skipped {state['skipped_format']} in another pixel format" if state["skipped_format"] else ""))


if __name__ == "__main__":
    main()
