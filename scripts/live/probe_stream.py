"""Diagnostic: listen to PX4 over MAVLink for N seconds and print, per message type, how many messages arrived,
how much wall time and how much PX4 time (time_boot_ms) they cover, and the biggest gap between two messages.
Use it on the ground, before takeoff, if the live detector shows many empty seconds.
Usage: python probe_stream.py [seconds] [address]"""
import sys, time
from pymavlink import mavutil

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 15
addr = sys.argv[2] if len(sys.argv) > 2 else "udpin:0.0.0.0:14540"
ids = {"ATTITUDE_QUATERNION": 31, "LOCAL_POSITION_NED": 32, "GLOBAL_POSITION_INT": 33, "ATTITUDE_TARGET": 83, "POSITION_TARGET_GLOBAL_INT": 87}
m = mavutil.mavlink_connection(addr)
if m.wait_heartbeat(timeout=30) is None:
    sys.exit("no heartbeat")
for mid in ids.values():
    m.mav.command_long_send(m.target_system, m.target_component, 511, 0, mid, 100000, 0, 0, 0, 0, 0)
stats, t_start = {}, time.time()
while time.time() - t_start < secs:
    x = m.recv_match(blocking=True, timeout=0.5)
    if x is None:
        continue
    ty, now = x.get_type(), time.time()
    s = stats.setdefault(ty, {"n": 0, "w0": now, "w1": now, "t0": None, "t1": None, "maxgap": 0.0, "lastw": now, "modes": set()})
    s["n"] += 1; s["w1"] = now; s["maxgap"] = max(s["maxgap"], now - s["lastw"]); s["lastw"] = now
    if ty == "HEARTBEAT":
        s["modes"].add((x.type, x.base_mode))
    tb = getattr(x, "time_boot_ms", None)
    if tb is not None:
        s["t0"] = tb if s["t0"] is None else s["t0"]; s["t1"] = tb
print(f"{'message':30s} {'count':>6s} {'wall s':>7s} {'px4 s':>7s} {'msgs/px4 s':>10s} {'max wall gap s':>14s} {'first time_boot_ms':>18s}")
for ty, s in sorted(stats.items()):
    wall = s["w1"] - s["w0"]
    px4 = (s["t1"] - s["t0"]) / 1000 if s["t0"] is not None else float("nan")
    rate = s["n"] / px4 if px4 and px4 == px4 and px4 > 0 else float("nan")
    print(f"{ty:30s} {s['n']:6d} {wall:7.1f} {px4:7.1f} {rate:10.1f} {s['maxgap']:14.2f} {str(s['t0']):>18s}" + (f"  heartbeat (type, base_mode): {sorted(s['modes'])}" if ty == "HEARTBEAT" else ""))
