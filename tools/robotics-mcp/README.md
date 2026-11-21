# robotics-mcp

MCP servers that let Claude work inside robotics tools, with a shared safety layer that you control. Servers so far: PX4 (simulation, tested against a real SIH flight), ROS 2, Arduino and ABB RobotStudio (read only). The last three were tested only against stand-ins, see the end of this file.

## Two modes

Every tool has a tier: read, write (reversible) or physical (moves something or cannot be undone).

| | Read | Write | Physical |
| --- | --- | --- | --- |
| Ask mode (default) | runs | needs your approval for that exact call | needs your approval for that exact call |
| Lazy mode (you grant a scope for N minutes) | runs | runs | runs on a simulator; real hardware still asks every time |

Lazy mode and approvals are made by you, in your own terminal, never by a tool call:

```
python robotics_guard.py grant px4:params --minutes 30    # lazy mode, simulators only
python robotics_guard.py grant px4:params --minutes 30 --real   # also WRITE on real hardware
python robotics_guard.py pending                           # calls waiting for you
python robotics_guard.py approve d328ff3c                  # one call, once, valid 10 minutes
python robotics_guard.py status | revoke | resume | log
```

When a tool needs approval it returns `needs_confirmation` with an id and the command to run. After you approve, the same call goes through once.

Limits a grant cannot widen: the parameter allowlist and ranges in `config.json` (see `config.example.json`; edit it yourself), a rate limit (20 changes per minute), and "real hardware never lazy for physical actions". Two errors in a row inside a grant drop back to ask mode until you run `resume`. Grants are signed; editing the grant file to extend it makes it invalid. Every call is written to `audit.jsonl` in `~/.robotics-mcp` (or `ROBOTICS_MCP_DIR`).

Honest limits: this protects against instructions hidden in tool output (a log line, a topic, a serial line) and against the model asking for more than you allowed. It does not protect against another program running as your user that can read your files. A connection is treated as real hardware unless it is a UDP or TCP address on this machine (override with `real_hardware` in `config.json`).

## Quick routine (one terminal)

```
scripts/sim.sh start                 # PX4 + Gazebo in the background, fault parameters reset (sihsim_airplane for SIH)
claude                               # in ~/px4-fault-detection-sim, with the px4 server added
! python tools/robotics-mcp/robotics_guard.py grant px4:params --minutes 30    # optional lazy mode, typed by you
! python tools/robotics-mcp/robotics_guard.py approve <id>                     # or approve single calls
scripts/sim.sh stop
```

In Claude Code a line starting with `!` is a command you type yourself, so an approval made that way is still yours. If Claude Code ever asks to run `robotics_guard.py approve` or `grant` on its own, answer no.

## Without AI: px4ctl.py

The same functions as a normal command line. A change asks you y/N in the terminal (or `--yes`); the allowlist, ranges, rate limit and audit log still apply.

```
python px4ctl.py status
python px4ctl.py get FW_THR_MAX
python px4ctl.py inject engine_gazebo
python px4ctl.py clear
python px4ctl.py eval results/gazebo/table_gz.csv
```

## PX4 server tools

`px4_status`, `px4_get_param` (read); `px4_set_param` (allowlisted, range checked), `px4_inject_fault` (`engine_gazebo`, `engine_sih`, `elevator`; originals are saved), `px4_clear_faults` (write); `px4_run_eval` (runs `scripts/detect_eval.py` on a table inside the repo); `guard_status`.

## ROS 2 server tools

Read: `ros2_list_nodes`, `ros2_list_topics`, `ros2_topic_info`, `ros2_echo_once` (time limit 20 s), `ros2_list_services`, `ros2_list_params`, `ros2_get_param`, `ros2_bag_info` (only inside `ros2.bag_dir`), `ros2_launch_log`, `ros2_stop` (stopping is always allowed). Write (scope `ros2:write`): `ros2_set_param` and `ros2_call_service`, both only for the node/parameter pairs and services you list in `config.json`. Physical (scope `ros2:motion`): `ros2_publish_once` (one message, only to listed topics) and `ros2_launch` (only listed package and launch file pairs, stops itself after `launch_max_seconds`).

ROS 2 cannot tell a simulation from a robot, so `ros2.real_hardware` is true by default: publishing and launching then need your approval every time, even in lazy mode. Set it to false in `config.json` only for a simulation. Everything coming back from the system (topic messages, logs) is returned in an `untrusted_output` field, because a message can contain text meant to trick the model; the server instructions tell Claude not to follow it. Names are validated (no leading dash, no spaces or shell characters), no shell is used, output is cut at 4000 characters, and messages must be a YAML mapping starting with `{`.

The server calls the `ros2` command line tool, so start it from a shell where ROS 2 is sourced, for example in Claude Desktop on Windows with WSL:

```
"ros2": { "command": "wsl.exe", "args": ["bash", "-lc", "source /opt/ros/jazzy/setup.bash && python3 ~/robotics-mcp/ros2_server.py"] }
```

(replace `jazzy` with your distro, and give the WSL environment `ROBOTICS_MCP_DIR` the same folder you use for grants, otherwise your `grant` and `approve` commands and the server look at different folders).

## Arduino server tools

Free: `ard_list_boards`, `ard_read_sketch`, `ard_compile`, `ard_serial_read` (max 30 s, port must match `/dev/tty...` or `COMn`, and `arduino.ports_allow` if you set it). Needs permission (scope `arduino:write`): `ard_write_sketch`, only inside `arduino.sketches_dir`, max 100 KB, keeps the old file as `.bak`. Upload (`ard_upload`) changes a real board, so it needs your approval for that exact call every time, even in lazy mode. Needs `arduino-cli` on PATH and `pyserial` for the serial reader. Opening a serial port resets some boards (Uno, Nano). Compiler messages and serial lines come back as `untrusted_output`.

## RobotStudio / ABB controller server tools (read only)

Uses Robot Web Services over GET requests only; it cannot start the program, move the robot, set a signal or change RAPID (a write version would be a separate step, ask mode first). Tools: `rs_controller_state`, `rs_operation_mode`, `rs_execution_state`, `rs_list_signals`, `rs_get_signal`, `rs_get_rapid_variable`, `rs_joint_target`, `rs_robot_target`, and `rs_get` for exploring any `/rw/...` path. Config: `robotstudio.base_url`, `version` (1 = IRC5 or RobotStudio with RobotWare 6, HTTP and digest login; 2 = OmniCore, HTTPS and basic login), `verify_tls`, `robot`, `task`. Credentials come from the environment (`RWS_USER`, `RWS_PASSWORD`); the defaults are ABB's published `Default User` / `robotics`, which belong on a virtual controller only. On a real controller set your own user with read rights. RobotStudio runs on Windows, so run this server on Windows (or point `base_url` at the Windows machine).

## Install

```
pip install -r requirements.txt
```

`python make_config.py` (add `--wsl <distro>` for WSL) prints ready-made entries for `claude_desktop_config.json`; it never edits the file. By hand, for PX4 alone, with the path of your own copy:

```
"mcpServers": { "px4": { "command": "python", "args": ["E:/tools/robotics-mcp/px4_server.py"],
  "env": { "PX4_CONNECTION": "udpin:0.0.0.0:14540", "PX4_SIM_REPO": "E:/px4-fault-detection-sim" } } }
```

If PX4 runs in WSL2 and the server on Windows, the UDP port may not be reachable; running the server inside the same WSL distro is the safer first try. Only one program can hold port 14540, so stop `live_detector.py` before using the server, or use another port.

## Tested

Unit tests (`python test_robotics.py`, 16 tests, no simulator needed): approval flow, single use, exact-call match, deny, grant scope, expiry, tampered grant, real hardware rule, error fallback, rate limit, allowlist beats grant, fault inject and clear restore the originals. End to end in the sandbox: the server started as a real MCP stdio process, a client listed the tools and ran status, parameter read, fault injection with approval, a denied non-allowlisted parameter, lazy-mode clear, and the evaluation on a PX4 SIH simulation (3 repeated runs). Tested by the owner on 2026-11-21 in Claude Code on WSL2 with Gazebo rc_cessna: status and parameter reads, `engine_gazebo` inject after approval, single-use approval, clear restored `FW_THR_MAX` to 1.0 (checked in pxh). `scripts/sim.sh` and `px4ctl.py` were tested in the sandbox with SIH only. Not tested: Claude Desktop, real hardware.

Arduino server: 5 unit tests (`python test_arduino.py`) against `fake_arduino_cli.py` and a fake serial reader. Not tested: real `arduino-cli` output, a real board, pyserial. RobotStudio server: 8 unit tests (`python test_robotstudio.py`) against a fake RWS HTTP server (digest and basic login, only GET sent, path checks, output limits). The resource paths follow ABB's published API but were not checked against a real controller: `ctrlstate` (version 1) is from memory, and the JSON shape is returned raw, not parsed. Use `rs_get` to explore if a tool returns 404.

ROS 2 server: 10 unit tests (`python test_ros2.py`) run against `fake_ros2.py`, a stand-in that prints what the real tool prints for the commands used, plus one MCP stdio run (tool list, a read, a publish that correctly asked for approval). ROS 2 itself was not installed where this was written, so real output formats, `ros2 launch` behaviour and parameter value parsing are untested. Please run `ros2_list_topics` and `ros2_echo_once` on your machine first and tell me what breaks.
