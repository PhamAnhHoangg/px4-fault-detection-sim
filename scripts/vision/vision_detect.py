"""Vision alarm from horizon measurements (output of horizon.py --csv): per-second means of horizon height and tilt,
compared with a baseline taken from steady flight. Alarm when the horizon has moved more than DY (image heights) or
tilted more than DROLL degrees away from the baseline for K seconds in a row. Same K = 3 as the telemetry detector.

  python vision_detect.py horizon.csv --baseline-from 30 --baseline-to 45 [--cut 55] [--out vision_alarm.csv]

Times are whatever the frame names use (simulation seconds). --cut only adds the delay to the printout.
The thresholds are first guesses; they must be tuned on normal Gazebo flights so that normal loiter never alarms.
"""
import argparse, csv, math
import numpy as np

K, DY, DROLL, MIN_QUALITY = 3, 0.06, 15.0, 0.6


def per_second(rows):
    acc = {}
    for r in rows:
        y = float(r["horizon_y"]); q = float(r["quality"]); roll = float(r["roll_deg"]) if r["roll_deg"] not in ("", "nan") else math.nan
        s = int(float(r["t"]))
        a = acc.setdefault(s, {"y": [], "roll": []})
        if y in (-0.5, 1.5):            # all ground or all sky: an extreme attitude, keep it as an extreme height
            a["y"].append(y)
        elif q >= MIN_QUALITY:
            a["y"].append(y)
            if not math.isnan(roll):
                a["roll"].append(roll)
    return {s: (np.mean(v["y"]) if v["y"] else math.nan, np.mean(v["roll"]) if v["roll"] else math.nan) for s, v in sorted(acc.items())}


def run(rows, b0, b1):
    sec = per_second(rows)
    base = [v for s, v in sec.items() if b0 <= s < b1]
    by = float(np.nanmedian([v[0] for v in base])); br = float(np.nanmedian([v[1] for v in base]))
    out, streak = [], 0
    for s, (y, roll) in sec.items():
        raw = s >= b1 and ((not math.isnan(y) and abs(y - by) > DY) or (not math.isnan(roll) and abs(roll - br) > DROLL))
        streak = streak + 1 if raw else 0
        out.append({"t": s, "horizon_y": round(y, 4), "roll_deg": round(roll, 2), "raw": int(raw), "alarm": int(streak >= K)})
    return out, by, br


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv"); ap.add_argument("--baseline-from", type=float, required=True); ap.add_argument("--baseline-to", type=float, required=True)
    ap.add_argument("--cut", type=float); ap.add_argument("--out")
    a = ap.parse_args()
    rows = list(csv.DictReader(open(a.csv)))
    out, by, br = run(rows, a.baseline_from, a.baseline_to)
    print(f"baseline: horizon_y {by:.3f}, roll {br:.1f} deg")
    first = next((r["t"] for r in out if r["alarm"] and (a.cut is None or r["t"] >= a.cut)), None)
    before = sum(r["alarm"] for r in out if a.cut is not None and r["t"] < a.cut)
    print("first vision alarm:", first if first is not None else "none",
          f"(delay {first - a.cut:.1f} s after the cut)" if first is not None and a.cut is not None else "",
          f"; alarm seconds before the cut: {before}" if a.cut is not None else "")
    if a.out:
        w = csv.DictWriter(open(a.out, "w", newline=""), fieldnames=list(out[0])); w.writeheader(); w.writerows(out)


if __name__ == "__main__":
    main()
