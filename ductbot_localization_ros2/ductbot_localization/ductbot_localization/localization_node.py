import math
import os
import sys
import threading
import time
import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.duration import Duration

from nav_msgs.msg import Odometry, Path
from geometry_msgs.msg import PoseStamped, TransformStamped, Quaternion
from sensor_msgs.msg import Imu, Range
from std_msgs.msg import Float32MultiArray, String, Float32
from std_srvs.srv import Trigger

from tf2_ros import TransformBroadcaster, StaticTransformBroadcaster
try:
    from scipy.spatial.transform import Rotation as R
except Exception:
    class _FallbackRotation:
        def __init__(self, quat):
            self._quat = quat

        @classmethod
        def from_euler(cls, seq, angles, degrees=False):
            if seq == 'z':
                yaw = np.radians(angles) if degrees else angles
                return cls(np.array([0.0, 0.0, np.sin(yaw * 0.5), np.cos(yaw * 0.5)]))
            elif seq == 'xyz':
                rad = np.radians(angles) if degrees else angles
                r, p, y = rad
                cr, sr = np.cos(r * 0.5), np.sin(r * 0.5)
                cp, sp = np.cos(p * 0.5), np.sin(p * 0.5)
                cy, sy = np.cos(y * 0.5), np.sin(y * 0.5)
                w = cy * cp * cr + sy * sp * sr
                x = cy * cp * sr - sy * sp * cr
                y = cy * sp * cr + sy * cp * sr
                z = sy * cp * cr - cy * sp * sr
                return cls(np.array([x, y, z, w]))
            return cls(np.array([0.0, 0.0, 0.0, 1.0]))

        def as_quat(self):
            return self._quat

    R = _FallbackRotation

from .localization_engine import LocalizationEngine
from .checkpoint_logger import CheckpointLogger

try:
    import serial
except ImportError:
    serial = None


class DuctBotLocalizationNode(Node):
    """
    ROS 2 Node for Duct Bot Localization, IMU, Odometry, and Telemetry.
    
    Reads serial stream from Master ESP32 (or simulated topic),
    runs circular-arc differential kinematics with backlash & asymmetric track scaling,
    broadcasts TF transforms, logs 10mm checkpoints, and publishes standard ROS 2 messages.
    """
    def __init__(self):
        super().__init__('ductbot_localization_node')
        
        # -------------------------------------------------------------
        # 1. PARAMETERS DECLARATION & INITIALIZATION
        # -------------------------------------------------------------
        self.declare_parameter('port', '/dev/ttyUSB0')
        self.declare_parameter('baudrate', 115200)
        self.declare_parameter('wheel_base', 0.260)
        self.declare_parameter('front_offset', 0.145)
        self.declare_parameter('ticks_per_meter_fwd', 15055.0)
        self.declare_parameter('ticks_per_meter_rev', 16260.0)
        self.declare_parameter('backlash_ticks', 450)
        self.declare_parameter('sample_rate_hz', 100.0)
        
        self.declare_parameter('odom_frame', 'odom')
        self.declare_parameter('base_frame', 'base_link')
        self.declare_parameter('front_face_frame', 'front_face_link')
        self.declare_parameter('imu_frame', 'imu_link')
        self.declare_parameter('tof_left_frame', 'tof_left_link')
        self.declare_parameter('tof_right_frame', 'tof_right_link')
        self.declare_parameter('publish_tf', True)
        
        self.declare_parameter('enable_checkpoint_logging', True)
        self.declare_parameter('checkpoint_interval_m', 0.01)
        self.declare_parameter('csv_output_dir', os.path.expanduser('~/ductbot_logs'))
        self.declare_parameter('sim_mode', False)
        
        # Retrieve parameter values
        self.port = self.get_parameter('port').get_parameter_value().string_value
        self.baudrate = self.get_parameter('baudrate').get_parameter_value().integer_value
        self.wheel_base = self.get_parameter('wheel_base').get_parameter_value().double_value
        self.front_offset = self.get_parameter('front_offset').get_parameter_value().double_value
        self.ticks_per_meter_fwd = self.get_parameter('ticks_per_meter_fwd').get_parameter_value().double_value
        self.ticks_per_meter_rev = self.get_parameter('ticks_per_meter_rev').get_parameter_value().double_value
        self.backlash_ticks = self.get_parameter('backlash_ticks').get_parameter_value().integer_value
        self.sample_rate_hz = self.get_parameter('sample_rate_hz').get_parameter_value().double_value
        
        self.odom_frame = self.get_parameter('odom_frame').get_parameter_value().string_value
        self.base_frame = self.get_parameter('base_frame').get_parameter_value().string_value
        self.front_face_frame = self.get_parameter('front_face_frame').get_parameter_value().string_value
        self.imu_frame = self.get_parameter('imu_frame').get_parameter_value().string_value
        self.tof_left_frame = self.get_parameter('tof_left_frame').get_parameter_value().string_value
        self.tof_right_frame = self.get_parameter('tof_right_frame').get_parameter_value().string_value
        self.publish_tf = self.get_parameter('publish_tf').get_parameter_value().bool_value
        
        self.enable_checkpoint_logging = self.get_parameter('enable_checkpoint_logging').get_parameter_value().bool_value
        self.checkpoint_interval_m = self.get_parameter('checkpoint_interval_m').get_parameter_value().double_value
        self.csv_output_dir = self.get_parameter('csv_output_dir').get_parameter_value().string_value
        self.sim_mode = self.get_parameter('sim_mode').get_parameter_value().bool_value

        self.get_logger().info("=== DuctBot ROS 2 Localization Node Initializing ===")
        self.get_logger().info(f"Port: {self.port}, Baud: {self.baudrate}, Sim Mode: {self.sim_mode}")
        self.get_logger().info(f"Geometry: WheelBase={self.wheel_base}m, FrontOffset={self.front_offset}m")
        self.get_logger().info(f"Calibration: FwdScale={self.ticks_per_meter_fwd}, RevScale={self.ticks_per_meter_rev}, Backlash={self.backlash_ticks}")

        # -------------------------------------------------------------
        # 2. CORE ENGINES INITIALIZATION
        # -------------------------------------------------------------
        self.engine = LocalizationEngine(
            sample_rate_hz=self.sample_rate_hz,
            wheel_base=self.wheel_base,
            front_offset=self.front_offset,
            ticks_per_meter_fwd=self.ticks_per_meter_fwd,
            ticks_per_meter_rev=self.ticks_per_meter_rev,
            backlash_ticks=self.backlash_ticks
        )
        
        self.logger_engine = None
        if self.enable_checkpoint_logging:
            self.logger_engine = CheckpointLogger(
                output_dir=self.csv_output_dir,
                interval_m=self.checkpoint_interval_m
            )
            self.logger_engine.log_event("ROS2_START")
            self.get_logger().info(f"Logging 10mm checkpoints to: {self.logger_engine.output_file}")

        # -------------------------------------------------------------
        # 3. PUBLISHERS & BROADCASTERS
        # -------------------------------------------------------------
        self.odom_pub = self.create_publisher(Odometry, '/odom', 10)
        self.pose_pub = self.create_publisher(PoseStamped, '/ductbot/pose', 10)
        self.path_pub = self.create_publisher(Path, '/ductbot/path', 10)
        self.imu_pub = self.create_publisher(Imu, '/ductbot/imu', 10)
        self.tof_left_pub = self.create_publisher(Range, '/ductbot/tof/left', 10)
        self.tof_right_pub = self.create_publisher(Range, '/ductbot/tof/right', 10)
        self.distance_pub = self.create_publisher(Float32, '/ductbot/robot/distance', 10)
        self.env_pub = self.create_publisher(Float32MultiArray, '/ductbot/environment', 10)
        self.raw_telemetry_pub = self.create_publisher(String, '/ductbot/raw_telemetry', 10)
        
        self.tf_broadcaster = TransformBroadcaster(self)
        self.static_tf_broadcaster = StaticTransformBroadcaster(self)
        
        # Publish static robot transforms
        self._publish_static_transforms()
        
        # Path message container
        self.path_msg = Path()
        self.path_msg.header.frame_id = self.odom_frame

        # -------------------------------------------------------------
        # 4. SERVICES
        # -------------------------------------------------------------
        self.pause_service = self.create_service(Trigger, '/ductbot/pause_tracking', self._handle_pause)
        self.resume_service = self.create_service(Trigger, '/ductbot/resume_tracking', self._handle_resume)
        self.reset_service = self.create_service(Trigger, '/ductbot/reset_odometry', self._handle_reset)
        
        # -------------------------------------------------------------
        # 5. SIMULATION / EXTERNAL DATA SUBSCRIBER
        # -------------------------------------------------------------
        self.sim_sub = self.create_subscription(
            String,
            '/ductbot/sim_telemetry',
            self._handle_sim_telemetry,
            10
        )

        # State tracking
        self.is_paused = False
        self.is_running = True
        self.serial_conn = None
        self.lock = threading.Lock()

        # -------------------------------------------------------------
        # 6. HARDWARE SERIAL BACKGROUND THREAD
        # -------------------------------------------------------------
        if not self.sim_mode:
            self.serial_thread = threading.Thread(target=self._serial_worker, daemon=True)
            self.serial_thread.start()
        else:
            self.get_logger().info("Running in SIMULATION MODE. Waiting for messages on /ductbot/sim_telemetry")

    def _publish_static_transforms(self):
        """Publishes fixed robot geometry transforms (base_link to front_face, imu, tof sensors)."""
        now = self.get_clock().now().to_msg()
        static_transforms = []
        
        # 1. base_link -> front_face_link (Camera at front edge, +14.5cm on Y axis in math / X in ROS convention)
        tf_front = TransformStamped()
        tf_front.header.stamp = now
        tf_front.header.frame_id = self.base_frame
        tf_front.child_frame_id = self.front_face_frame
        tf_front.transform.translation.x = 0.0
        tf_front.transform.translation.y = self.front_offset
        tf_front.transform.translation.z = 0.0
        tf_front.transform.rotation.w = 1.0
        static_transforms.append(tf_front)
        
        # 2. base_link -> imu_link (Geometric center)
        tf_imu = TransformStamped()
        tf_imu.header.stamp = now
        tf_imu.header.frame_id = self.base_frame
        tf_imu.child_frame_id = self.imu_frame
        tf_imu.transform.translation.x = 0.0
        tf_imu.transform.translation.y = 0.0
        tf_imu.transform.translation.z = 0.0
        tf_imu.transform.rotation.w = 1.0
        static_transforms.append(tf_imu)
        
        # 3. base_link -> tof_left_link (-13cm X, +10cm Y)
        tf_tofl = TransformStamped()
        tf_tofl.header.stamp = now
        tf_tofl.header.frame_id = self.base_frame
        tf_tofl.child_frame_id = self.tof_left_frame
        tf_tofl.transform.translation.x = - (self.wheel_base / 2.0)
        tf_tofl.transform.translation.y = 0.10
        tf_tofl.transform.translation.z = 0.0
        # Left sensor points outward 90 deg (Yaw = +pi/2)
        q_l = R.from_euler('z', 90.0, degrees=True).as_quat()
        tf_tofl.transform.rotation.x = float(q_l[0])
        tf_tofl.transform.rotation.y = float(q_l[1])
        tf_tofl.transform.rotation.z = float(q_l[2])
        tf_tofl.transform.rotation.w = float(q_l[3])
        static_transforms.append(tf_tofl)
        
        # 4. base_link -> tof_right_link (+13cm X, +10cm Y)
        tf_tofr = TransformStamped()
        tf_tofr.header.stamp = now
        tf_tofr.header.frame_id = self.base_frame
        tf_tofr.child_frame_id = self.tof_right_frame
        tf_tofr.transform.translation.x = (self.wheel_base / 2.0)
        tf_tofr.transform.translation.y = 0.10
        tf_tofr.transform.translation.z = 0.0
        # Right sensor points outward -90 deg (Yaw = -pi/2)
        q_r = R.from_euler('z', -90.0, degrees=True).as_quat()
        tf_tofr.transform.rotation.x = float(q_r[0])
        tf_tofr.transform.rotation.y = float(q_r[1])
        tf_tofr.transform.rotation.z = float(q_r[2])
        tf_tofr.transform.rotation.w = float(q_r[3])
        static_transforms.append(tf_tofr)
        
        self.static_tf_broadcaster.sendTransform(static_transforms)

    def _handle_pause(self, request, response):
        with self.lock:
            self.is_paused = True
            if self.logger_engine:
                self.logger_engine.log_event("ROS2_PAUSE")
        self.get_logger().info("Localization tracking PAUSED by service call.")
        response.success = True
        response.message = "Tracking paused successfully."
        return response

    def _handle_resume(self, request, response):
        with self.lock:
            self.is_paused = False
            if self.logger_engine:
                self.logger_engine.log_event("ROS2_RESUME")
        self.get_logger().info("Localization tracking RESUMED by service call.")
        response.success = True
        response.message = "Tracking resumed successfully."
        return response

    def _handle_reset(self, request, response):
        with self.lock:
            self.engine.reset()
            if self.logger_engine:
                self.logger_engine.reset()
                self.logger_engine.log_event("ROS2_RESET")
            self.path_msg.poses.clear()
        self.get_logger().info("Localization odometry RESET to (0, 0, 0).")
        response.success = True
        response.message = "Odometry and path reset successfully."
        return response

    def _handle_sim_telemetry(self, msg: String):
        """Processes telemetry strings received from /ductbot/sim_telemetry."""
        self.process_raw_telemetry_line(msg.data)

    def process_raw_telemetry_line(self, line: str):
        """
        Parses the Master ESP32 string format:
        ENC1=123 ENC2=456 | ACC: x y z | GYRO: x y z | ANG: r p y | TOFL: 52 TOFR: 48 | ENV: temp hum voc co2 mq2 dust
        """
        if not line or self.is_paused:
            return
            
        line = line.strip()
        if not line:
            return

        # Publish raw telemetry for debug/logging
        raw_msg = String()
        raw_msg.data = line
        self.raw_telemetry_pub.publish(raw_msg)
        
        if "ACC:" in line and "GYRO:" in line and "ENC1=" in line and "ANG:" in line:
            sections = line.split("|")
            acc_vals, gyr_vals, enc_vals, ang_vals = [], [], [0, 0], []
            tof_vals = [0, 0]
            env_vals = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
            
            for section in sections:
                section = section.strip()
                if section.startswith("ACC:"):
                    try:
                        num_str = section.replace("ACC:", "").strip()
                        acc_vals = [float(v) for v in num_str.split()]
                    except Exception: pass
                elif section.startswith("GYRO:"):
                    try:
                        num_str = section.replace("GYRO:", "").strip()
                        gyr_vals = [float(v) for v in num_str.split()]
                    except Exception: pass
                elif section.startswith("ANG:"):
                    try:
                        num_str = section.replace("ANG:", "").strip()
                        ang_vals = [float(v) for v in num_str.split()]
                    except Exception: pass
                elif "ENC1=" in section:
                    try:
                        parts = section.split()
                        for p in parts:
                            if p.startswith("ENC1="): enc_vals[0] = int(p.split("=")[1])
                            elif p.startswith("ENC2="): enc_vals[1] = int(p.split("=")[1])
                    except Exception: pass
                elif "TOFL:" in section:
                    try:
                        parts = section.split()
                        for p_idx, p in enumerate(parts):
                            if p == "TOFL:" and p_idx + 1 < len(parts):
                                tof_vals[0] = int(parts[p_idx + 1])
                            elif p == "TOFR:" and p_idx + 1 < len(parts):
                                tof_vals[1] = int(parts[p_idx + 1])
                    except Exception: pass
                elif section.startswith("ENV:"):
                    try:
                        num_str = section.replace("ENV:", "").strip()
                        vals = [float(v) for v in num_str.split()]
                        if len(vals) == 6:
                            env_vals = vals
                    except Exception: pass
                    
            if len(acc_vals) == 3 and len(gyr_vals) == 3 and len(ang_vals) == 3:
                with self.lock:
                    # Convert gyro from degrees/sec to radians/sec
                    gyr_rads = np.deg2rad(gyr_vals)
                    loc_data = self.engine.update(acc_vals, gyr_rads, enc_vals, ang_vals)
                    
                    if self.logger_engine and self.enable_checkpoint_logging:
                        self.logger_engine.update(
                            total_distance=loc_data["total_distance_cm"] / 100.0,
                            x=loc_data["real_position"][0],
                            y=loc_data["real_position"][1],
                            yaw=loc_data["euler_deg"][2],
                            tof=tof_vals,
                            env=env_vals
                        )
                        
                self._publish_ros_messages(loc_data, acc_vals, gyr_rads, ang_vals, tof_vals, env_vals)

    def _publish_ros_messages(self, loc_data, acc_vals, gyr_rads, ang_vals, tof_vals, env_vals):
        """Converts internal math dictionary into standard ROS 2 messages and publishes them."""
        now = self.get_clock().now().to_msg()
        
        # Heading quaternion (from filtered yaw in radians)
        yaw_rad = loc_data['yaw_rad']
        q_rot = R.from_euler('z', yaw_rad).as_quat()
        quat_msg = Quaternion(
            x=float(q_rot[0]),
            y=float(q_rot[1]),
            z=float(q_rot[2]),
            w=float(q_rot[3])
        )
        
        # 1. Odometry Message (/odom)
        odom = Odometry()
        odom.header.stamp = now
        odom.header.frame_id = self.odom_frame
        odom.child_frame_id = self.base_frame
        
        # Center Position of Robot
        center_pos = loc_data['center_position']
        tot_dist_m = float(loc_data['total_distance_cm'] / 100.0)
        odom.pose.pose.position.x = float(center_pos[0])
        odom.pose.pose.position.y = float(center_pos[1])
        odom.pose.pose.position.z = tot_dist_m
        odom.pose.pose.orientation = quat_msg
        
        # Publish total distance Float32 message
        try:
            dist_msg = Float32()
            dist_msg.data = tot_dist_m
            self.distance_pub.publish(dist_msg)
        except Exception:
            pass

        # Velocities (Twist)
        odom.twist.twist.linear.x = float(loc_data['linear_velocity'])
        odom.twist.twist.angular.z = float(loc_data['angular_velocity'])
        
        # Covariance matrix diagonal placeholders
        odom.pose.covariance[0] = 0.001   # x
        odom.pose.covariance[7] = 0.001   # y
        odom.pose.covariance[35] = 0.005  # yaw
        
        self.odom_pub.publish(odom)
        
        # 2. Dynamic TF Transform (odom -> base_link)
        if self.publish_tf:
            tf_msg = TransformStamped()
            tf_msg.header.stamp = now
            tf_msg.header.frame_id = self.odom_frame
            tf_msg.child_frame_id = self.base_frame
            tf_msg.transform.translation.x = float(center_pos[0])
            tf_msg.transform.translation.y = float(center_pos[1])
            tf_msg.transform.translation.z = float(center_pos[2])
            tf_msg.transform.rotation = quat_msg
            self.tf_broadcaster.sendTransform(tf_msg)
            
        # 3. PoseStamped Message (/ductbot/pose - Front Face Location)
        front_pos = loc_data['real_position']
        pose_stamped = PoseStamped()
        pose_stamped.header.stamp = now
        pose_stamped.header.frame_id = self.odom_frame
        pose_stamped.pose.position.x = float(front_pos[0])
        pose_stamped.pose.position.y = float(front_pos[1])
        pose_stamped.pose.position.z = float(front_pos[2])
        pose_stamped.pose.orientation = quat_msg
        self.pose_pub.publish(pose_stamped)
        
        # 4. Path Message (/ductbot/path)
        # Append point if moved > 2cm from last path point or path is empty
        if not self.path_msg.poses or math.dist(
            [front_pos[0], front_pos[1]],
            [self.path_msg.poses[-1].pose.position.x, self.path_msg.poses[-1].pose.position.y]
        ) > 0.02:
            self.path_msg.header.stamp = now
            self.path_msg.poses.append(pose_stamped)
            # Limit path length to last 2000 points to preserve memory
            if len(self.path_msg.poses) > 2000:
                self.path_msg.poses.pop(0)
            self.path_pub.publish(self.path_msg)
            
        # 5. IMU Message (/ductbot/imu)
        imu_msg = Imu()
        imu_msg.header.stamp = now
        imu_msg.header.frame_id = self.imu_frame
        
        # Full 3D orientation quaternion from hardware Euler angles
        imu_rot = R.from_euler('xyz', loc_data['euler_deg'], degrees=True).as_quat()
        imu_msg.orientation.x = float(imu_rot[0])
        imu_msg.orientation.y = float(imu_rot[1])
        imu_msg.orientation.z = float(imu_rot[2])
        imu_msg.orientation.w = float(imu_rot[3])
        
        imu_msg.angular_velocity.x = float(gyr_rads[0])
        imu_msg.angular_velocity.y = float(gyr_rads[1])
        imu_msg.angular_velocity.z = float(gyr_rads[2])
        
        # Linear acceleration in m/s^2 (converted from g units)
        lin_acc = loc_data['linear_accel']
        imu_msg.linear_acceleration.x = float(lin_acc[0])
        imu_msg.linear_acceleration.y = float(lin_acc[1])
        imu_msg.linear_acceleration.z = float(lin_acc[2])
        
        self.imu_pub.publish(imu_msg)
        
        # 6. Time-of-Flight Left & Right Range Messages
        # TOF readings in mm, convert to meters. (-1: <25mm blind, -2: >1000mm out of range)
        range_l = Range()
        range_l.header.stamp = now
        range_l.header.frame_id = self.tof_left_frame
        range_l.radiation_type = Range.INFRARED
        range_l.field_of_view = 0.44  # ~25 degrees FOV for VL53L0X
        range_l.min_range = 0.025     # 25mm
        range_l.max_range = 1.000     # 1000mm
        if tof_vals[0] > 0:
            range_l.range = float(tof_vals[0]) / 1000.0
        elif tof_vals[0] == -1:
            range_l.range = 0.020     # Below min
        else:
            range_l.range = float('inf') # Out of range / timeout
        self.tof_left_pub.publish(range_l)
        
        range_r = Range()
        range_r.header.stamp = now
        range_r.header.frame_id = self.tof_right_frame
        range_r.radiation_type = Range.INFRARED
        range_r.field_of_view = 0.44
        range_r.min_range = 0.025
        range_r.max_range = 1.000
        if tof_vals[1] > 0:
            range_r.range = float(tof_vals[1]) / 1000.0
        elif tof_vals[1] == -1:
            range_r.range = 0.020
        else:
            range_r.range = float('inf')
        self.tof_right_pub.publish(range_r)
        
        # 7. Environment Telemetry Message (/ductbot/environment)
        # Array contents: [Temp_C, Humidity_pct, VOC_index, CO2_ppm, MQ2_raw, Dust_raw]
        env_msg = Float32MultiArray()
        env_msg.data = [float(v) for v in env_vals]
        self.env_pub.publish(env_msg)

    def _serial_worker(self):
        """Background thread reading lines from physical USB serial port."""
        if serial is None:
            self.get_logger().error("pyserial is not installed! Please run 'pip install pyserial'")
            return
            
        while rclpy.ok() and self.is_running:
            if self.serial_conn is None or not self.serial_conn.is_open:
                try:
                    self.get_logger().info(f"Connecting to Master ESP32 on {self.port} at {self.baudrate} baud...")
                    self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=1.0)
                    self.get_logger().info(f"Connected successfully to {self.port}!")
                except Exception as e:
                    self.get_logger().warn(f"Failed to open {self.port}: {e}. Retrying in 2 seconds...")
                    time.sleep(2.0)
                    continue

            try:
                if self.serial_conn.in_waiting > 0:
                    line = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        self.process_raw_telemetry_line(line)
                else:
                    time.sleep(0.001)
            except Exception as e:
                self.get_logger().warn(f"Serial communication error: {e}")
                if self.serial_conn:
                    try: self.serial_conn.close()
                    except Exception: pass
                self.serial_conn = None
                time.sleep(1.0)

    def destroy_node(self):
        self.is_running = False
        if self.logger_engine:
            self.logger_engine.log_event("ROS2_STOP")
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = DuctBotLocalizationNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Shutting down DuctBot Localization Node...")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
