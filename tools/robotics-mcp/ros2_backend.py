"""Runs the ros2 command line tool safely: no shell, names validated, time limit, output size limit."""
import os, re, shutil, subprocess, sys

NAME_RE = re.compile(r"^[A-Za-z0-9_/~.:\-]+$")   # topic, node, service, package names
MAX_OUT = 4000


class Ros2Error(Exception):
    pass


def check_name(value, what):
    if not isinstance(value, str) or not NAME_RE.match(value) or value.startswith("-") or len(value) > 200:
        raise Ros2Error(f"invalid {what}: {value!r}")
    return value


def check_yaml(value):
    """Messages and service requests must be a flow mapping like {linear: {x: 0.1}}; this also keeps them from being read as options."""
    if not isinstance(value, str) or not value.strip().startswith("{") or len(value) > 2000:
        raise Ros2Error("message must be a YAML mapping starting with '{' (max 2000 characters)")
    return value


def ros2_cmd():
    cmd = os.environ.get("ROS2_BIN", "ros2")
    if os.path.basename(cmd) == cmd and shutil.which(cmd) is None:
        raise Ros2Error("ros2 not found: start the server from a shell where ROS 2 is sourced (source /opt/ros/<distro>/setup.bash)")
    return [cmd] if not cmd.endswith(".py") else [sys.executable, cmd]


def run(args, timeout=10):
    """Returns (exit_code, text). A command that runs past the time limit is killed and reported as a timeout."""
    try:
        p = subprocess.run(ros2_cmd() + list(args), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"")
        out = out.decode(errors="replace") if isinstance(out, bytes) else out
        return 124, (out[-MAX_OUT:] + f"\n[stopped after {timeout} s]").strip()
    text = (p.stdout + p.stderr).strip()
    if len(text) > MAX_OUT:
        text = text[:MAX_OUT] + f"\n[output cut at {MAX_OUT} characters]"
    return p.returncode, text
