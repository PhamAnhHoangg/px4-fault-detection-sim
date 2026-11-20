"""Show what happened in a PX4 ULog: PX4 messages, changed parameters, and a 5 s summary of
height, speed, flight mode and motor output. Use it to check a flight before building a table.
Usage: python inspect_log.py flight.ulg"""
import sys, numpy as np, pandas as pd
from pyulog import ULog

def topic(u, name):
    d = [x for x in u.data_list if x.name == name]
    return pd.DataFrame(d[0].data) if d else None

u = ULog(sys.argv[1])
print("duration_s", round((u.last_timestamp - u.start_timestamp) / 1e6, 1))
print("\n--- PX4 messages")
for m in u.logged_messages:
    print(round(m.timestamp / 1e6, 1), m.message)
print("\n--- changed parameters (CAL_* left out)")
for t, n, v in u.changed_parameters:
    if not n.startswith("CAL_"):
        print(round(t / 1e6, 1), n, v)

lp, st, mo = topic(u, "vehicle_local_position"), topic(u, "vehicle_status"), topic(u, "actuator_motors")
if lp is None:
    sys.exit("no vehicle_local_position in this log")
lp = lp.sort_values("timestamp").copy()
lp["speed"] = np.sqrt(lp["vx"]**2 + lp["vy"]**2 + lp["vz"]**2)
if st is not None:
    lp = pd.merge_asof(lp, st[["timestamp", "nav_state", "arming_state"]].sort_values("timestamp"), on="timestamp")
if mo is not None and "control[0]" in mo.columns:
    lp = pd.merge_asof(lp, mo[["timestamp", "control[0]"]].rename(columns={"control[0]": "motor0"}).sort_values("timestamp"), on="timestamp")
lp["t"] = (lp["timestamp"] // 1_000_000 // 5) * 5
cols = [c for c in ("z", "speed", "vz", "nav_state", "arming_state", "motor0") if c in lp.columns]
print("\n--- every 5 s: z (negative = up, m), speed (m/s), vz (m/s, positive = sinking), nav_state (last in window), arming_state (2 = armed), motor0")
agg = {c: ("last" if c in ("nav_state", "arming_state") else "mean") for c in cols}
print(lp.groupby("t").agg(agg).round(2).to_string())
