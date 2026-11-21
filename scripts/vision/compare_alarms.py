"""Which detector alarms first after the cut: telemetry or vision?

  python compare_alarms.py out/live_cam1.csv out/horizon_cam1.csv [--baseline 0 15]

telemetry CSV: from live_detector.py --csv (columns t, alarm, fault_sec, boot_s)
horizon CSV:   from horizon.py frames/ --csv (column t = simulation seconds from the frame names)
boot_s lines the two clocks up. The vision baseline is taken from flight seconds 0 to 15 (steady loiter after the
settle time) unless --baseline is given. Prints both alarm times relative to the cut and writes nothing.
"""
import argparse, csv, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import vision_detect


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("telemetry"); ap.add_argument("horizon")
    ap.add_argument("--baseline", type=float, nargs=2, default=[0, 15]); ap.add_argument("--cut", type=float)
    a = ap.parse_args()
    tel = list(csv.DictReader(open(a.telemetry)))
    offs = [float(r["boot_s"]) - float(r["t"]) for r in tel if r.get("boot_s") not in (None, "", "nan")]
    if not offs:
        sys.exit("telemetry CSV has no boot_s column: record it with the current live_detector.py")
    off = offs[0]                                  # flight t = simulation seconds - off
    cut = a.cut
    if cut is None:
        cut = next((float(r["fault_sec"]) for r in tel if r.get("fault_sec") not in (None, "", "nan")), None)
        if cut is None:
            sys.exit("no fault_sec in the telemetry CSV: give --cut")
    hz = list(csv.DictReader(open(a.horizon)))
    for r in hz:
        r["t"] = float(r["t"]) - off
    vis, by, br = vision_detect.run(hz, *a.baseline)
    t_tel = next((float(r["t"]) for r in tel if str(r["alarm"]).lower() in ("1", "true") and float(r["t"]) >= cut), None)
    t_vis = next((r["t"] for r in vis if r["alarm"] and r["t"] >= cut), None)
    early = lambda rows, key: sum(1 for r in rows if str(r[key]).lower() in ("1", "true") and float(r["t"]) < cut)
    fmt = lambda x: "no alarm" if x is None else f"t = {x:.0f} s, {x - cut:.1f} s after the cut"
    print(f"clock offset {off:.2f} s, cut at flight t = {cut:.1f} s, vision baseline horizon_y {by:.3f}, roll {br:.1f} deg")
    print(f"telemetry: {fmt(t_tel)} (alarm seconds before the cut: {early(tel, 'alarm')})")
    print(f"vision:    {fmt(t_vis)} (alarm seconds before the cut: {early(vis, 'alarm')})")
    if t_tel is not None and t_vis is not None:
        print("first:", "telemetry" if t_tel < t_vis else "vision" if t_vis < t_tel else "same second", f"(gap {abs(t_tel - t_vis):.0f} s)")


if __name__ == "__main__":
    main()
