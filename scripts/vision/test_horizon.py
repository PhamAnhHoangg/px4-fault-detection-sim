import math, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from horizon import detect
from synth import make_frame


class HorizonTest(unittest.TestCase):
    def test_known_angles_and_heights(self):
        worst_r = worst_y = 0
        for i, (r, y) in enumerate([(0, .5), (10, .4), (-15, .6), (25, .5), (-30, .35), (5, .7), (40, .5), (-45, .45)]):
            d = detect(make_frame(r, y, seed=i))
            worst_r = max(worst_r, abs(d["roll_deg"] - r)); worst_y = max(worst_y, abs(d["horizon_y"] - y))
            self.assertGreater(d["quality"], 0.6, (r, y, d))
        self.assertLess(worst_r, 2.0)
        self.assertLess(worst_y, 0.03)

    def test_all_ground_and_all_sky(self):
        self.assertEqual(detect(make_frame(0, -0.2, clouds=False))["horizon_y"], -0.5)
        self.assertEqual(detect(make_frame(0, 1.3, clouds=False))["horizon_y"], 1.5)


if __name__ == "__main__":
    unittest.main()
