"""Prints the mcpServers block for claude_desktop_config.json for the servers in this folder.
It only prints; it never edits your config. Merge the printed entries into your existing "mcpServers" yourself.

  python make_config.py                      # servers run with the Python that runs this script (Windows or Linux)
  python make_config.py --wsl Ubuntu-PX4 --ros-distro jazzy     # run inside a WSL distro (needed for ROS 2 and PX4 in WSL)
"""
import argparse, json, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--wsl", help="WSL distro name; the servers then run inside it")
ap.add_argument("--wsl-dir", default="~/px4-fault-detection-sim/tools/robotics-mcp", help="folder of this code inside WSL")
ap.add_argument("--wsl-python", default="python3", help="python inside WSL that has mcp installed, e.g. ~/venv-sim/bin/python")
ap.add_argument("--ros-distro", default="jazzy")
ap.add_argument("--state-dir", default=None, help="ROBOTICS_MCP_DIR (grants and approvals); use the same one in your terminal")
ap.add_argument("--repo", default=None, help="PX4_SIM_REPO path (for px4_run_eval)")
a = ap.parse_args()
here = Path(__file__).resolve().parent
servers = {}
for name, f in (("px4", "px4_server.py"), ("arduino", "arduino_server.py"), ("robotstudio", "robotstudio_server.py"), ("ros2", "ros2_server.py")):
    if a.wsl:
        if name in ("robotstudio",):   # RobotStudio is Windows software: run that server on Windows
            continue
        pre = f"source /opt/ros/{a.ros_distro}/setup.bash && " if name == "ros2" else ""
        env = f"ROBOTICS_MCP_DIR={a.state_dir or '~/.robotics-mcp'} "
        servers[name] = {"command": "wsl.exe", "args": ["-d", a.wsl, "bash", "-lc", f"{pre}{env}{a.wsl_python} {a.wsl_dir}/{f}"]}
    else:
        e = {"ROBOTICS_MCP_DIR": a.state_dir} if a.state_dir else {}
        if name == "px4" and a.repo:
            e["PX4_SIM_REPO"] = a.repo
        servers[name] = {"command": sys.executable, "args": [str(here / f)], **({"env": e} if e else {})}
print(json.dumps({"mcpServers": servers}, indent=2))
