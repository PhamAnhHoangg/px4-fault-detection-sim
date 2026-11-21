"""End-to-end check of the vision chain on a made-up flight (no simulator): 10 frames per second, steady loiter with a
small bank and wobble, then after the cut the nose goes down slowly (horizon rises in the image).
Writes frames, runs horizon.py and vision_detect.py on them. This shows the code works; it says nothing about real flights."""
import math, subprocess, sys, tempfile
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from synth import make_frame

CUT, END = 55.0, 75.0
d = Path(tempfile.mkdtemp()) / "frames"; d.mkdir()
rng = np.random.default_rng(1)
for i in range(int(30 * 10), int(END * 10)):
    t = i / 10
    pitch_drop = 0 if t < CUT else min(0.25, 0.012 * (t - CUT) ** 1.5)    # horizon rises after the cut
    y = 0.5 + 0.01 * math.sin(t) + rng.normal(0, 0.004) - pitch_drop
    roll = 12 + 2 * math.sin(0.7 * t) + rng.normal(0, 0.5)
    cv2.imwrite(str(d / f"{int(t * 1000)}.png"), make_frame(roll, y, seed=i))
h = d.parent / "horizon.csv"
subprocess.run([sys.executable, str(Path(__file__).parent / "horizon.py"), str(d), "--csv", str(h)], check=True)
subprocess.run([sys.executable, str(Path(__file__).parent / "vision_detect.py"), str(h), "--baseline-from", "30",
                "--baseline-to", "45", "--cut", str(CUT)], check=True)
