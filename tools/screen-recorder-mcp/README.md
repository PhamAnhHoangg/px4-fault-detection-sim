# screen-recorder MCP

A small MCP server that lets Claude take screenshots and record your screen, one window or a region to an mp4.
It runs on your own computer, writes only into one folder, and never clicks or types.

Status: the recording code and the MCP protocol are tested on Linux (ffmpeg + a virtual screen). The Windows part
(`gdigrab`, window listing with `ctypes`) is written but **not yet run on a real Windows desktop**. Capturing WSLg
windows (Gazebo, the plot window) by title is not verified; if it fails, record the screen or a region instead.

## Tools

| Tool | What it does |
| --- | --- |
| `list_windows` | Visible windows with title and position (Windows only) |
| `screenshot` | PNG of `screen`, `window:<part of title>` or `region:x,y,w,h`, returned so Claude can see it |
| `start_recording` | Starts an mp4. Same `target` values, `fps` (1 to 60), `name`, `max_seconds` (default 600, auto-stop) |
| `stop_recording` | Finishes the mp4 and returns its path |
| `recording_status`, `list_recordings` | What is running, and the newest files |

A window is recorded as the rectangle it has when you start, so do not move it. Anything that covers it is recorded
too. For two windows side by side, record the screen or a region that contains both.

## Install on Windows

1. ffmpeg: `winget install Gyan.FFmpeg`, then open a new terminal and check `ffmpeg -version`.
2. Python 3.10 or newer with the MCP package: `pip install "mcp>=2,<3"`.
3. Copy this folder to a Windows folder, for example from PowerShell:
   `Copy-Item -Recurse \\wsl$\PX4-Sim\home\hoang\px4-fault-detection-sim\tools\screen-recorder-mcp E:\tools\screen-recorder-mcp`
4. Add it to the Claude Desktop config (`%APPDATA%\Claude\claude_desktop_config.json`), then restart Claude Desktop:

```json
{
  "mcpServers": {
    "screen-recorder": {
      "command": "python",
      "args": ["E:\\tools\\screen-recorder-mcp\\server.py"],
      "env": { "SCREEN_RECORDER_DIR": "E:\\recordings" }
    }
  }
}
```

If `python` is not the one where you installed `mcp`, put the full path to that `python.exe` in `command`.
If ffmpeg is not on PATH, add `"FFMPEG_PATH": "C:\\path\\to\\ffmpeg.exe"` to `env`.

## Things to know

- Recording captures everything visible in the chosen area, including passwords or messages that show up in it. Claude
  is told to say what it records before it starts.
- Files only go into `SCREEN_RECORDER_DIR` (default `Videos\claude-recordings`). File names are cleaned.
- Recordings stop by themselves after `max_seconds` (at most 3600) and when the server exits.

## Tests

```
python -m unittest -v test_recorder                                   # command lines, parsing, limits
xvfb-run -a python -m unittest -v test_recorder                       # Linux only: real recording and screenshots
```
