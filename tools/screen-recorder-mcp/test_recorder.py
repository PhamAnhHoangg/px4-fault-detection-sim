"""Tests for recorder.py. Run: python -m unittest -v test_recorder
The recording test needs ffmpeg and a display (on Linux: xvfb-run -a python -m unittest -v test_recorder)."""
import os, shutil, subprocess, sys, tempfile, time, unittest
from unittest import mock
from pathlib import Path

os.environ["SCREEN_RECORDER_DIR"] = tempfile.mkdtemp()
import recorder as r


class Parsing(unittest.TestCase):
    def test_targets(self):
        self.assertEqual(r.parse_target("screen"), ("screen", None))
        self.assertEqual(r.parse_target(""), ("screen", None))
        self.assertEqual(r.parse_target("window: Gazebo"), ("window", "Gazebo"))
        k, rect = r.parse_target("region:10,20,300,200")
        self.assertEqual((k, rect.x, rect.y, rect.w, rect.h), ("region", 10, 20, 300, 200))

    def test_bad_targets(self):
        for bad in ("window:", "region:1,2,3", "region:a,b,c,d", "region:0,0,4,4", "desktop"):
            with self.assertRaises(r.RecorderError, msg=bad):
                r.parse_target(bad)

    def test_even_and_names(self):
        e = r.Rect(0, 0, 101, 53).even()
        self.assertEqual((e.w, e.h), (100, 52))
        self.assertEqual(r.safe_name("../../evil name!"), "evil_name")
        self.assertTrue(r.safe_name("").startswith("rec-"))

    def test_limits(self):
        with self.assertRaises(r.RecorderError):
            r.start_recording("screen", fps=0)
        with self.assertRaises(r.RecorderError):
            r.start_recording("screen", max_seconds=999999)


class Commands(unittest.TestCase):
    def test_windows_region(self):
        c = r.build_record_cmd("ffmpeg", r.Rect(-1920, 0, 1280, 720), 30, "o.mp4", platform="win32")
        s = " ".join(c)
        self.assertIn("-f gdigrab", s); self.assertIn("-offset_x -1920 -offset_y 0 -video_size 1280x720", s)
        self.assertTrue(s.endswith("-pix_fmt yuv420p o.mp4"))

    def test_windows_screen_has_no_offsets(self):
        s = " ".join(r.build_record_cmd("ffmpeg", None, 30, "o.mp4", platform="win32"))
        self.assertNotIn("-offset_x", s); self.assertIn("-i desktop", s)

    def test_linux_region(self):
        with mock.patch.dict(os.environ, {"DISPLAY": ":7"}):
            s = " ".join(r.build_shot_cmd("ffmpeg", r.Rect(5, 6, 200, 100), "o.png", platform="linux"))
        self.assertIn("-f x11grab", s); self.assertIn("-i :7+5,6", s); self.assertIn("-frames:v 1", s)


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("ffmpeg") and os.environ.get("DISPLAY"),
                     "needs Linux, ffmpeg and a display")
class RealRecording(unittest.TestCase):
    def test_record_and_stop(self):
        info = r.start_recording("region:0,0,320,240", fps=10, name="t1", max_seconds=30)
        time.sleep(2.0)
        self.assertEqual(len(r.status()), 1)
        done = r.stop_recording()
        self.assertTrue(done["ok"], done)
        d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", done["file"]],
                           capture_output=True, text=True).stdout.strip()
        self.assertGreater(float(d), 1.0)
        self.assertEqual(r.status(), [])

    def test_screenshot(self):
        p = r.screenshot("region:0,0,200,100", "s1")
        self.assertTrue(p.exists() and p.stat().st_size > 0)

    def test_auto_stop(self):
        r.start_recording("region:0,0,160,120", fps=5, name="auto", max_seconds=1)
        time.sleep(4)
        self.assertEqual(r.status(), [])


if __name__ == "__main__":
    unittest.main()
