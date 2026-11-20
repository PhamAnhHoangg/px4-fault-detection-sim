# robotics-mcp

MCP servers that let Claude work inside robotics tools, with a shared safety layer that you control. First server: PX4 (simulation). Planned on the same layer: ROS 2, Arduino (`arduino-cli`), ABB RobotStudio (read only first). Only PX4 exists today.

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
