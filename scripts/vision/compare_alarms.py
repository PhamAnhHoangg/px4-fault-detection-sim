"""Which detector alarms first: telemetry (live_detector.py --csv) or vision (vision_detect.py --out)?
Both CSVs must use the same time axis (seconds of the same flight). The cut time is taken from the telemetry CSV
(fault_sec column) unless --cut is given.

  python compare_alarms.py out/live3.csv out/vision3.csv
"""
import argparse, csv


def first_alarm(path, cut):
    for r in csv.DictReader(open(path)):
        if str(r.get("alarm")).lower() in ("1", "true") and float(r["t"]) >= cut:
            return float(r["t"])
    return None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("telemetry"); ap.add_argument("vision"); ap.add_argument("--cut", type=float)
    a = ap.parse_args()
    cut = a.cut
    if cut is None:
        vals = [r.get("fault_sec") for r in csv.DictReader(open(a.telemetry))]
        cut = next((float(v) for v in vals if v not in (None, "", "nan")), None)
        if cut is None:
            raise SystemExit("no fault_sec in the telemetry CSV: give --cut")
    t, v = first_alarm(a.telemetry, cut), first_alarm(a.vision, cut)
    fmt = lambda x: "no alarm" if x is None else f"t = {x:.0f} s, {x - cut:.1f} s after the cut"
    print(f"cut at {cut:.1f} s\ntelemetry: {fmt(t)}\nvision:    {fmt(v)}")
    if t is not None and v is not None:
        print("first:", "telemetry" if t < v else "vision" if v < t else "same second", f"(gap {abs(t - v):.0f} s)")


if __name__ == "__main__":
    main()
