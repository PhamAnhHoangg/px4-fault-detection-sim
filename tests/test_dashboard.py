import json, sys, threading, time, unittest, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "live"))
import dashboard


class DashboardTest(unittest.TestCase):
    def test_state_and_stream(self):
        hub = dashboard.Hub(threshold=0.5, mode="live")
        srv = dashboard.serve(hub, 0, "127.0.0.1")
        port = srv.server_address[1]
        hub.push_row({"t": 40, "prob": 0.1, "raw": 0, "alarm": 0, "alt_error": 0.2,
                      "hud_altitude": 100.0, "vel_lin_z": 0.0})
        hub.push_cut(25.0)
        state = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/state.json", timeout=5))
        self.assertEqual(len(state["rows"]), 1)
        self.assertEqual(state["cut_t"], 25.0)
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5).read()
        self.assertIn(b"EventSource", page)


if __name__ == "__main__":
    unittest.main()
