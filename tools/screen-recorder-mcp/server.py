"""Screen-recorder MCP server (stdio). Gives Claude tools to look at, screenshot and record your screen or one window.
Runs on your own computer; files go to SCREEN_RECORDER_DIR (default: Videos/claude-recordings).
Start it from Claude Desktop (see README.md). It never writes anywhere else and never clicks or types."""
import json
import recorder
from mcp.server.mcpserver import MCPServer, Image

mcp = MCPServer(
    "screen-recorder",
    instructions="Record or screenshot the user's screen, a window or a region. Recording captures everything visible in "
                 "that area, so tell the user what is being recorded before you start and stop when done.",
)


def _run(fn, *a, **k):
    try:
        return json.dumps(fn(*a, **k), indent=2)
    except recorder.RecorderError as e:
        return f"error: {e}"


@mcp.tool()
def list_windows() -> str:
    """List visible windows (title and position). Windows only. Use a part of a title in target='window:<title>'."""
    return _run(recorder.list_windows)


@mcp.tool()
def screenshot(target: str = "screen", name: str = "") -> Image | str:
    """Take a screenshot and return it so you can see it. target: 'screen', 'window:<part of title>' or 'region:x,y,w,h'.
    The PNG is also saved in the recordings folder."""
    try:
        path = recorder.screenshot(target, name or None)
    except recorder.RecorderError as e:
        return f"error: {e}"
    return Image(path=str(path))


@mcp.tool()
def start_recording(target: str = "screen", fps: int = 30, name: str = "", max_seconds: int = 600) -> str:
    """Start recording to an mp4. target: 'screen', 'window:<part of title>' or 'region:x,y,w,h'. A window is recorded as the
    rectangle it has now, so it must not be moved; anything that covers it is recorded too. Stops by itself after max_seconds."""
    return _run(recorder.start_recording, target, fps, name or None, max_seconds)


@mcp.tool()
def stop_recording(id: str = "") -> str:
    """Stop a recording and return the file path. id is optional when only one recording is running."""
    return _run(recorder.stop_recording, id or None)


@mcp.tool()
def recording_status() -> str:
    """List the recordings that are running now."""
    return _run(recorder.status)


@mcp.tool()
def list_recordings() -> str:
    """List the newest mp4 files in the recordings folder."""
    return _run(recorder.list_recordings)


if __name__ == "__main__":
    mcp.run()
