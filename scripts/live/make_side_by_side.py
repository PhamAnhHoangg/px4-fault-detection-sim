"""Side-by-side demo: chase-camera frames from Gazebo (left) and the dashboard at the same flight second (right),
lined up with the simulation clock (boot_s column of the live detector CSV). Writes an MP4 and a GIF.
Needs Chrome, ffmpeg, opencv-python-headless and websocket-client. Not needed to run the project.

  python scripts/live/make_side_by_side.py out/chase_frames results/gazebo/live_chase.csv docs/demo_side_by_side
       [--from 15] [--fps 10]

Frames: from scripts/vision/record_frames.py --topic /chase_cam (names = simulation time in ms).
Assumption: PX4's clock in SITL follows the Gazebo clock, so frame names match boot_s. If the propeller does not
stop on screen when the dashboard shows the cut, this assumption is wrong for your setup; pass --shift seconds.
"""
import argparse, csv, subprocess, sys, tempfile
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, str(Path(__file__).parent))
import dashboard
from make_demo_gif import render_dashboard, trim_after_touchdown


def label(img, text):
    cv2.rectangle(img, (0, 0), (img.shape[1], 34), (30, 30, 30), -1)
    cv2.putText(img, text, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1, cv2.LINE_AA)
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("frames"); ap.add_argument("csv"); ap.add_argument("out", help="output path without extension")
    ap.add_argument("--from", dest="t_from", type=float, default=15); ap.add_argument("--fps", type=float, default=10)
    ap.add_argument("--shift", type=float, default=0.0, help="seconds to add to the camera clock if the two clocks differ")
    ap.add_argument("--height", type=int, default=540)
    a = ap.parse_args()
    rows = trim_after_touchdown(list(csv.DictReader(open(a.csv))))
    off = next(float(r["boot_s"]) - float(r["t"]) for r in rows if dashboard.clean(r.get("boot_s")) is not None)
    frames = sorted(Path(a.frames).glob("*.png"), key=lambda f: int(f.stem))
    if not frames:
        sys.exit("no frames in " + a.frames)
    ft = np.array([int(f.stem) / 1000 + a.shift - off for f in frames])     # flight time of each camera frame
    t_end = float(rows[-1]["t"]) + 1
    print(f"camera frames cover flight t {ft[0]:.1f} to {ft[-1]:.1f} s; CSV covers 0 to {t_end:.0f} s")
    tmp = Path(tempfile.mkdtemp())
    dash = render_dashboard(rows, tmp / "dash", "Live fault detector, Gazebo flight", 900, 1060)
    comp = tmp / "comp"; comp.mkdir()
    k = 0
    for t in np.arange(max(a.t_from, ft[0]), min(t_end, ft[-1]), 1 / a.fps):
        cam = cv2.imread(str(frames[int(np.abs(ft - t).argmin())]))
        d = cv2.imread(str(dash[min(int(t), len(dash) - 1)]))
        cam = cv2.resize(cam, (int(cam.shape[1] * a.height / cam.shape[0]), a.height))
        d = cv2.resize(d, (int(d.shape[1] * a.height / d.shape[0]), a.height))
        label(cam, f"Gazebo, chase camera   t = {t:4.1f} s")
        cv2.imwrite(str(comp / f"{k:05d}.png"), np.hstack([cam, d])); k += 1
    if k == 0:
        sys.exit("camera frames and CSV do not overlap in time: check --shift")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(a.fps), "-i", str(comp / "%05d.png"),
                    "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", a.out + ".mp4"], check=True)
    vf = "fps=8,scale=960:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96[p];[s1][p]paletteuse=dither=bayer"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(a.fps), "-i", str(comp / "%05d.png"), "-vf", vf, a.out + ".gif"], check=True)
    for ext in (".mp4", ".gif"):
        print(a.out + ext, Path(a.out + ext).stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
