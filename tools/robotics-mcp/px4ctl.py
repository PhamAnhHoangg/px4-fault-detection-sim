"""Command line for the PX4 tools, no AI involved. You are the one deciding, so a change asks you y/N in the
terminal (or pass --yes). The allowlist, ranges, rate limit and audit log of robotics_guard still apply.

  python px4ctl.py status
  python px4ctl.py get FW_THR_MAX
  python px4ctl.py set NAV_LOITER_RAD 120
  python px4ctl.py inject engine_gazebo      # engine_gazebo, engine_sih or elevator
  python px4ctl.py clear
  python px4ctl.py eval results/gazebo/table_gz.csv
env: PX4_CONNECTION (default udpin:0.0.0.0:14540). Only one program can use that port at a time.
"""
import argparse, json, os, subprocess, sys, time
from pathlib import Path
import robotics_guard as guard
import px4_core
from px4_backend import Px4Backend, BackendError

SERVER = "px4ctl"


def confirm(text, yes):
    if yes:
        return True
    if not sys.stdin.isatty():
        print("not confirmed (no terminal to ask; add --yes)")
        return False
    return input(f"{text} [y/N] ").strip().lower() in ("y", "yes")


def gate(tool, args, backend):
    """Rate limit and audit for a change the user confirmed at the keyboard."""
    log = [t for t in guard._read("rate.json", []) if t > time.time() - 60]
    if len(log) >= guard.config()["rate_limit_per_min"]:
        guard.audit(SERVER, tool, guard.WRITE, "deny", "rate limit")
        sys.exit("rate limit reached, wait a minute")
    guard._write("rate.json", log + [time.time()])
    guard.audit(SERVER, tool, guard.WRITE, "allow", f"confirmed at keyboard real={backend.is_real} {json.dumps(args)}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="PX4 tools without AI")
    ap.add_argument("--yes", action="store_true", help="do not ask before a change")
    ap.add_argument("--connect", default=os.environ.get("PX4_CONNECTION", "udpin:0.0.0.0:14540"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    g = sub.add_parser("get"); g.add_argument("name")
    s = sub.add_parser("set"); s.add_argument("name"); s.add_argument("value", type=float)
    i = sub.add_parser("inject"); i.add_argument("kind", choices=sorted(px4_core.FAULTS))
    sub.add_parser("clear")
    e = sub.add_parser("eval"); e.add_argument("table")
    a = ap.parse_args(argv)

    if a.cmd == "eval":   # offline, no simulator needed
        repo = Path(__file__).resolve().parents[2]
        r = subprocess.run([sys.executable, str(repo / "scripts" / "detect_eval.py"), a.table, "/tmp/px4ctl_eval"], cwd=repo)
        return r.returncode

    b = Px4Backend(a.connect)
    try:
        if a.cmd == "status":
            print(json.dumps(b.status(), indent=2))
        elif a.cmd == "get":
            print(a.name, "=", b.get_param(a.name)[0])
        elif a.cmd == "set":
            px4_core.check_limits(a.name, a.value)
            old = b.get_param(a.name)[0]
            where = "REAL HARDWARE" if b.is_real else "simulator"
            if not confirm(f"set {a.name} from {old} to {a.value} on the {where}?", a.yes):
                return 1
            gate("set", {"name": a.name, "value": a.value}, b)
            print(a.name, "=", b.set_param(a.name, a.value))
        elif a.cmd == "inject":
            if not confirm(f"inject {a.kind} ({px4_core.FAULTS[a.kind]}) on the {'REAL HARDWARE' if b.is_real else 'simulator'}?", a.yes):
                return 1
            gate("inject", {"kind": a.kind}, b)
            print(json.dumps(px4_core.inject(b, a.kind), indent=2))
            print("remember: python px4ctl.py clear")
        elif a.cmd == "clear":   # putting values back is the safe direction: no question
            gate("clear", {}, b)
            print(json.dumps(px4_core.clear(b), indent=2))
    except (BackendError, ValueError) as err:
        print("error:", err)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
