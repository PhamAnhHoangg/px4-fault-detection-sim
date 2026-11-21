"""arduino-cli and serial access with validated names, time limits and size limits. No shell is used."""
import os, re, shutil, subprocess, sys, time
from pathlib import Path

MAX_OUT = 4000
SKETCH_RE = re.compile(r"^[A-Za-z0-9_\-]{1,60}$")
FQBN_RE = re.compile(r"^[A-Za-z0-9_.\-]+:[A-Za-z0-9_.\-]+:[A-Za-z0-9_.\-]+(:[A-Za-z0-9_.=,\-]+)?$")
PORT_RE = re.compile(r"^(/dev/tty[A-Za-z0-9._\-]+|COM[0-9]{1,3})$")
MAX_SKETCH_BYTES = 100_000


class ArduinoError(Exception):
    pass


def cli_cmd():
    cmd = os.environ.get("ARDUINO_CLI", "arduino-cli")
    if os.path.basename(cmd) == cmd and shutil.which(cmd) is None:
        raise ArduinoError("arduino-cli not found: install it and make sure it is on PATH (or set ARDUINO_CLI)")
    return [sys.executable, cmd] if cmd.endswith(".py") else [cmd]


def run(args, timeout=120):
    try:
        p = subprocess.run(cli_cmd() + list(args), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f"[stopped after {timeout} s]"
    text = (p.stdout + p.stderr).strip()
    return p.returncode, (text[:MAX_OUT] + f"\n[output cut at {MAX_OUT} characters]") if len(text) > MAX_OUT else text


def sketch_dir(base, name):
    if not base:
        raise ArduinoError("set arduino.sketches_dir in config.json first")
    if not SKETCH_RE.match(name or ""):
        raise ArduinoError("sketch name may only contain letters, digits, _ and -")
    return Path(base).expanduser().resolve() / name


def check_fqbn(f):
    if not FQBN_RE.match(f or ""):
        raise ArduinoError(f"invalid board id (fqbn): {f!r}, expected like arduino:avr:uno")
    return f


def check_port(p, allow):
    if not PORT_RE.match(p or ""):
        raise ArduinoError(f"invalid port: {p!r}")
    if allow and p not in allow:
        raise ArduinoError(f"{p} is not in arduino.ports_allow (edit config.json yourself to add it)")
    return p


def serial_read(port, baud, seconds):
    """Read lines for a few seconds. Opening a port can reset some boards (Uno, Nano)."""
    import serial   # pyserial, imported late so the other tools work without it
    lines, end = [], time.time() + seconds
    with serial.Serial(port, baud, timeout=0.5) as s:
        while time.time() < end and sum(map(len, lines)) < MAX_OUT:
            raw = s.readline()
            if raw:
                lines.append(raw.decode(errors="replace").rstrip())
    return "\n".join(lines)[:MAX_OUT]
