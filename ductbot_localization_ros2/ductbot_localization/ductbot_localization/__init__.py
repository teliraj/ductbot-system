"""Duct Bot ROS 2 Localization and Video Comparison Package.

Ports proven kinematics, IMU fusion, front face offset tracking,
10mm checkpoint logging, and DTW video localization from fresh_repo into ROS 2.
"""

from .localization_engine import LocalizationEngine
from .checkpoint_logger import CheckpointLogger
from .video_localization import VideoLocalization, kabsch_se2, constrained_dtw

__all__ = [
    'LocalizationEngine', 
    'CheckpointLogger',
    'VideoLocalization',
    'kabsch_se2',
    'constrained_dtw'
]
