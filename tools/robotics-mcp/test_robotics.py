"""Tests for the guard and the PX4 server logic with a fake backend (no simulator, no MCP client needed)."""
import json, os, sys, tempfile, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import robotics_guard as g


class Fake:
    is_real = False
    def __init__(self): self.p = {"FW_THR_MAX": 1.0, "FW_THR_MIN": 0.0, "SIH_T_MAX": 6.0}
    def get_param(self, n):
        if n not in self.p: raise Exception("no such param")
        return self.p[n], 9
    def set_param(self, n, v): self.p[n] = float(v); return float(v)
    def status(self): return {"fake": True}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["ROBOTICS_MCP_DIR"] = self.tmp.name
    def tearDown(self): self.tmp.cleanup()


class GuardTest(Base):
    def test_read_always_allowed(self):
        self.assertEqual(g.check("s", "t", g.READ, "s:x", {})["decision"], "allow")

    def test_ask_mode_needs_approval_once(self):
        r = g.check("s", "t", g.WRITE, "s:x", {"a": 1})
        self.assertEqual(r["decision"], "confirm")
        self.assertEqual(g.check("s", "t", g.WRITE, "s:x", {"a": 1})["decision"], "confirm")  # still waiting
        self.assertTrue(g.approve(r["approval_id"]))
        self.assertEqual(g.check("s", "t", g.WRITE, "s:x", {"a": 1})["decision"], "allow")
        self.assertEqual(g.check("s", "t", g.WRITE, "s:x", {"a": 1})["decision"], "confirm")  # single use

    def test_approval_is_for_that_exact_call(self):
        r = g.check("s", "t", g.WRITE, "s:x", {"a": 1}); g.approve(r["approval_id"])
        self.assertEqual(g.check("s", "t", g.WRITE, "s:x", {"a": 2})["decision"], "confirm")

    def test_denied(self):
        r = g.check("s", "t", g.WRITE, "s:x", {}); g.approve(r["approval_id"], yes=False)
        self.assertEqual(g.check("s", "t", g.WRITE, "s:x", {})["decision"], "deny")

    def test_grant_allows_sim_write_and_physical(self):
        g.make_grant("s:x", 5)
        self.assertEqual(g.check("s", "t", g.WRITE, "s:x", {})["decision"], "allow")
        self.assertEqual(g.check("s", "t", g.PHYSICAL, "s:x", {})["decision"], "allow")

    def test_grant_other_scope_does_not_apply(self):
        g.make_grant("s:y", 5)
        self.assertEqual(g.check("s", "t", g.WRITE, "s:x", {})["decision"], "confirm")

    def test_real_hardware(self):
        g.make_grant("s:x", 5)
        self.assertEqual(g.check("s", "t", g.WRITE, "s:x", {}, real=True)["decision"], "confirm")
        g.make_grant("s:x", 5, allow_real=True)
        self.assertEqual(g.check("s", "t", g.WRITE, "s:x", {}, real=True)["decision"], "allow")
        self.assertEqual(g.check("s", "t", g.PHYSICAL, "s:x", {}, real=True)["decision"], "confirm")  # never lazy

    def test_expired_and_tampered_grant(self):
        g.make_grant("s:x", 5)
        grants = json.loads((g.state_dir() / "grants.json").read_text())
        grants[0]["expires"] = time.time() - 1
        (g.state_dir() / "grants.json").write_text(json.dumps(grants))
        self.assertEqual(g.check("s", "t", g.WRITE, "s:x", {})["decision"], "confirm")
        g.make_grant("s:x", 5)
        grants = json.loads((g.state_dir() / "grants.json").read_text())
        grants[0]["expires"] += 99999   # the model edits the file to extend the grant
        (g.state_dir() / "grants.json").write_text(json.dumps(grants))
        self.assertEqual(g.check("s", "t", g.WRITE, "s:x", {})["decision"], "confirm")

    def test_two_errors_suspend_lazy_mode(self):
        g.make_grant("s:x", 5)
        g.record_result(False); g.record_result(False)
        self.assertEqual(g.check("s", "t", g.WRITE, "s:x", {})["decision"], "confirm")
        g.set_suspended(False)
        self.assertEqual(g.check("s", "t", g.WRITE, "s:x", {})["decision"], "allow")

    def test_rate_limit(self):
        g.make_grant("s:x", 5)
        (g.state_dir() / "config.json").write_text(json.dumps({"rate_limit_per_min": 3}))
        res = [g.check("s", "t", g.WRITE, "s:x", {"i": i})["decision"] for i in range(5)]
        self.assertEqual(res, ["allow"] * 3 + ["deny"] * 2)

    def test_audit_written(self):
        g.check("s", "t", g.READ, "s:x", {})
        self.assertIn('"tool": "t"', (g.state_dir() / "audit.jsonl").read_text())


class Px4Test(Base):
    def setUp(self):
        super().setUp()
        import px4_server
        self.s = px4_server
        self.s.backend = Fake()

    def test_set_param_flow(self):
        out = json.loads(self.s.px4_set_param("FW_THR_MAX", 0))
        self.assertEqual(out["status"], "needs_confirmation")
        g.approve(out["approval_id"])
        self.assertEqual(json.loads(self.s.px4_set_param("FW_THR_MAX", 0))["new"], 0.0)

    def test_allowlist_and_range_beat_any_grant(self):
        g.make_grant("px4:params", 30)
        self.assertIn("not on the allowlist", self.s.px4_set_param("MAV_SYS_ID", 5))
        self.assertIn("outside the allowed range", self.s.px4_set_param("FW_THR_MAX", 5))
        self.assertEqual(self.s.backend.p["FW_THR_MAX"], 1.0)

    def test_inject_and_clear_restores_originals(self):
        g.make_grant("px4:params", 30)
        self.s.px4_inject_fault("engine_gazebo")
        self.assertEqual((self.s.backend.p["FW_THR_MAX"], self.s.backend.p["FW_THR_MIN"]), (0.0, 0.0))
        self.s.px4_inject_fault("engine_gazebo")        # twice must not overwrite the saved originals
        out = json.loads(self.s.px4_clear_faults())
        self.assertEqual(self.s.backend.p["FW_THR_MAX"], 1.0)
        self.assertEqual(out["restored"]["FW_THR_MAX"], 1.0)

    def test_real_hardware_detection(self):
        from px4_backend import Px4Backend
        self.assertFalse(Px4Backend("udpin:0.0.0.0:14540").is_real)
        self.assertTrue(Px4Backend("/dev/ttyACM0").is_real)
        self.assertTrue(Px4Backend("udpin:192.168.1.50:14550").is_real)

    def test_eval_path_must_stay_in_repo(self):
        os.environ["PX4_SIM_REPO"] = self.tmp.name
        self.assertIn("error", self.s.px4_run_eval("../../etc/passwd"))


if __name__ == "__main__":
    unittest.main()
