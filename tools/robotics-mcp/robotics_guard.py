"""Shared safety layer for the robotics MCP servers.

Every tool declares a tier: READ (looks only), WRITE (changes a setting, reversible) or PHYSICAL (can move
something or cannot be undone). The server asks check() before it acts. Result is allow, confirm or deny.

  ask mode (default): READ runs; WRITE and PHYSICAL need your approval for that exact call.
  lazy mode: you grant a scope for N minutes; inside it WRITE runs without asking, and PHYSICAL runs only on a
             simulator. PHYSICAL on real hardware always needs a per-call approval, grant or not.

Grants and approvals are made by you in your own terminal (this file is also the command line tool), never by a
tool call. They are signed with a secret that is stored next to them. Limits in config.json (parameter
allowlist with ranges, rate limit) are checked on every call and a grant cannot widen them.

Honest limit: this protects against instructions hidden in tool output (a log line, a topic, a serial line) and
against the model asking for more than you allowed. It does not protect against a process that already runs as
your user and can read your files.
"""
import argparse, hashlib, hmac, json, os, secrets, sys, time
from pathlib import Path

READ, WRITE, PHYSICAL = "read", "write", "physical"
APPROVAL_TTL = 600          # seconds an approval stays usable (single use)
MAX_ERRORS = 2              # errors in a row inside a grant, then back to ask mode until `resume`

DEFAULT_CONFIG = {
    "rate_limit_per_min": 20,
    "px4": {
        "param_allow": {
            "FW_THR_MIN": [0, 1], "FW_THR_MAX": [0, 1], "SIH_T_MAX": [0, 10], "CA_SV_CS2_TRQ_P": [0, 1],
            "NAV_DLL_ACT": [0, 6], "NAV_LOITER_RAD": [50, 300], "MIS_TAKEOFF_ALT": [5, 120],
            "RWTO_TKOFF": [0, 1], "FW_LAUN_DETCN_ON": [0, 1],
        },
        "real_hardware": False,
    },
}


def state_dir():
    d = Path(os.environ.get("ROBOTICS_MCP_DIR", Path.home() / ".robotics-mcp"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read(name, default):
    p = state_dir() / name
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return default


def _write(name, data):
    p = state_dir() / name
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    os.replace(tmp, p)


def _secret():
    p = state_dir() / "secret"
    if not p.exists():
        p.write_text(secrets.token_hex(32))
        try:
            p.chmod(0o600)
        except OSError:
            pass
    return p.read_text().strip().encode()


def _sign(payload: dict) -> str:
    msg = json.dumps(payload, sort_keys=True).encode()
    return hmac.new(_secret(), msg, hashlib.sha256).hexdigest()


def config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    user = _read("config.json", {})
    for k, v in user.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg


def audit(server, tool, tier, outcome, detail=""):
    with open(state_dir() / "audit.jsonl", "a") as f:
        f.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "server": server, "tool": tool,
                            "tier": tier, "outcome": outcome, "detail": detail}) + "\n")


def _action_id(server, tool, args):
    blob = json.dumps([server, tool, args], sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:8]


# ---- grants (made by the user in a terminal) -------------------------------------------------

def make_grant(scope, minutes, allow_real=False):
    g = {"scope": scope, "expires": time.time() + 60 * minutes, "allow_real": bool(allow_real), "nonce": secrets.token_hex(4)}
    g["sig"] = _sign({k: g[k] for k in ("scope", "expires", "allow_real", "nonce")})
    grants = [x for x in _read("grants.json", []) if x["scope"] != scope] + [g]
    _write("grants.json", grants)
    return g


def active_grant(scope):
    for g in _read("grants.json", []):
        body = {k: g.get(k) for k in ("scope", "expires", "allow_real", "nonce")}
        if g.get("scope") == scope and g.get("expires", 0) > time.time() and hmac.compare_digest(g.get("sig", ""), _sign(body)):
            return g
    return None


def revoke(scope=None):
    grants = [] if scope in (None, "all") else [g for g in _read("grants.json", []) if g["scope"] != scope]
    _write("grants.json", grants)


def suspended():
    return bool(_read("state.json", {}).get("suspended"))


def set_suspended(flag):
    st = _read("state.json", {}); st["suspended"] = bool(flag); st["errors"] = 0
    _write("state.json", st)


def record_result(ok):
    """Call after a WRITE or PHYSICAL action ran. Two errors in a row suspend lazy mode."""
    st = _read("state.json", {})
    st["errors"] = 0 if ok else st.get("errors", 0) + 1
    if st["errors"] >= MAX_ERRORS:
        st["suspended"] = True
    _write("state.json", st)


# ---- approvals --------------------------------------------------------------------------------

def approve(action_id, yes=True):
    pend = _read("pending.json", {})
    if action_id not in pend:
        return False
    pend[action_id]["status"] = "approved" if yes else "denied"
    pend[action_id]["decided"] = time.time()
    _write("pending.json", pend)
    return True


def _use_approval(action_id):
    pend = _read("pending.json", {})
    p = pend.get(action_id)
    if p and p["status"] == "approved" and time.time() - p["decided"] < APPROVAL_TTL:
        del pend[action_id]
        _write("pending.json", pend)
        return True
    return False


# ---- the check the servers call ---------------------------------------------------------------

def check(server, tool, tier, scope, args, real=False):
    """Returns dict: {'decision': 'allow'|'confirm'|'deny', 'reason': str, 'approval_id': str|None}."""
    def out(decision, reason, aid=None):
        audit(server, tool, tier, decision, f"{reason} {json.dumps(args, default=str)}"[:300])
        return {"decision": decision, "reason": reason, "approval_id": aid}

    if tier == READ:
        return out("allow", "read")
    # rate limit on anything that changes something
    log = [t for t in _read("rate.json", []) if t > time.time() - 60]
    if len(log) >= config()["rate_limit_per_min"]:
        return out("deny", "rate limit reached, wait a minute")
    aid = _action_id(server, tool, args)
    g = None if suspended() else active_grant(scope)
    lazy_ok = g is not None and (not real or g["allow_real"])
    if tier == PHYSICAL and real:
        lazy_ok = False   # real hardware: never lazy
    if lazy_ok:
        _write("rate.json", log + [time.time()])
        return out("allow", f"grant {scope}")
    if _use_approval(aid):
        _write("rate.json", log + [time.time()])
        return out("allow", "approved by user")
    pend = _read("pending.json", {})
    if aid in pend and pend[aid]["status"] == "denied":
        del pend[aid]               # the denial is reported once; a later call may ask again
        _write("pending.json", pend)
        return out("deny", "user denied this call")
    if aid not in pend:
        pend[aid] = {"server": server, "tool": tool, "tier": tier, "args": args, "real": real,
                     "status": "pending", "asked": time.time()}
        _write("pending.json", pend)
    why = "real hardware" if (tier == PHYSICAL and real) else ("lazy mode suspended after errors" if suspended() else "no grant")
    return out("confirm", f"needs your approval ({why})", aid)


def confirm_message(res):
    return {"status": "needs_confirmation", "approval_id": res["approval_id"], "reason": res["reason"],
            "how": f"Tell the user to run in their own terminal: python robotics_guard.py approve {res['approval_id']}  "
                   "then repeat the same call. The approval works once, for 10 minutes."}


# ---- command line for the user ----------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="Grant, approve and inspect robotics MCP permissions")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grant", help="lazy mode for a scope, for a limited time")
    g.add_argument("scope"); g.add_argument("--minutes", type=int, default=30)
    g.add_argument("--real", action="store_true", help="also allow WRITE on real hardware (PHYSICAL still asks)")
    r = sub.add_parser("revoke"); r.add_argument("scope", nargs="?", default="all")
    a = sub.add_parser("approve"); a.add_argument("id")
    d = sub.add_parser("deny"); d.add_argument("id")
    sub.add_parser("pending"); sub.add_parser("status"); sub.add_parser("resume")
    lg = sub.add_parser("log"); lg.add_argument("-n", type=int, default=20)
    a = ap.parse_args(argv)
    if a.cmd == "grant":
        if a.minutes < 1 or a.minutes > 480:
            sys.exit("minutes must be 1 to 480")
        x = make_grant(a.scope, a.minutes, a.real)
        print(f"lazy mode on for '{a.scope}' until {time.strftime('%H:%M', time.localtime(x['expires']))}"
              + (" (real hardware writes allowed)" if a.real else " (simulators only)"))
    elif a.cmd == "revoke":
        revoke(a.scope); print("revoked", a.scope)
    elif a.cmd in ("approve", "deny"):
        print("done" if approve(a.id, a.cmd == "approve") else "no such pending call")
    elif a.cmd == "pending":
        for k, v in _read("pending.json", {}).items():
            if v["status"] == "pending":
                print(k, v["tier"], v["tool"], json.dumps(v["args"]), "REAL" if v["real"] else "sim")
    elif a.cmd == "resume":
        set_suspended(False); print("lazy mode can be used again")
    elif a.cmd == "status":
        live = [x for x in _read("grants.json", []) if x["expires"] > time.time()]
        print("suspended after errors:", suspended())
        for x in live:
            print(f"grant {x['scope']} until {time.strftime('%H:%M', time.localtime(x['expires']))} real={x['allow_real']}")
        if not live:
            print("no grants: ask mode")
    elif a.cmd == "log":
        p = state_dir() / "audit.jsonl"
        for line in (p.read_text().splitlines()[-a.n:] if p.exists() else []):
            print(line)


if __name__ == "__main__":
    main()
