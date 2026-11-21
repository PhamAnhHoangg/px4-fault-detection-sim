"""Horizon detection for a forward-looking camera on a fixed-wing plane (OpenCV).

For each frame: split sky from ground (sky is brighter and bluer), find the sky/ground boundary in every column,
fit a straight line through it, and report
  roll_deg   tilt of the horizon in the image (positive = horizon turns clockwise, about the plane's roll to the left)
  horizon_y  height of the horizon at the image centre, 0 = top edge, 1 = bottom edge
             (nose down -> horizon moves UP in the image -> horizon_y gets smaller)
  quality    share of columns that agree with the fitted line (0 to 1); below about 0.6 the result is unreliable
If the frame is almost all sky or all ground, horizon_y is reported as -0.5 (all ground: nose far down) or 1.5 (all sky).

  python horizon.py frame.png                 # one image
  python horizon.py frames/ --csv horizon.csv # a folder of frames named <time_ms>.png
"""
import argparse, csv, math, sys
from pathlib import Path
import cv2
import numpy as np

SPLIT_MIN = 30      # minimum score gap between sky and ground (raw units); tune on real Gazebo frames
SKY_BLUE_MIN = 20   # blue minus red above this = sky, for one-class frames


def sky_mask(bgr):
    """True where the pixel looks like sky. Otsu threshold on a 'blue and bright' score, so no fixed colours are needed."""
    img = cv2.GaussianBlur(bgr, (5, 5), 0).astype(np.float32)
    b, g, r = img[..., 0], img[..., 1], img[..., 2]
    raw = 0.6 * b + 0.4 * (b + g + r) / 3 - 0.5 * r
    score = cv2.normalize(raw, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    _, m = cv2.threshold(score, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)) > 0
    # Otsu always splits in two. If the two parts are not clearly different, the frame is one class only:
    # decide sky or ground by colour (sky is bluer than red, ground is not).
    if m.all() or (~m).all() or raw[m].mean() - raw[~m].mean() < SPLIT_MIN:
        is_sky = float((b - r).mean()) > SKY_BLUE_MIN
        return np.full(m.shape, is_sky)
    return m


def detect(bgr):
    h, w = bgr.shape[:2]
    sky = sky_mask(bgr)
    frac = sky.mean()
    if frac < 0.03:
        return {"roll_deg": float("nan"), "horizon_y": -0.5, "quality": 0.0}
    if frac > 0.97:
        return {"roll_deg": float("nan"), "horizon_y": 1.5, "quality": 0.0}
    # Which side is sky: compare the top and bottom halves (works up to about 90 degrees of roll)
    sky_on_top = sky[: h // 2].mean() >= sky[h // 2:].mean()
    cols = np.arange(0, w, max(1, w // 160))
    xs, ys = [], []
    for x in cols:
        col = sky[:, x] if sky_on_top else sky[::-1, x]
        ground = np.flatnonzero(~col)
        if len(ground) and ground[0] > 0:            # first ground pixel below the sky part
            y = ground[0] if sky_on_top else h - 1 - ground[0]
            xs.append(x); ys.append(y)
    if len(xs) < 10:
        return {"roll_deg": float("nan"), "horizon_y": 0.5 if frac > 0.5 else -0.5, "quality": 0.0}
    xs, ys = np.array(xs, float), np.array(ys, float)
    best = None
    rng = np.random.default_rng(0)
    for _ in range(60):                                   # small RANSAC against clouds, trees and texture
        i, j = rng.choice(len(xs), 2, replace=False)
        if xs[i] == xs[j]:
            continue
        a = (ys[j] - ys[i]) / (xs[j] - xs[i]); c = ys[i] - a * xs[i]
        inl = np.abs(ys - (a * xs + c)) < max(3, 0.02 * h)
        if best is None or inl.sum() > best.sum():
            best = inl
    a, c = np.polyfit(xs[best], ys[best], 1)
    roll = math.degrees(math.atan(a))
    yc = (a * (w / 2) + c) / h
    return {"roll_deg": round(roll, 2), "horizon_y": round(float(yc), 4), "quality": round(float(best.mean()), 3)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path"); ap.add_argument("--csv")
    a = ap.parse_args()
    p = Path(a.path)
    if p.is_file():
        print(detect(cv2.imread(str(p))))
        return
    files = sorted(p.glob("*.png"), key=lambda f: int(f.stem) if f.stem.isdigit() else 0)
    if not files:
        sys.exit("no .png frames in " + str(p))
    rows = []
    for f in files:
        img = cv2.imread(str(f))
        if img is None:
            continue
        d = detect(img); d["t"] = int(f.stem) / 1000 if f.stem.isdigit() else len(rows)
        rows.append(d)
    out = open(a.csv, "w", newline="") if a.csv else sys.stdout
    wr = csv.DictWriter(out, fieldnames=["t", "roll_deg", "horizon_y", "quality"]); wr.writeheader(); wr.writerows(rows)
    if a.csv:
        print(f"{len(rows)} frames -> {a.csv}")


if __name__ == "__main__":
    main()
