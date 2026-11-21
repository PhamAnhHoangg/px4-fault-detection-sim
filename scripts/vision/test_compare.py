"""Synthetic check that compare_alarms.py lines up the camera clock with the telemetry clock (offset 41.5 s)."""
import csv, subprocess, sys, tempfile, unittest
from pathlib import Path
import cv2, numpy as np
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from synth import make_frame


class CompareTest(unittest.TestCase):
    def test_alignment_and_order(self):
        d = Path(tempfile.mkdtemp()); fr = d / "frames"; fr.mkdir()
        OFF, CUT = 41.5, 25.0
        rng = np.random.default_rng(2)
        for i in range(0, 50 * 10):
            ft = i / 10
            drop = 0 if ft < CUT else min(.25, .012 * (ft - CUT) ** 1.5)
            cv2.imwrite(str(fr / f"{int(round((ft + OFF) * 1000))}.png"),
                        make_frame(12 + rng.normal(0, .5), .5 + rng.normal(0, .004) - drop, seed=i))
        with open(d / "tel.csv", "w", newline="") as f:
            w = csv.writer(f); w.writerow(["t", "alarm", "fault_sec", "boot_s"])
            for t in range(50):
                w.writerow([t, t >= 28, CUT, t + OFF])
        subprocess.run([sys.executable, str(HERE / "horizon.py"), str(fr), "--csv", str(d / "hz.csv")], check=True, capture_output=True)
        out = subprocess.run([sys.executable, str(HERE / "compare_alarms.py"), str(d / "tel.csv"), str(d / "hz.csv")],
                             check=True, capture_output=True, text=True).stdout
        print(out)
        self.assertIn("telemetry: t = 28 s, 3.0 s after the cut (alarm seconds before the cut: 0)", out)
        self.assertIn("vision:    t = 30 s, 5.0 s after the cut (alarm seconds before the cut: 0)", out)
        self.assertIn("first: telemetry", out)


if __name__ == "__main__":
    unittest.main()
