"""Live fault detector for a running PX4 simulation (SIH or Gazebo), over MAVLink.

It builds the same per-second features as scripts/build_table.py (5 s mean, 5 s std, 10 s change of
altitude error, altitude, climb rate, cross-track error to the loiter circle, roll/pitch/yaw gap), runs the
saved random forest every second and raises an alarm after 3 raw alarms in a row. The time axis is simulation
time (the time stamps PX4 sends), so a slow simulator does not change the result.

The first --settle seconds after arming are skipped, the same as SETTLE_S when the model was trained.

Optional: --cut-at S sets the engine-cut parameters S seconds after the settle time, and puts the
original values back when the script ends. These parameters are remembered by PX4 between runs, so if the
script is killed hard (kill -9, closed terminal) check FW_THR_MAX yourself.

Usage examples:
  python live_detector.py --model model.joblib                      # watch only, you fly by hand
  python live_detector.py --model model.joblib --cut-at 25 \
      --fault FW_THR_MIN=0 --fault FW_THR_MAX=0                     # cut the engine for you
"""
import argparse, math, struct, sys, time
from collections import defaultdict
import numpy as np, pandas as pd, joblib
from pymavlink import mavutil

K = 3
THRESH = 0.5
SIGNALS = ["alt_error", "hud_altitude", "vel_lin_z", "xtrack_error", "roll_gap", "pitch_gap", "yaw_gap"]
INTERVAL_MS = 100  # ask PX4 for 10 Hz of each message we need
MSG_IDS = {"ATTITUDE_QUATERNION": 31, "LOCAL_POSITION_NED": 32, "GLOBAL_POSITION_INT": 33,
           "ATTITUDE_TARGET": 83, "POSITION_TARGET_GLOBAL_INT": 87}


def euler(w, x, y, z):  # same formulas as build_table.py
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    pitch = math.asin(max(-1, min(1, 2 * (w * y - z * x))))
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return roll, pitch, yaw


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


INT_TYPES = (mavutil.mavlink.MAV_PARAM_TYPE_INT8, mavutil.mavlink.MAV_PARAM_TYPE_INT16, mavutil.mavlink.MAV_PARAM_TYPE_INT32,
             mavutil.mavlink.MAV_PARAM_TYPE_UINT8, mavutil.mavlink.MAV_PARAM_TYPE_UINT16, mavutil.mavlink.MAV_PARAM_TYPE_UINT32)


def read_param(master, name, tries=5):
    """Returns (value, mavlink type). PX4 sends integer parameters as raw bytes inside the float field."""
    for _ in range(tries):  # PX4 sometimes drops a request while it is busy, so ask again
        master.mav.param_request_read_send(master.target_system, master.target_component, name.encode(), -1)
        end = time.time() + 1.5
        while time.time() < end:
            m = master.recv_match(type="PARAM_VALUE", blocking=True, timeout=0.3)
            if m is not None and m.param_id.rstrip("\x00") == name:
                v = m.param_value
                if m.param_type in INT_TYPES:
                    v = struct.unpack("<i", struct.pack("<f", v))[0]
                return v, m.param_type
    return None, None


def get_param(master, name):
    return read_param(master, name)[0]


def set_param(master, name, value):
    _, ptype = read_param(master, name)
    if ptype is None:
        sys.exit(f"could not read {name} before setting it")
    raw = struct.unpack("<f", struct.pack("<i", int(value)))[0] if ptype in INT_TYPES else float(value)
    master.mav.param_set_send(master.target_system, master.target_component, name.encode(), raw, ptype)


def parse_kv(items):
    out = []
    for s in items or []:
        k, v = s.split("=")
        out.append((k, float(v)))
    return out


def features_for_bin(series, b):
    """series: dict signal -> dict bin -> value. Same windows as build_table.py, last row only."""
    feats = {}
    for name in SIGNALS:
        x = pd.Series([series[name].get(i, np.nan) for i in range(b + 1)], dtype=float).ffill(limit=5)
        feats[f"{name}__mean5"] = x.rolling(5, min_periods=3).mean().iloc[-1]
        feats[f"{name}__std5"] = x.rolling(5, min_periods=3).std().iloc[-1]
        feats[f"{name}__delta10"] = (x - x.shift(10)).iloc[-1]
    return feats


class Window:
    """Small live plot: fault probability, threshold, alarm. Needs a display (WSLg shows it on Windows)."""
    def __init__(self, png=None):
        import matplotlib
        if png:
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        self.plt, self.png = plt, png
        self.fig, self.ax = plt.subplots(figsize=(8, 3.6))
        self.fig.canvas.manager.set_window_title("UAV fault detector (live)") if not png else None
        self.t, self.p, self.alarm = [], [], []
        self.cut = None
        if not png:
            plt.ion(); plt.show(block=False)

    def update(self, t, prob, alarm, cut_t):
        self.t.append(t); self.p.append(prob); self.alarm.append(alarm)
        if cut_t is not None:
            self.cut = cut_t
        ax = self.ax; ax.clear()
        ax.plot(self.t, self.p, color="tab:blue", lw=1.6, label="fault probability")
        ax.axhline(THRESH, color="gray", ls="--", lw=1, label="threshold 0.5")
        for tt, a in zip(self.t, self.alarm):
            if a:
                ax.axvspan(tt, tt + 1, color="tab:red", alpha=0.25, lw=0)
        if self.cut is not None:
            ax.axvline(self.cut, color="black", lw=1.2, label="engine cut")
        ax.set_ylim(-0.02, 1.05); ax.set_xlabel("seconds since settle time (simulation time)"); ax.set_ylabel("probability")
        state = "FAULT ALARM" if alarm else "normal"
        ax.set_title(state, color="tab:red" if alarm else "tab:green", fontsize=16, fontweight="bold")
        ax.legend(loc="center left", fontsize=8)
        self.fig.tight_layout()
        if self.png:
            self.fig.savefig(self.png, dpi=110)
        else:
            self.plt.pause(0.001)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--connect", default="udpin:0.0.0.0:14540", help="MAVLink address (SITL onboard port 14540; 14550 is the GCS port)")
    ap.add_argument("--settle", type=int, default=30, help="seconds after arming to skip (must match SETTLE_S of the table)")
    ap.add_argument("--csv", default=None, help="write one row per second here")
    ap.add_argument("--png", default=None, help="no window: save the plot to this file every second")
    ap.add_argument("--no-plot", action="store_true")
    ap.add_argument("--cut-at", type=int, default=None, help="seconds after the settle time at which to set the --fault parameters")
    ap.add_argument("--fault", action="append", help="PARAM=VALUE set at the cut, e.g. FW_THR_MAX=0 (repeat)")
    ap.add_argument("--set", action="append", help="PARAM=VALUE set once at the start, e.g. NAV_DLL_ACT=0 (repeat)")
    ap.add_argument("--max-seconds", type=int, default=None, help="stop after this many seconds past the settle time")
    ap.add_argument("--wait", type=int, default=60, help="seconds to wait for the first MAVLink heartbeat")
    args = ap.parse_args()

    pack = joblib.load(args.model)
    model, features = pack["model"], pack["features"]
    print(f"model trained on: {', '.join(pack['trained_on'])}")
    master = mavutil.mavlink_connection(args.connect)
    print(f"waiting for PX4 on {args.connect} ...", flush=True)
    if master.wait_heartbeat(timeout=args.wait) is None:
        sys.exit("no heartbeat. Is the simulator running? (PX4 prints 'Ready for takeoff' when it is up)")
    print(f"connected, system {master.target_system}")
    for name, mid in MSG_IDS.items():
        master.mav.command_long_send(master.target_system, master.target_component,
                                     mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0, mid, INTERVAL_MS * 1000, 0, 0, 0, 0, 0)

    sets = parse_kv(args.set)
    for k, v in sets:
        set_param(master, k, v); time.sleep(0.2)
    loiter_rad = get_param(master, "NAV_LOITER_RAD")
    if loiter_rad is None:
        sys.exit("could not read NAV_LOITER_RAD")
    faults = parse_kv(args.fault)
    original = {}
    for k, _ in faults:
        original[k] = get_param(master, k)
        if original[k] is None:
            sys.exit(f"could not read {k}")
    print(f"loiter radius {loiter_rad:.0f} m; fault parameters now: {original}")

    window = None if args.no_plot else Window(args.png)
    acc = defaultdict(lambda: defaultdict(list))  # signal -> bin -> samples
    series = {n: {} for n in SIGNALS}
    now_ms, arm_ms, t0_ms = 0, None, None
    last = {"tl": None, "tn": None, "alt_sp": None}
    raw_hist, rows, cut_done, cut_t = [], [], False, None
    next_bin = 0
    armed_seen = False

    def finalize(b):
        nonlocal raw_hist
        for n in ("alt_error", "hud_altitude", "vel_lin_z", "xtrack_error"):
            v = acc[n].get(b)
            series[n][b] = float(np.mean(v)) if v else np.nan
        for g, (a, s) in {"roll_gap": ("roll", "roll_sp"), "pitch_gap": ("pitch", "pitch_sp"), "yaw_gap": ("yaw", "yaw_sp")}.items():
            va, vs = acc[a].get(b), acc[s].get(b)
            series[g][b] = wrap(float(np.mean(va)) - float(np.mean(vs))) if va and vs else np.nan
        row = {"t": b, "prob": np.nan, "raw": 0, "alarm": False, "samples": len(acc["hud_altitude"].get(b, []))}
        row.update({n: series[n][b] for n in SIGNALS})
        if b >= 10:
            f = features_for_bin(series, b)
            if all(np.isfinite(f[c]) for c in features):
                p = float(model.predict_proba(pd.DataFrame([f], columns=features))[0, 1])
                raw_hist.append(int(p >= THRESH))
                row.update(prob=p, raw=raw_hist[-1], alarm=len(raw_hist) >= K and all(raw_hist[-K:]))
        rows.append(row)
        flag = "ALARM" if row["alarm"] else ""
        ptxt = "  n/a" if np.isnan(row["prob"]) else f"{row['prob']:5.2f}"
        print(f"t={b:3d}s  prob={ptxt}  alt_err={row['alt_error']:7.2f}  alt={row['hud_altitude']:6.1f}  "
              f"vz={row['vel_lin_z']:5.1f}  n={row['samples']:2d}  {flag}", flush=True)
        if window is not None and not np.isnan(row["prob"]):
            window.update(b, row["prob"], row["alarm"], cut_t)

    print(f"watching. Flight starts counting {args.settle} s after arming.", flush=True)
    last_rx = time.time(); last_ui = 0.0
    try:
        while True:
            m = master.recv_match(blocking=True, timeout=0.2)
            if window is not None and not window.png and time.time() - last_ui > 0.1:
                window.plt.pause(0.001)  # let the window handle clicks and redraw, at most 10 times a second
                last_ui = time.time()
            if m is None:
                if time.time() - last_rx > 15:
                    print("no data for 15 s, stopping"); break
                continue
            last_rx = time.time()
            ty = m.get_type()
            if ty == "HEARTBEAT" and m.type != mavutil.mavlink.MAV_TYPE_GCS:
                armed = bool(m.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                if armed and arm_ms is None:
                    arm_ms = now_ms; t0_ms = arm_ms + args.settle * 1000; armed_seen = True
                    print(f"armed (sim time {now_ms/1000:.1f} s)", flush=True)
                if armed_seen and not armed:
                    print("disarmed, flight over"); break
                continue
            if hasattr(m, "time_boot_ms"):
                now_ms = max(now_ms, m.time_boot_ms)
            if t0_ms is None or now_ms < t0_ms:
                continue
            b = (now_ms - t0_ms) // 1000
            while next_bin < b:  # bins before b are complete
                finalize(next_bin); next_bin += 1
                if args.cut_at is not None and not cut_done and next_bin >= args.cut_at:
                    for k, v in faults:
                        set_param(master, k, v)
                    cut_done = True; cut_t = (now_ms - t0_ms) / 1000
                    print(f"*** fault parameters set at t={cut_t:.1f} s: {faults}", flush=True)
                if args.max_seconds is not None and next_bin >= args.max_seconds:
                    raise KeyboardInterrupt
            if ty == "GLOBAL_POSITION_INT":
                acc["hud_altitude"][b].append(m.alt / 1000.0)
                if last["alt_sp"] is not None:  # altitude error = altitude setpoint minus measured altitude
                    acc["alt_error"][b].append(last["alt_sp"] - m.alt / 1000.0)
                if last["tl"] is not None and loiter_rad > 1:
                    k = 111_320.0
                    lat, lon = m.lat / 1e7, m.lon / 1e7
                    dx = (lat - last["tl"]) * k
                    dy = (lon - last["tn"]) * k * math.cos(math.radians(lat))
                    acc["xtrack_error"][b].append(math.hypot(dx, dy) - loiter_rad)
            elif ty == "LOCAL_POSITION_NED":
                acc["vel_lin_z"][b].append(-m.vz)
            elif ty == "POSITION_TARGET_GLOBAL_INT":
                last["tl"], last["tn"], last["alt_sp"] = m.lat_int / 1e7, m.lon_int / 1e7, m.alt
            elif ty == "ATTITUDE_QUATERNION":
                r, p, y = euler(m.q1, m.q2, m.q3, m.q4)
                acc["roll"][b].append(r); acc["pitch"][b].append(p); acc["yaw"][b].append(y)
            elif ty == "ATTITUDE_TARGET":
                r, p, y = euler(*m.q)
                acc["roll_sp"][b].append(r); acc["pitch_sp"][b].append(p); acc["yaw_sp"][b].append(y)
    except KeyboardInterrupt:
        print("stopping")
    finally:
        for k, v in original.items():
            if cut_done:
                set_param(master, k, v)
                print(f"restored {k} = {v}")
        if args.csv and rows:
            df = pd.DataFrame(rows); df["fault_sec"] = cut_t
            df.to_csv(args.csv, index=False); print("saved", args.csv)
        if rows:
            al = [r["t"] for r in rows if r["alarm"]]
            if cut_t is not None:
                after = [t for t in al if t + 1 > cut_t]
                pre = [t for t in al if t + 1 <= cut_t]
                print(f"summary: cut at {cut_t:.1f} s, first alarm after cut at t={after[0] if after else 'none'}, alarms before cut: {len(pre)}")
            else:
                print(f"summary: {len(al)} alarm seconds in {len(rows)} s")
        if window is not None and not window.png and rows:
            print("flight over. The plot window stays open: close it to end the script.", flush=True)
            window.plt.ioff(); window.plt.show()


if __name__ == "__main__":
    main()
