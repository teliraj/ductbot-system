import unittest
import os
import tempfile
import numpy as np

from ductbot_localization.video_localization import VideoLocalization, kabsch_se2, constrained_dtw

class TestVideoLocalization(unittest.TestCase):
    def setUp(self):
        self.engine = VideoLocalization(resample_spacing_m=0.02)

    def test_kabsch_alignment(self):
        """Tests 2D SE(2) rigid transform alignment."""
        # Create synthetic points
        A = np.array([[0, 0], [1, 0], [2, 0], [2, 1]], dtype=float)
        # Shift and rotate B by 90 degrees
        R_true = np.array([[0, -1], [1, 0]])
        t_true = np.array([5.0, 10.0])
        B = (R_true @ A.T).T + t_true
        
        R_calc, t_calc = kabsch_se2(A, B)
        B_aligned = (R_calc @ B.T).T + t_calc
        
        np.testing.assert_allclose(A, B_aligned, atol=1e-4)

    def test_dtw_alignment(self):
        """Tests constrained DTW alignment between two sequences."""
        N = 50
        # Sequence A: Straight with one 90 deg turn at step 25
        seq_A = np.zeros((N, 4))
        seq_A[:, 3] = np.linspace(0, 2.0, N)
        seq_A[25:, 2] = 90.0
        
        # Sequence B: Same trajectory but sampled unevenly (M=60)
        M = 60
        seq_B = np.zeros((M, 4))
        seq_B[:, 3] = np.linspace(0, 2.0, M)
        seq_B[30:, 2] = 90.0
        
        path, _, _, _ = constrained_dtw(seq_A, seq_B, w_xy=0.0, w_yaw=5.0, w_path=1.0)
        self.assertTrue(len(path) > 0)
        self.assertEqual(path[0], (0, 0))
        self.assertEqual(path[-1], (N - 1, M - 1))


if __name__ == '__main__':
    unittest.main()
