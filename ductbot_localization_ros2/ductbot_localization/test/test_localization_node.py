import unittest
import math
import numpy as np

from ductbot_localization.localization_engine import LocalizationEngine
from ductbot_localization.checkpoint_logger import CheckpointLogger

class TestDuctBotLocalization(unittest.TestCase):
    def setUp(self):
        self.engine = LocalizationEngine(
            sample_rate_hz=100.0,
            wheel_base=0.260,
            front_offset=0.145,
            ticks_per_meter_fwd=15055.0,
            ticks_per_meter_rev=16260.0,
            backlash_ticks=450
        )

    def test_straight_run_254(self):
        """Simulates 2.54m straight run matching run_254_test.py from fresh_repo."""
        target_dist_m = 2.54
        ticks_per_m = 15055.0
        total_ticks = int(target_dist_m * ticks_per_m)
        steps = 500
        ticks_per_step = total_ticks / steps

        enc = [0.0, 0.0]
        res = None
        for _ in range(steps):
            enc[0] += ticks_per_step
            enc[1] += ticks_per_step
            res = self.engine.update(
                accel=[0.0, 0.0, 1.0],
                gyro=[0.0, 0.0, 0.0],
                enc=[int(enc[0]), int(enc[1])],
                ang=[0.0, 0.0, 90.0] # Physical 90 deg -> Engine 0 deg
            )

        self.assertIsNotNone(res)
        dist_m = res['total_distance_cm'] / 100.0
        # Tolerating small backlash / discretization difference (< 4cm)
        self.assertAlmostEqual(dist_m, target_dist_m, delta=0.05)
        self.assertAlmostEqual(res['euler_deg'][2], 0.0, delta=0.1)

    def test_point_turn(self):
        """Verifies 90 degree point turn."""
        enc = [0, 0]
        for i in range(50):
            enc[0] += 50
            enc[1] -= 50
            yaw_ang = 90.0 - (90.0 * (i + 1) / 50.0)
            res = self.engine.update(
                accel=[0.0, 0.0, 1.0],
                gyro=[0.0, 0.0, -1.5],
                enc=enc.copy(),
                ang=[0.0, 0.0, yaw_ang]
            )

        self.assertTrue(res['is_slipping']) # Spot turn ratio > 2.0
        self.assertAlmostEqual(res['euler_deg'][2], 270.0, delta=1.0)


if __name__ == '__main__':
    unittest.main()
