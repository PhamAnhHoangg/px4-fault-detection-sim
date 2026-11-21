"""Build a per-second feature table from PX4 ULog flights, using the ALFA project's windowing:
5 s rolling mean, 5 s rolling std, 10 s change of each signal. Label = 1 from the fault second on.
Fault time = moment SIH_T_MAX (SIH), FW_THR_MAX (Gazebo engine) or CA_SV_CS2_TRQ_P (Gazebo elevator) was set to 0, read from the ULog parameter changes.
SET env SETTLE_S to change how many seconds after arming the table starts (default 30). Env NOISE=1 adds typical sensor noise (robustness test).
Usage: python build_table.py out.csv flight1.ulg flight2.ulg ..."""
import sys, os, numpy as np, pandas as pd
from pyulog import ULog

SETTLE_S = int(os.environ.get("SETTLE_S", 30))  # skip the climb: start after this many seconds of flight
FAULT_PARAMS = ("SIH_T_MAX", "FW_THR_MAX", "CA_SV_CS2_TRQ_P", "CA_SV_CS1_TRQ_P")  # CS1 = elevator in SIH, CS2 = elevator in the Gazebo Cessna  # a change of one of these to 0 marks the fault second
NOISE = float(os.environ.get("NOISE", 0))  # robustness test: 0 = none, 1 = typical sensor noise, see NOISE_STD
# Noise added to the per-second signals at NOISE = 1 (standard deviations): altitude 1 m (GPS-like), climb rate 0.3 m/s,
# distance to the loiter circle 1.5 m, attitude gaps 0.01 rad (about 0.6 degrees). White noise per second, seeded per flight.
NOISE_STD = {"alt": 1.0, "vel_lin_z": 0.3, "xtrack_error": 1.5, "roll_gap": 0.01, "pitch_gap": 0.01, "yaw_gap": 0.01}
POST_FAULT_CAP = 30  # same cap idea as ALFA (evalkit.load(cap=30))

def euler(q):  # q = w,x,y,z
    w, x, y, z = q
    roll = np.arctan2(2*(w*x + y*z), 1 - 2*(x*x + y*y))
    pitch = np.arcsin(np.clip(2*(w*y - z*x), -1, 1))
    yaw = np.arctan2(2*(w*z + x*y), 1 - 2*(y*y + z*z))
    return roll, pitch, yaw

def wrap(a): return (a + np.pi) % (2*np.pi) - np.pi

def topic(u, name):
    d = [x for x in u.data_list if x.name == name]
    return pd.DataFrame(d[0].data) if d else None

def build(path):
    u = ULog(path)
    st = topic(u, "vehicle_status")
    armed = st.loc[st["arming_state"] == 2, "timestamp"]
    if armed.empty:
        raise SystemExit(f"{path}: the vehicle never armed")
    t_arm = int(armed.iloc[0])
    gp, lp, tecs = topic(u, "vehicle_global_position"), topic(u, "vehicle_local_position"), topic(u, "tecs_status")
    att, atts = topic(u, "vehicle_attitude"), topic(u, "vehicle_attitude_setpoint")
    trip, mot = topic(u, "position_setpoint_triplet"), topic(u, "actuator_motors")

    # Fault start = first time after arming that a fault parameter is set LOWER than its value before
    # (covers a cut to 0, a partial loss, and the first step of a slow ramp). Exception: CA_SV_CS*_TRQ_P set HIGHER
    # than 1 also counts (the allocator then moves the surface less: a weak control surface).
    fault_us = None; last = {k: v for k, v in u.initial_parameters.items() if k in FAULT_PARAMS}
    for ts, name, val in u.changed_parameters:
        if name not in FAULT_PARAMS:
            continue
        prev = last.get(name); last[name] = val
        if ts <= t_arm or prev is None or fault_us is not None:
            continue
        weaker = val < prev or (name.startswith("CA_SV_CS") and val > prev and val > 1)
        if weaker:
            fault_us = ts
    t0 = t_arm + SETTLE_S * 1_000_000
    if int(u.last_timestamp) <= t0:
        raise SystemExit(f"{path}: only {(int(u.last_timestamp) - t_arm) / 1e6:.0f} s of armed flight, less than SETTLE_S={SETTLE_S}. Lower SETTLE_S or check the flight with inspect_log.py")

    def per_sec(df, series):
        sec = ((df["timestamp"].to_numpy() - t0) // 1_000_000).astype(int)
        return pd.Series(np.asarray(series, float)).groupby(sec).mean()

    sig = {}
    # altitude error: setpoint minus measured altitude (both AMSL)
    alt_sp = per_sec(tecs, tecs["altitude_sp"]); alt = per_sec(gp, gp["alt"])
    sig["alt_error"] = alt_sp.sub(alt, fill_value=np.nan)
    sig["hud_altitude"] = alt
    sig["vel_lin_z"] = per_sec(lp, -lp["vz"])
    # tracking error proxy in loiter: distance to loiter centre minus loiter radius
    cur_lat = trip["current.lat"].to_numpy(); cur_lon = trip["current.lon"].to_numpy()
    rad = trip["current.loiter_radius"].to_numpy()
    tg = pd.DataFrame({"timestamp": trip["timestamp"], "lat": cur_lat, "lon": cur_lon, "rad": rad})
    gpf = gp[["timestamp", "lat", "lon"]].sort_values("timestamp")
    m = pd.merge_asof(gpf, tg.sort_values("timestamp"), on="timestamp", suffixes=("", "_c"))
    k = 111_320.0
    dx = (m["lat"] - m["lat_c"]) * k
    dy = (m["lon"] - m["lon_c"]) * k * np.cos(np.radians(m["lat"]))
    dist = np.hypot(dx, dy)
    sig["xtrack_error"] = per_sec(m, (dist - m["rad"]).where(m["rad"] > 1))
    # attitude gaps
    r, p, y = euler(att[["q[0]", "q[1]", "q[2]", "q[3]"]].to_numpy().T)
    rs, ps, ys = euler(atts[["q_d[0]", "q_d[1]", "q_d[2]", "q_d[3]"]].to_numpy().T)
    ra, pa, ya = (per_sec(att, v) for v in (r, p, y))
    rb, pb, yb = (per_sec(atts, v) for v in (rs, ps, ys))
    sig["roll_gap"] = wrap(ra.sub(rb, fill_value=np.nan)); sig["pitch_gap"] = wrap(pa.sub(pb, fill_value=np.nan))
    sig["yaw_gap"] = wrap(ya.sub(yb, fill_value=np.nan))

    if NOISE > 0:
        import zlib
        rng = np.random.default_rng(zlib.crc32(os.path.basename(path).encode()))
        n = lambda x, k: x + rng.normal(0, NOISE * NOISE_STD[k], len(x))
        alt_noisy = n(alt, "alt")
        sig["alt_error"] = alt_sp.sub(alt_noisy, fill_value=np.nan); sig["hud_altitude"] = alt_noisy
        for k in ("vel_lin_z", "xtrack_error", "roll_gap", "pitch_gap", "yaw_gap"):
            sig[k] = n(sig[k], k)

    end_s = int((u.last_timestamp - t0) // 1_000_000)
    fault_s = None if fault_us is None else (fault_us - t0) / 1e6
    if fault_s is not None:
        end_s = min(end_s, int(fault_s) + POST_FAULT_CAP)
    else:
        end_s -= 4  # normal flights end with a forced disarm; drop the last seconds
    idx = range(0, end_s)
    parts = []
    for name, s in sig.items():
        x = s.reindex(idx).ffill(limit=5)
        parts.append(pd.DataFrame({f"{name}__mean5": x.rolling(5, min_periods=3).mean(),
                                   f"{name}__std5": x.rolling(5, min_periods=3).std(),
                                   f"{name}__delta10": x - x.shift(10)}))
    df = pd.concat(parts, axis=1); df.index.name = "t"; df = df.reset_index()
    df.insert(0, "flight", os.path.basename(path).replace(".ulg", ""))
    if fault_s is None:
        df["label"] = 0; df["fault_sec"] = np.nan
    else:
        df["label"] = (df["t"] + 1 > fault_s).astype(int); df["fault_sec"] = fault_s
    return df

if __name__ == "__main__":
    out = sys.argv[1]
    tabs = []
    for p in sys.argv[2:]:
        t = build(p); print(p, t.shape, "fault_sec", t["fault_sec"].iloc[0]); tabs.append(t)
    tab = pd.concat(tabs, ignore_index=True)
    feat = [c for c in tab.columns if "__" in c]
    before = len(tab); tab = tab[tab["t"] >= 10].dropna(subset=feat)
    print("dropped for missing values:", before - len(tab))
    tab.to_csv(out, index=False); print(tab.groupby("flight")["label"].agg(["count", "sum"]))
