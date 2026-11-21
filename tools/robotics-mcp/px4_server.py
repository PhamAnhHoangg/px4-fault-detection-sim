"""PX4 MCP server (stdio). Read parameters and state, set allowed parameters, inject and clear the known faults,
and run the offline detector evaluation. Every change goes through robotics_guard (ask mode or lazy mode).
Environment: PX4_CONNECTION (default udpin:0.0.0.0:14540), PX4_SIM_REPO (path of px4-fault-detection-sim)."""
import json, os, subprocess, sys, time
from pathlib import Path
import robotics_guard as guard
import px4_core
from px4_core import FAULTS, check_limits as _limits
from px4_backend import Px4Backend, BackendError
from mcp.server.mcpserver import MCPServer

SERVER = "px4"
SCOPE = "px4:params"
mcp = MCPServer("px4", instructions=(
    "Tools for a PX4 simulation. Changes need the user's approval: when a tool returns needs_confirmation, tell the user "
    "the exact command to run in their own terminal, wait until they say it is done, then repeat the same call. "
    "Never try to work around a denial. Always clear faults when a test is over."))
backend = Px4Backend(os.environ.get("PX4_CONNECTION", "udpin:0.0.0.0:14540"))


def _j(x):
    return json.dumps(x, indent=2, default=str)


def _gate(tool, tier, args):
    res = guard.check(SERVER, tool, tier, SCOPE, args, real=backend.is_real or guard.config()["px4"]["real_hardware"])
    if res["decision"] == "allow":
        return None
    if res["decision"] == "deny":
        return _j({"status": "denied", "reason": res["reason"]})
    return _j(guard.confirm_message(res))


@mcp.tool()
def px4_status() -> str:
    """Connection, whether it is a simulator or real hardware, armed state and altitude."""
    guard.check(SERVER, "px4_status", guard.READ, SCOPE, {})
    try:
        return _j(backend.status())
    except BackendError as e:
        return f"error: {e}"


@mcp.tool()
def px4_get_param(name: str) -> str:
    """Read one PX4 parameter."""
    guard.check(SERVER, "px4_get_param", guard.READ, SCOPE, {"name": name})
    try:
        v, _ = backend.get_param(name)
        return _j({name: v})
    except BackendError as e:
        return f"error: {e}"


@mcp.tool()
def px4_set_param(name: str, value: float) -> str:
    """Set one allowlisted PX4 parameter (range checked). Needs the user's approval or an active lazy-mode grant."""
    try:
        _limits(name, value)
    except ValueError as e:
        guard.audit(SERVER, "px4_set_param", guard.WRITE, "deny", str(e))
        return f"denied: {e}"
    blocked = _gate("px4_set_param", guard.WRITE, {"name": name, "value": value})
    if blocked:
        return blocked
    try:
        old, _ = backend.get_param(name)
        new = backend.set_param(name, value)
        guard.record_result(True)
        return _j({"name": name, "old": old, "new": new})
    except BackendError as e:
        guard.record_result(False)
        return f"error: {e}"


@mcp.tool()
def px4_inject_fault(kind: str) -> str:
    """Inject a known fault: engine_gazebo (FW_THR_MIN/MAX = 0), engine_sih (SIH_T_MAX = 0) or elevator
    (CA_SV_CS2_TRQ_P = 0). The original values are saved so px4_clear_faults can put them back."""
    if kind not in FAULTS:
        return f"error: kind must be one of {sorted(FAULTS)}"
    blocked = _gate("px4_inject_fault", guard.WRITE, {"kind": kind})
    if blocked:
        return blocked
    try:
        out = px4_core.inject(backend, kind)
        guard.record_result(True)
        return _j(out)
    except (BackendError, ValueError) as e:
        guard.record_result(False)
        return f"error: {e}. Run px4_clear_faults to be safe."


@mcp.tool()
def px4_clear_faults() -> str:
    """Put every parameter changed by px4_inject_fault back to its saved original value."""
    blocked = _gate("px4_clear_faults", guard.WRITE, {})
    if blocked:
        return blocked
    try:
        out = px4_core.clear(backend)
        guard.record_result(True)
        return _j(out)
    except BackendError as e:
        guard.record_result(False)
        return f"error: {e}"


@mcp.tool()
def px4_run_eval(table_csv: str) -> str:
    """Run the offline leave-one-flight-out detector evaluation (scripts/detect_eval.py) on a feature table inside
    the project repo and return its summary. Read only: it writes result files under /tmp."""
    repo = Path(os.environ.get("PX4_SIM_REPO", ".")).resolve()
    csv = (repo / table_csv).resolve()
    if repo not in csv.parents or csv.suffix != ".csv" or not csv.exists():
        return "error: the table must be an existing .csv inside the project repo"
    guard.check(SERVER, "px4_run_eval", guard.READ, SCOPE, {"table": table_csv})
    r = subprocess.run([sys.executable, str(repo / "scripts" / "detect_eval.py"), str(csv), "/tmp/px4_mcp_eval"],
                       capture_output=True, text=True, timeout=300, cwd=repo)
    return (r.stdout + r.stderr)[-3000:]


@mcp.tool()
def guard_status() -> str:
    """Show the permission state: active lazy-mode grants, whether lazy mode is suspended, calls waiting for approval."""
    live = [{"scope": g["scope"], "minutes_left": round((g["expires"] - time.time()) / 60), "real": g["allow_real"]}
            for g in guard._read("grants.json", []) if g["expires"] > time.time()]
    pend = {k: f"{v['tool']} {v['args']}" for k, v in guard._read("pending.json", {}).items() if v["status"] == "pending"}
    return _j({"grants": live, "suspended": guard.suspended(), "waiting_for_approval": pend})


if __name__ == "__main__":
    mcp.run()
