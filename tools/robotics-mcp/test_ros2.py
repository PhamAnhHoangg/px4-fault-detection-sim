"""Tests for the ROS 2 server using fake_ros2.py instead of a real ROS 2 (no ROS 2 needed)."""
import json, os, sys, tempfile, time, unittest
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import robotics_guard as g


class Base(unittest.TestCase):
    CFG = {"ros2": {"param_allow": {"/talker": ["max_speed"]}, "service_allow": ["/reset"],
                    "topic_pub_allow": ["/cmd_vel"], "launch_allow": [["demo", "demo.launch.py"]],
                    "real_hardware": True, "launch_max_seconds": 600}}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["ROBOTICS_MCP_DIR"] = self.tmp.name
        os.environ["ROS2_BIN"] = str(HERE / "fake_ros2.py")
        (Path(self.tmp.name) / "config.json").write_text(json.dumps(self.CFG))
        import ros2_server
        self.s = ros2_server

    def tearDown(self):
        for p in list(self.s._procs.values()):
            if p["popen"].poll() is None:
                p["popen"].kill()
        self.tmp.cleanup()


class Ros2Test(Base):
    def test_reads_work_without_approval(self):
        out = json.loads(self.s.ros2_list_topics())
        self.assertIn("/cmd_vel", out["untrusted_output"])
        self.assertIn("/talker", json.loads(self.s.ros2_list_nodes())["untrusted_output"])
        self.assertIn("hello", json.loads(self.s.ros2_echo_once("/chatter"))["untrusted_output"])

    def test_injected_text_stays_inside_untrusted_field(self):
        out = json.loads(self.s.ros2_echo_once("/evil"))
        self.assertIn("IGNORE PREVIOUS", out["untrusted_output"])
        self.assertEqual(set(out), {"exit_code", "untrusted_output"})
        # and nothing was changed or queued by reading it
        self.assertEqual(g._read("pending.json", {}), {})

    def test_timeout_and_size_limit(self):
        t0 = time.time()
        out = json.loads(self.s.ros2_echo_once("/silent", timeout_s=1))
        self.assertLess(time.time() - t0, 5)
        self.assertEqual(out["exit_code"], 124)
        self.assertIn("cut at", json.loads(self.s.ros2_echo_once("/big"))["untrusted_output"])

    def test_bad_names_rejected(self):
        for bad in ["--help", "/a b", "/a;rm -rf", "", "$(id)"]:
            self.assertTrue(self.s.ros2_topic_info(bad).startswith("error: invalid"), bad)

    def test_set_param_allowlist_and_approval(self):
        self.assertIn("not on the allowlist", self.s.ros2_set_param("/talker", "other", "1"))
        first = json.loads(self.s.ros2_set_param("/talker", "max_speed", "0.5"))
        self.assertEqual(first["status"], "needs_confirmation")
        g.approve(first["approval_id"])
        self.assertEqual(json.loads(self.s.ros2_set_param("/talker", "max_speed", "0.5"))["exit_code"], 0)

    def test_service_allowlist(self):
        g.make_grant("ros2:write", 5, allow_real=True)
        self.assertIn("not on the allowlist", self.s.ros2_call_service("/other", "std_srvs/srv/Trigger"))
        self.assertEqual(json.loads(self.s.ros2_call_service("/reset", "std_srvs/srv/Trigger"))["exit_code"], 0)
        self.assertIn("must be a YAML mapping", self.s.ros2_call_service("/reset", "std_srvs/srv/Trigger", "--evil"))

    def test_publish_is_never_lazy_on_real_hardware(self):
        g.make_grant("ros2:motion", 30, allow_real=True)
        out = json.loads(self.s.ros2_publish_once("/cmd_vel", "geometry_msgs/msg/Twist", "{linear: {x: 0.1}}"))
        self.assertEqual(out["status"], "needs_confirmation")
        g.approve(out["approval_id"])
        ok = json.loads(self.s.ros2_publish_once("/cmd_vel", "geometry_msgs/msg/Twist", "{linear: {x: 0.1}}"))
        self.assertEqual(ok["exit_code"], 0)
        self.assertIn("not on the allowlist", self.s.ros2_publish_once("/other", "geometry_msgs/msg/Twist", "{}"))

    def test_publish_lazy_when_declared_simulation(self):
        cfg = json.loads(json.dumps(self.CFG)); cfg["ros2"]["real_hardware"] = False
        (Path(self.tmp.name) / "config.json").write_text(json.dumps(cfg))
        g.make_grant("ros2:motion", 30)
        out = json.loads(self.s.ros2_publish_once("/cmd_vel", "geometry_msgs/msg/Twist", "{linear: {x: 0.1}}"))
        self.assertEqual(out["exit_code"], 0)

    def test_launch_log_stop(self):
        cfg = json.loads(json.dumps(self.CFG)); cfg["ros2"]["real_hardware"] = False
        (Path(self.tmp.name) / "config.json").write_text(json.dumps(cfg))
        g.make_grant("ros2:motion", 30)
        self.assertIn("not on the allowlist", self.s.ros2_launch("demo", "evil.launch.py"))
        out = json.loads(self.s.ros2_launch("demo", "demo.launch.py", "use_sim:=true"))
        time.sleep(1)
        log = json.loads(self.s.ros2_launch_log(out["id"]))
        self.assertTrue(log["running"])
        self.assertIn("launch started", log["untrusted_output"])
        self.assertFalse(json.loads(self.s.ros2_stop(out["id"]))["running"])
        self.assertFalse(json.loads(self.s.ros2_launch_log(out["id"]))["running"])

    def test_bag_must_stay_in_bag_dir(self):
        cfg = json.loads(json.dumps(self.CFG)); cfg["ros2"]["bag_dir"] = self.tmp.name
        (Path(self.tmp.name) / "config.json").write_text(json.dumps(cfg))
        (Path(self.tmp.name) / "demo").mkdir()
        self.assertIn("Duration", json.loads(self.s.ros2_bag_info("demo"))["untrusted_output"])
        self.assertIn("error", self.s.ros2_bag_info("../../etc"))


if __name__ == "__main__":
    unittest.main()
