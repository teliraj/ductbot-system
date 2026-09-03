import numpy as np
import math
try:
    from scipy.spatial.transform import Rotation as R
except Exception:
    class _FallbackRotation:
        def __init__(self, mat):
            self._mat = mat

        @classmethod
        def from_euler(cls, seq, angles, degrees=False):
            if degrees:
                angles = np.radians(angles)
            r, p, y = angles
            Rx = np.array([[1, 0, 0], [0, np.cos(r), -np.sin(r)], [0, np.sin(r), np.cos(r)]])
            Ry = np.array([[np.cos(p), 0, np.sin(p)], [0, 1, 0], [-np.sin(p), 0, np.cos(p)]])
            Rz = np.array([[np.cos(y), -np.sin(y), 0], [np.sin(y), np.cos(y), 0], [0, 0, 1]])
            return cls(Rz @ Ry @ Rx)

        def as_matrix(self):
            return self._mat

    R = _FallbackRotation

class LocalizationEngine:
    """
    LocalizationEngine is the core mathematical processor for the Duct Bot.
    
    Ported directly from fresh_repo/RPi_Localization_Logger/localization_engine.py.
    
    It takes raw sensor readings (Accelerometer, Gyroscope, Encoders, and Hardware Euler Angles)
    and turns them into a true 3D position (X, Y in meters) and tracking orientation (Yaw).
    
    Kinematics Features:
    - Asymmetric forward/reverse ticks_per_meter calibration
    - Mechanical backlash filtering (track slack compensation)
    - Swept circular arc integration for curved trajectory tracking
    - Front face offset compensation (camera position at front edge)
    - Centrifugal & tangential lever-arm IMU compensation
    """
    def __init__(self, 
                 sample_rate_hz=100.0, 
                 wheel_base=0.260, 
                 front_offset=0.145,
                 ticks_per_meter_fwd=15055.0, 
                 ticks_per_meter_rev=16260.0,
                 backlash_ticks=450):
        # Time Step details. If data comes in at 100Hz, dt is 0.01 seconds.
        self.dt = 1.0 / sample_rate_hz
        
        # Robot physical geometry
        self.wheel_base = wheel_base          # Track center-to-center is 26cm (0.260m)
        self.front_offset = front_offset      # Distance from center of rotation to front edge (0.145m)
        
        # Calibrated track scales
        self.ticks_per_meter_fwd = ticks_per_meter_fwd
        self.ticks_per_meter_rev = ticks_per_meter_rev
        self.BACKLASH_TICKS = backlash_ticks
        
        # Current Tracking State (X, Y, Z coordinates in meters)
        self.position = np.zeros(3)             
        
        # Overall accumulated distance tracker (Odometer) in meters
        self.total_distance = 0.0               
        
        # Hardware calibration offsets
        self.accel_bias = np.zeros(3)
        self.gyro_bias = np.zeros(3)
        
        # Mount rotation matrix
        self.mount_rotation = np.eye(3)
        
        # Reference gravity vector (BNO085 outputs in standard 'g' units)
        self.gravity_vector = np.array([0.0, 0.0, 1.0])
        
        # Backlash & kinematic state
        self.track_dir = [0, 0] # 1=Fwd, -1=Rev
        self.backlash_remaining = [0, 0] # Ticks remaining to ignore
        self.prev_enc = None
        self.prev_gyro = None
        self.filtered_yaw = 0.0
        self.position_initialized = False

    def reset(self):
        """Resets the tracking state back to origin (0, 0, 0) and zero heading."""
        self.position = np.zeros(3)
        self.total_distance = 0.0
        self.prev_enc = None
        self.prev_gyro = None
        self.track_dir = [0, 0]
        self.backlash_remaining = [0, 0]
        self.position_initialized = False
        self.filtered_yaw = 0.0

    def calibrate(self, accel_samples, gyro_samples):
        """
        Calculates simple static bias offsets.
        The bot MUST be perfectly still and flat while running this function!
        """
        self.accel_bias = np.mean(accel_samples, axis=0) - self.gravity_vector
        self.gyro_bias = np.mean(gyro_samples, axis=0)

    def update(self, accel, gyro, enc, ang):
        """
        The main processing function. Call this every time a new sensor packet arrives.
        
        Inputs:
        - accel: [x, y, z] Accelerometer data in 'g' units (Gravity).
        - gyro:  [x, y, z] Angular velocity in radians/second.
        - enc:   [left, right] Raw integer ticks from the wheel encoders.
        - ang:   [roll, pitch, yaw] Orientation degrees from the hardware IMU fusion.
        
        Returns: 
        - A dictionary containing updated positions, yaw angles, acceleration, and distance.
        """
        # -------------------------------------------------------------
        # STEP 1: SENSOR CALIBRATION AND ROTATION ALIGNMENT
        # -------------------------------------------------------------
        accel_cal = np.array(accel) - self.accel_bias
        accel_cal = self.mount_rotation @ accel_cal
        gyro = self.mount_rotation @ (np.array(gyro) - self.gyro_bias)
        
        euler_deg = np.array(ang, dtype=float)
        
        # Adjust Yaw: shift by 90 degrees so physical "Zero degrees" matches mathematical X/Y
        euler_deg[2] -= 90.0
        euler_deg[2] = euler_deg[2] % 360.0
        
        # Generate rotation matrix from Roll/Pitch/Yaw
        r_rot = R.from_euler('xyz', euler_deg, degrees=True)
        rot_matrix = r_rot.as_matrix()
        
        # -------------------------------------------------------------
        # STEP 2: LEVER ARM COMPENSATION (ADVANCED IMU MATH)
        # -------------------------------------------------------------
        omega = np.array(gyro)
        if self.prev_gyro is None:
            self.prev_gyro = np.zeros(3)
            
        alpha_ang = (omega - self.prev_gyro) / self.dt
        self.prev_gyro = omega
        
        # IMU is mounted at geometric center
        r_bot_wrt_imu = np.array([0.0, 0.0, 0.0])
        
        a_imu_local_ms2 = accel_cal * 9.81
        a_center_local_ms2 = a_imu_local_ms2 + np.cross(alpha_ang, r_bot_wrt_imu) + np.cross(omega, np.cross(omega, r_bot_wrt_imu))
        
        accel_global = rot_matrix @ (a_center_local_ms2 / 9.81)
        linear_accel_g = accel_global - self.gravity_vector
        linear_accel_ms2 = linear_accel_g * 9.81
        
        # -------------------------------------------------------------
        # STEP 3: DIFFERENTIAL WHEEL ODOMETRY
        # -------------------------------------------------------------
        if self.prev_enc is None:
            self.prev_enc = list(enc)
            
        delta_enc1 = enc[0] - self.prev_enc[0]
        delta_enc2 = enc[1] - self.prev_enc[1]
        
        # Encoder delta clamp (prevents dropped digit corruption jumps at 100Hz)
        MAX_DELTA = 1500  
        if abs(delta_enc1) > MAX_DELTA:
            delta_enc1 = MAX_DELTA * (1 if delta_enc1 > 0 else -1)
            
        if abs(delta_enc2) > MAX_DELTA:
            delta_enc2 = MAX_DELTA * (1 if delta_enc2 > 0 else -1)
            
        self.prev_enc = list(enc)
        
        # --- 1. BACKLASH FILTER ---
        # Track 1 (Left)
        if delta_enc1 > 0:
            if self.track_dir[0] != 1:
                self.track_dir[0] = 1
                self.backlash_remaining[0] = self.BACKLASH_TICKS
        elif delta_enc1 < 0:
            if self.track_dir[0] != -1:
                self.track_dir[0] = -1
                self.backlash_remaining[0] = self.BACKLASH_TICKS
        if self.backlash_remaining[0] > 0:
            consumed = min(abs(delta_enc1), self.backlash_remaining[0])
            self.backlash_remaining[0] -= consumed
            delta_enc1 = (abs(delta_enc1) - consumed) * self.track_dir[0]
            
        # Track 2 (Right)
        if delta_enc2 > 0:
            if self.track_dir[1] != 1:
                self.track_dir[1] = 1
                self.backlash_remaining[1] = self.BACKLASH_TICKS
        elif delta_enc2 < 0:
            if self.track_dir[1] != -1:
                self.track_dir[1] = -1
                self.backlash_remaining[1] = self.BACKLASH_TICKS
        if self.backlash_remaining[1] > 0:
            consumed = min(abs(delta_enc2), self.backlash_remaining[1])
            self.backlash_remaining[1] -= consumed
            delta_enc2 = (abs(delta_enc2) - consumed) * self.track_dir[1]
        
        avg_delta = (delta_enc1 + delta_enc2) / 2.0
        tpm = self.ticks_per_meter_fwd if avg_delta >= 0 else self.ticks_per_meter_rev
        
        left_dist_m = (delta_enc1 / tpm)
        right_dist_m = (delta_enc2 / tpm)
        linear_dist_m = (left_dist_m + right_dist_m) / 2.0
        
        # Slip Ratio calculation
        translation_dist = abs(left_dist_m + right_dist_m)
        rotation_dist = abs(left_dist_m - right_dist_m)
        turn_ratio = rotation_dist / translation_dist if translation_dist > 0.001 else 999.0
        is_slipping = turn_ratio > 2.0
        
        # -------------------------------------------------------------
        # STEP 4: EXACT CIRCULAR ARC KINEMATICS & FRONT FACE OFFSET
        # -------------------------------------------------------------
        is_straight = (abs(delta_enc1 - delta_enc2) < max(abs(delta_enc1), abs(delta_enc2)) * 0.1) and (abs(avg_delta) > 10)
        
        if not self.position_initialized:
            self.filtered_yaw = euler_deg[2]
            yaw_rad = math.radians(self.filtered_yaw)
            
            # Center position placed backward along heading so FRONT FACE starts at (0,0)
            self.position[0] = self.front_offset * math.sin(yaw_rad)
            self.position[1] = -self.front_offset * math.cos(yaw_rad)
            self.position[2] = 0.0
            self.position_initialized = True
            
        alpha_yaw = 0.02 if is_straight else 0.8
        
        yaw_diff = euler_deg[2] - self.filtered_yaw
        if yaw_diff > 180.0: yaw_diff -= 360.0
        elif yaw_diff < -180.0: yaw_diff += 360.0
        
        self.filtered_yaw = (self.filtered_yaw + alpha_yaw * yaw_diff) % 360.0
        yaw_rad = math.radians(self.filtered_yaw)
            
        # EXACT CIRCULAR ARC INTEGRATION
        dTheta = (right_dist_m - left_dist_m) / self.wheel_base
        
        if abs(dTheta) < 0.0001:
            # Moving purely straight
            self.position[0] += linear_dist_m * -math.sin(yaw_rad)
            self.position[1] += linear_dist_m * math.cos(yaw_rad)
        else:
            # Sweeping an arc
            radius = linear_dist_m / dTheta
            self.position[0] += radius * (math.cos(yaw_rad + dTheta) - math.cos(yaw_rad))
            self.position[1] += radius * (math.sin(yaw_rad + dTheta) - math.sin(yaw_rad))
            
        self.position[2] = 0.0
        
        # FRONT FACE CALCULATION
        front_pos = self.position.copy()
        front_pos[0] += self.front_offset * -math.sin(yaw_rad)
        front_pos[1] += self.front_offset * math.cos(yaw_rad)
        
        # Total distance (Odometer) accumulation
        camera_delta_dist = math.sqrt(linear_dist_m**2 + (dTheta * self.front_offset)**2)
        self.total_distance += camera_delta_dist
        
        displacement = math.sqrt(front_pos[0]**2 + front_pos[1]**2)
        
        # Linear & angular velocity calculation
        linear_velocity_mps = linear_dist_m / self.dt
        angular_velocity_radps = dTheta / self.dt
        
        return {
            'euler_deg': euler_deg,
            'linear_accel': linear_accel_ms2,
            'position': front_pos,
            'center_position': self.position.copy(),
            'real_position': front_pos,
            'yaw_rad': yaw_rad,
            'yaw_deg': self.filtered_yaw,
            'total_distance_cm': self.total_distance * 100.0,
            'displacement_cm': displacement * 100.0,
            'is_slipping': is_slipping,
            'linear_velocity': linear_velocity_mps,
            'angular_velocity': angular_velocity_radps
        }
