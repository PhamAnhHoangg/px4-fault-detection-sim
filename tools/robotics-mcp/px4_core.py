"""PX4 logic shared by the MCP server (px4_server.py) and the command line (px4ctl.py): allowlist checks and fault
inject/clear with saved originals. The caller decides who approves; this module only acts and records."""
import json
import robotics_guard as guard

FAULTS = {   # parameter values used in the recorded flights
    "engine_gazebo": {"FW_THR_MIN": 0, "FW_THR_MAX": 0},
    "engine_sih": {"SIH_T_MAX": 0},
    "elevator": {"CA_SV_CS2_TRQ_P": 0},
}


def check_limits(name, value):
    allow = guard.config()["px4"]["param_allow"]
    if name not in allow:
        raise ValueError(f"{name} is not on the allowlist (edit config.json yourself to add it)")
    lo, hi = allow[name]
    if not (lo <= float(value) <= hi):
        raise ValueError(f"{name}={value} is outside the allowed range {lo} to {hi}")


def _faults_file():
    return guard.state_dir() / "px4_faults.json"


def inject(backend, kind):
    if kind not in FAULTS:
        raise ValueError(f"kind must be one of {sorted(FAULTS)}")
    for name, val in FAULTS[kind].items():
        check_limits(name, val)
    f = _faults_file()
    saved = json.loads(f.read_text()) if f.exists() else {}
    for name, val in FAULTS[kind].items():
        if name not in saved:          # never overwrite an original with a fault value
            saved[name] = backend.get_param(name)[0]
        f.write_text(json.dumps(saved))
        backend.set_param(name, val)
    return {"injected": kind, "set": FAULTS[kind], "originals_saved": saved}


def clear(backend):
    f = _faults_file()
    if not f.exists():
        return {"restored": {}, "note": "nothing was injected"}
    saved = json.loads(f.read_text())
    for name, val in saved.items():
        backend.set_param(name, val)
    f.unlink()
    return {"restored": saved}
