# robotics-mcp

MCP servers that let Claude work inside robotics tools, with a shared safety layer that you control. Servers so far: PX4 (simulation, tested against a real SIH flight) and ROS 2 (tested only against a stand-in `ros2`, see below). Planned on the same layer: Arduino (`arduino-cli`), ABB RobotStudio (read only first).

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

## Install

```
pip install -r requirements.txt
```

Claude Desktop (`claude_desktop_config.json`), with the path of your own copy:

```
"mcpServers": { "px4": { "command": "python", "args": ["E:/tools/robotics-mcp/px4_server.py"],
  "env": { "PX4_CONNECTION": "udpin:0.0.0.0:14540", "PX4_SIM_REPO": "E:/px4-fault-detection-sim" } } }
```

If PX4 runs in WSL2 and the server on Windows, the UDP port may not be reachable; running the server inside the same WSL distro is the safer first try. Only one program can hold port 14540, so stop `live_detector.py` before using the server, or use another port.

## Tested

Unit tests (`python test_robotics.py`, 16 tests, no simulator needed): approval flow, single use, exact-call match, deny, grant scope, expiry, tampered grant, real hardware rule, error fallback, rate limit, allowlist beats grant, fault inject and clear restore the originals. End to end in the sandbox: the server started as a real MCP stdio process, a client listed the tools and ran status, parameter read, fault injection with approval, a denied non-allowlisted parameter, lazy-mode clear, and the evaluation on a PX4 SIH simulation (3 repeated runs). Not tested: Gazebo, Windows, Claude Desktop itself, real hardware.

ROS 2 server: 10 unit tests (`python test_ros2.py`) run against `fake_ros2.py`, a stand-in that prints what the real tool prints for the commands used, plus one MCP stdio run (tool list, a read, a publish that correctly asked for approval). ROS 2 itself was not installed where this was written, so real output formats, `ros2 launch` behaviour and parameter value parsing are untested. Please run `ros2_list_topics` and `ros2_echo_once` on your machine first and tell me what breaks.
