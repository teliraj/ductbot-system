"""
ROS2 & RTSP Unified Camera & Localization Bridge for Ductbots UI.
Receives Front/Rear camera streams via ROS2 topics or direct RTSP fallback,
subscribes to real-time odometry, pose, path, IMU, TOF and environmental metrics
from ductbot_localization_node, and interfaces with the video comparison engine.
"""

import os
import sys
import time
import math
import json
import threading
import cv2
import numpy as np
import atexit

# Ensure ductbot_localization package from Downloads is prioritized on sys.path
_DOWNLOADS_PKG_DIR = "/home/roboserv-4i/Downloads/ductbot_localization_ros2/ductbot_localization"
if os.path.exists(_DOWNLOADS_PKG_DIR):
    if _DOWNLOADS_PKG_DIR in sys.path:
        sys.path.remove(_DOWNLOADS_PKG_DIR)
    sys.path.insert(0, _DOWNLOADS_PKG_DIR)

# Configurable DVR RTSP URLs (can be overridden via environment variables)
DVR_IP = os.environ.get("DUCTBOT_DVR_IP", "192.168.1.130")
DEFAULT_FRONT_RTSP = os.environ.get(
    "DUCTBOT_FRONT_RTSP",
    f"rtsp://admin:dvr%40robo4i@{DVR_IP}:554/cam/realmonitor?channel=1&subtype=0"
)
DEFAULT_REAR_RTSP = os.environ.get(
    "DUCTBOT_REAR_RTSP",
    f"rtsp://admin:dvr%40robo4i@{DVR_IP}:554/cam/realmonitor?channel=2&subtype=0"
)

FRONT_TOPICS = ["/ductbot/camera/front", "/ductbot/camera/front/image_raw", "/ductbot/camera/front/compressed"]
REAR_TOPICS = ["/ductbot/camera/rear", "/ductbot/camera/rear/image_raw", "/ductbot/camera/rear/compressed"]

# Try importing ROS2 libraries
ROS2_AVAILABLE = False
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
    try:
        from sensor_msgs.msg import (
            Image as RosImage,
            CompressedImage as RosCompressedImage,
            Imu as RosImu,
            Range as RosRange,
        )
    except ImportError:
        RosImage = RosCompressedImage = RosImu = RosRange = None

    try:
        from nav_msgs.msg import Odometry as RosOdometry, Path as RosPath
    except ImportError:
        RosOdometry = RosPath = None

    try:
        from geometry_msgs.msg import PoseStamped as RosPoseStamped
    except ImportError:
        RosPoseStamped = None

    try:
        from std_msgs.msg import (
            Float32 as RosFloat32,
            String as RosString,
            Float32MultiArray as RosFloat32MultiArray,
        )
    except ImportError:
        RosFloat32 = RosString = RosFloat32MultiArray = None

    try:
        from std_srvs.srv import Trigger as RosTrigger
    except ImportError:
        RosTrigger = None

    try:
        from cv_bridge import CvBridge
        cv_bridge_instance = CvBridge()
    except Exception:
        cv_bridge_instance = None

    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False


def quat_to_euler_deg(x, y, z, w):
    """Converts quaternion (x, y, z, w) to Euler angles (roll, pitch, yaw) in degrees."""
    # Roll (x-axis rotation)
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    # Pitch (y-axis rotation)
    sinp = 2.0 * (w * y - z * x)
    if abs(sinp) >= 1.0:
        pitch = math.copysign(math.pi / 2.0, sinp)
    else:
        pitch = math.asin(sinp)

    # Yaw (z-axis rotation)
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return math.degrees(roll), math.degrees(pitch), math.degrees(yaw)


class DirectRTSPCaptureThread(threading.Thread):
    """Background worker that continuously captures the newest frame from an RTSP stream."""

    def __init__(self, camera_name, rtsp_url, on_frame_callback):
        super().__init__(daemon=True, name=f"RTSP-{camera_name}")
        self.camera_name = camera_name
        self.rtsp_url = rtsp_url
        self.on_frame_callback = on_frame_callback
        self.running = True
        self.cap = None
        self._last_error_log_time = 0.0

    def run(self):
        # Configure ffmpeg low-latency flags for OpenCV
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            "rtsp_transport;tcp|fflags;nobuffer|max_delay;100000|stimeout;2000000"
        )

        while self.running:
            try:
                self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                if not self.cap.isOpened():
                    now = time.time()
                    if now - self._last_error_log_time > 10.0:
                        print(f"[RTSP-{self.camera_name}] Waiting for connection to {self.rtsp_url.split('@')[-1]}...")
                        self._last_error_log_time = now
                    time.sleep(4.0)
                    continue

                print(f"[RTSP-{self.camera_name}] Connected successfully to stream.")
                while self.running and self.cap.isOpened():
                    ret, frame = self.cap.read()
                    if not self.running:
                        break
                    if ret and frame is not None:
                        self.on_frame_callback(self.camera_name, frame)
                    else:
                        time.sleep(0.04)
                        break
            except Exception as e:
                now = time.time()
                if now - self._last_error_log_time > 10.0:
                    print(f"[RTSP-{self.camera_name}] Connection error: {e}")
                    self._last_error_log_time = now
                time.sleep(4.0)
            finally:
                if self.cap:
                    try:
                        self.cap.release()
                    except Exception:
                        pass
                    self.cap = None

    def stop(self):
        self.running = False


class CameraBridge:
    """
    Unified Camera, Localization & Video Comparison Bridge for Ductbots UI.
    Provides thread-safe access to:
    - Front and Rear camera feeds (ROS2 topics or RTSP fallback)
    - Localization telemetry (/odom, /ductbot/pose, /ductbot/path)
    - Sensor data (/ductbot/imu, /ductbot/tof/*, /ductbot/environment)
    - Video comparison status and trigger actions
    """

    def __init__(self, front_rtsp=None, rear_rtsp=None, enable_ros2=True):
        self.front_rtsp = front_rtsp or DEFAULT_FRONT_RTSP
        self.rear_rtsp = rear_rtsp or DEFAULT_REAR_RTSP
        self.enable_ros2 = enable_ros2 and ROS2_AVAILABLE

        self.active_camera = "front"
        self._lock = threading.Lock()
        self._frames = {
            "front": None,
            "rear": None,
        }
        self._last_frame_times = {
            "front": 0.0,
            "rear": 0.0,
        }
        self._source_types = {
            "front": "NONE",
            "rear": "NONE",
        }

        # Localization State Cache
        self._loc_lock = threading.Lock()
        self._localization_data = {
            "has_localization": False,
            "last_update": 0.0,
            # Position & Pose
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
            "yaw": 0.0,
            "pitch": 0.0,
            "roll": 0.0,
            "linear_speed": 0.0,
            "angular_speed": 0.0,
            "total_distance_m": 0.0,
            # Front camera pose
            "front_x": 0.0,
            "front_y": 0.0,
            # Trajectory path trail [(x, y), ...]
            "path": [],
            # TOF distances (mm)
            "TOF_L": 0.0,
            "TOF_R": 0.0,
            # Environmental
            "temperature": 0.0,
            "humidity": 0.0,
            "air_quality": 0.0,
            "gas_ppm": 0.0,
            "pressure": 0.0,
            "status_code": 0,
        }

        # Video comparison state
        self._comp_lock = threading.Lock()
        self._comparison_state = {
            "is_active": False,
            "progress_percent": 0.0,
            "status": "IDLE",
            "last_update": 0.0,
        }

        self.running = True
        self._ros_node = None
        self._ros_thread = None
        self._rtsp_threads = {}

        # ROS2 Service Clients
        self._cli_reset = None
        self._cli_pause = None
        self._cli_resume = None
        self._cli_compare_latest = None
        self._pub_trigger_comp = None

        atexit.register(self.stop)

        if self.enable_ros2:
            self._start_ros2()
        else:
            self._start_rtsp_fallbacks()

    def _on_new_frame(self, camera_name, frame, source="RTSP"):
        with self._lock:
            self._frames[camera_name] = frame
            self._last_frame_times[camera_name] = time.time()
            self._source_types[camera_name] = source

    def _start_ros2(self):
        def ros2_worker():
            try:
                if not rclpy.ok():
                    rclpy.init(args=None)
                self._ros_node = Node("ductbot_ui_ros_bridge")
                qos_sensors = QoSProfile(
                    reliability=ReliabilityPolicy.BEST_EFFORT,
                    history=HistoryPolicy.KEEP_LAST,
                    depth=10,
                )
                qos_cameras = QoSProfile(
                    reliability=ReliabilityPolicy.BEST_EFFORT,
                    history=HistoryPolicy.KEEP_LAST,
                    depth=1,
                )

                # ---------------------------------------------------------
                # 1. Camera Subscriptions
                # ---------------------------------------------------------
                def make_image_cb(cam_name):
                    def cb(msg):
                        try:
                            if cv_bridge_instance:
                                frame = cv_bridge_instance.imgmsg_to_cv2(msg, desired_encoding="bgr8")
                            else:
                                frame = np.frombuffer(msg.data, dtype=np.uint8).reshape((msg.height, msg.width, -1))
                            self._on_new_frame(cam_name, frame, source="ROS2")
                        except Exception:
                            pass
                    return cb

                def make_compressed_cb(cam_name):
                    def cb(msg):
                        try:
                            np_arr = np.frombuffer(msg.data, np.uint8)
                            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                            if frame is not None:
                                self._on_new_frame(cam_name, frame, source="ROS2")
                        except Exception:
                            pass
                    return cb

                if RosImage:
                    self._ros_node.create_subscription(RosImage, "/ductbot/camera/front", make_image_cb("front"), qos_cameras)
                    self._ros_node.create_subscription(RosImage, "/ductbot/camera/rear", make_image_cb("rear"), qos_cameras)
                if RosCompressedImage:
                    self._ros_node.create_subscription(RosCompressedImage, "/ductbot/camera/front/compressed", make_compressed_cb("front"), qos_cameras)
                    self._ros_node.create_subscription(RosCompressedImage, "/ductbot/camera/rear/compressed", make_compressed_cb("rear"), qos_cameras)

                # ---------------------------------------------------------
                # 2. Localization & Odometry Subscriptions
                # ---------------------------------------------------------
                if RosOdometry:
                    def _odom_cb(msg: RosOdometry):
                        with self._loc_lock:
                            pos = msg.pose.pose.position
                            ori = msg.pose.pose.orientation
                            r, p, y = quat_to_euler_deg(ori.x, ori.y, ori.z, ori.w)
                            vx = msg.twist.twist.linear.x
                            wz = msg.twist.twist.angular.z

                            self._localization_data["x"] = float(pos.x)
                            self._localization_data["y"] = float(pos.y)
                            self._localization_data["z"] = float(pos.z)
                            if float(pos.z) > 0.0 or self._localization_data["total_distance_m"] == 0.0:
                                self._localization_data["total_distance_m"] = round(float(pos.z), 4)
                            self._localization_data["roll"] = round(r, 2)
                            self._localization_data["pitch"] = round(p, 2)
                            self._localization_data["yaw"] = round(y, 2)
                            self._localization_data["linear_speed"] = round(vx, 3)
                            self._localization_data["angular_speed"] = round(wz, 3)
                            self._localization_data["has_localization"] = True
                            self._localization_data["last_update"] = time.time()
                    self._ros_node.create_subscription(RosOdometry, "/odom", _odom_cb, qos_sensors)

                if RosPoseStamped:
                    def _pose_cb(msg: RosPoseStamped):
                        with self._loc_lock:
                            self._localization_data["front_x"] = float(msg.pose.position.x)
                            self._localization_data["front_y"] = float(msg.pose.position.y)
                    self._ros_node.create_subscription(RosPoseStamped, "/ductbot/pose", _pose_cb, qos_sensors)

                if RosPath:
                    def _path_cb(msg: RosPath):
                        with self._loc_lock:
                            pts = []
                            for ps in msg.poses:
                                pts.append((float(ps.pose.position.x), float(ps.pose.position.y)))
                            self._localization_data["path"] = pts
                    self._ros_node.create_subscription(RosPath, "/ductbot/path", _path_cb, 10)

                if RosImu:
                    def _imu_cb(msg: RosImu):
                        with self._loc_lock:
                            ori = msg.orientation
                            r, p, y = quat_to_euler_deg(ori.x, ori.y, ori.z, ori.w)
                            self._localization_data["roll"] = round(r, 2)
                            self._localization_data["pitch"] = round(p, 2)
                            self._localization_data["yaw"] = round(y, 2)
                    self._ros_node.create_subscription(RosImu, "/ductbot/imu", _imu_cb, qos_sensors)

                if RosRange:
                    def _tof_l_cb(msg: RosRange):
                        with self._loc_lock:
                            self._localization_data["TOF_L"] = round(msg.range * 1000.0, 1)  # m to mm
                    def _tof_r_cb(msg: RosRange):
                        with self._loc_lock:
                            self._localization_data["TOF_R"] = round(msg.range * 1000.0, 1)  # m to mm
                    self._ros_node.create_subscription(RosRange, "/ductbot/tof/left", _tof_l_cb, qos_sensors)
                    self._ros_node.create_subscription(RosRange, "/ductbot/tof/right", _tof_r_cb, qos_sensors)

                if RosFloat32MultiArray:
                    def _env_cb(msg: RosFloat32MultiArray):
                        if len(msg.data) >= 6:
                            with self._loc_lock:
                                self._localization_data["temperature"] = round(float(msg.data[0]), 1)
                                self._localization_data["humidity"] = round(float(msg.data[1]), 1)
                                self._localization_data["air_quality"] = round(float(msg.data[2]), 1)
                                self._localization_data["gas_ppm"] = round(float(msg.data[3]), 1)
                                self._localization_data["pressure"] = round(float(msg.data[4]), 1)
                                self._localization_data["status_code"] = int(msg.data[5])
                    self._ros_node.create_subscription(RosFloat32MultiArray, "/ductbot/environment", _env_cb, qos_sensors)

                # ---------------------------------------------------------
                # 3. Video Comparison Subscriptions & Publishers
                # ---------------------------------------------------------
                if RosFloat32:
                    def _dist_cb(msg: RosFloat32):
                        with self._loc_lock:
                            self._localization_data["total_distance_m"] = round(float(msg.data), 4)
                    self._ros_node.create_subscription(RosFloat32, "/ductbot/robot/distance", _dist_cb, qos_sensors)

                    def _comp_prog_cb(msg: RosFloat32):
                        with self._comp_lock:
                            self._comparison_state["progress_percent"] = float(msg.data)
                            self._comparison_state["last_update"] = time.time()
                            self._comparison_state["is_active"] = (0.0 < msg.data < 100.0)
                    self._ros_node.create_subscription(RosFloat32, "/ductbot/video_comparison_progress", _comp_prog_cb, 10)

                if RosString:
                    def _comp_status_cb(msg: RosString):
                        try:
                            st = json.loads(msg.data)
                            with self._comp_lock:
                                self._comparison_state["status"] = st.get("status", msg.data)
                                self._comparison_state["progress_percent"] = float(st.get("progress_percent", self._comparison_state["progress_percent"]))
                                self._comparison_state["last_update"] = time.time()
                                self._comparison_state["is_active"] = (0.0 < self._comparison_state["progress_percent"] < 100.0)
                        except Exception:
                            with self._comp_lock:
                                self._comparison_state["status"] = msg.data
                    self._ros_node.create_subscription(RosString, "/ductbot/video_comparison_status", _comp_status_cb, 10)

                    self._pub_trigger_comp = self._ros_node.create_publisher(RosString, "/ductbot/trigger_comparison", 10)

                # ---------------------------------------------------------
                # 4. Service Clients
                # ---------------------------------------------------------
                if RosTrigger:
                    self._cli_reset = self._ros_node.create_client(RosTrigger, "/ductbot/reset_odometry")
                    self._cli_pause = self._ros_node.create_client(RosTrigger, "/ductbot/pause_tracking")
                    self._cli_resume = self._ros_node.create_client(RosTrigger, "/ductbot/resume_tracking")
                    self._cli_compare_latest = self._ros_node.create_client(RosTrigger, "/ductbot/compare_latest_runs")

                print("[ROS2 DuctbotROSBridge] Subscribed to camera & localization topics. Spinning...")
                while self.running and rclpy.ok():
                    rclpy.spin_once(self._ros_node, timeout_sec=0.05)

                    # If no ROS2 frames received in last 3s, ensure RTSP fallbacks run
                    now = time.time()
                    if now - self._last_frame_times["front"] > 3.0 and "front" not in self._rtsp_threads:
                        self._start_single_rtsp("front", self.front_rtsp)
                    if now - self._last_frame_times["rear"] > 3.0 and "rear" not in self._rtsp_threads:
                        self._start_single_rtsp("rear", self.rear_rtsp)

            except Exception as e:
                print(f"[ROS2 DuctbotROSBridge] Node error: {e}. Falling back to RTSP.")
                self._start_rtsp_fallbacks()

        self._ros_thread = threading.Thread(target=ros2_worker, daemon=True, name="ROS2-DuctbotBridge")
        self._ros_thread.start()

    def _start_single_rtsp(self, camera_name, rtsp_url):
        if camera_name in self._rtsp_threads:
            return
        t = DirectRTSPCaptureThread(camera_name, rtsp_url, self._on_new_frame)
        self._rtsp_threads[camera_name] = t
        t.start()

    def _start_rtsp_fallbacks(self):
        self._start_single_rtsp("front", self.front_rtsp)
        self._start_single_rtsp("rear", self.rear_rtsp)

    def set_active_camera(self, camera_name):
        """Set active camera to 'front' or 'rear'."""
        if camera_name in ("front", "rear"):
            self.active_camera = camera_name

    def get_active_camera(self):
        """Return active camera name ('front' or 'rear')."""
        return self.active_camera

    def toggle_camera(self):
        """Switch between 'front' and 'rear' cameras."""
        self.active_camera = "rear" if self.active_camera == "front" else "front"
        return self.active_camera

    def _generate_placeholder_frame(self, camera_name):
        """Generates a high-tech placeholder graphic when camera stream is disconnected."""
        w, h = 1280, 720
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:] = (18, 12, 8)  # Deep dark navy

        # Draw subtle grid lines
        for x in range(0, w, 60):
            cv2.line(frame, (x, 0), (x, h), (30, 22, 16), 1)
        for y in range(0, h, 60):
            cv2.line(frame, (0, y), (w, y), (30, 22, 16), 1)

        # Center target box
        cx, cy = w // 2, h // 2
        box_w, box_h = 560, 260
        x1, y1 = cx - box_w // 2, cy - box_h // 2
        x2, y2 = cx + box_w // 2, cy + box_h // 2
        cv2.rectangle(frame, (x1, y1), (x2, y2), (45, 35, 25), -1)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (180, 100, 40), 2)

        # Pulsing radar dot
        pulse = int((time.time() * 2) % 4)
        dots = "." * (pulse + 1)

        cam_title = f"{camera_name.upper()} CAMERA FEED"
        rtsp_target = self.front_rtsp if camera_name == "front" else self.rear_rtsp
        rtsp_display = rtsp_target.split("@")[-1] if "@" in rtsp_target else rtsp_target

        cv2.putText(frame, cam_title, (cx - 190, cy - 60), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (240, 240, 250), 2, cv2.LINE_AA)
        cv2.putText(frame, f"STATUS: SEARCHING / NO SIGNAL{dots}", (cx - 210, cy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (60, 120, 240), 2, cv2.LINE_AA)
        cv2.putText(frame, f"TARGET: {rtsp_display}", (cx - 240, cy + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (160, 160, 170), 1, cv2.LINE_AA)
        cv2.putText(frame, "ROS2 TOPIC: /ductbot/camera/" + camera_name, (cx - 200, cy + 80), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (120, 180, 100), 1, cv2.LINE_AA)

        # Corner crosshairs
        cv2.drawMarker(frame, (x1 + 20, y1 + 20), (180, 100, 40), cv2.MARKER_CROSS, 20, 2)
        cv2.drawMarker(frame, (x2 - 20, y1 + 20), (180, 100, 40), cv2.MARKER_CROSS, 20, 2)
        cv2.drawMarker(frame, (x1 + 20, y2 - 20), (180, 100, 40), cv2.MARKER_CROSS, 20, 2)
        cv2.drawMarker(frame, (x2 - 20, y2 - 20), (180, 100, 40), cv2.MARKER_CROSS, 20, 2)

        return frame

    def get_frame(self, camera_name, allow_placeholder=True):
        """Return (has_frame, frame) for the specified camera."""
        with self._lock:
            frame = self._frames.get(camera_name)
            last_t = self._last_frame_times.get(camera_name, 0.0)
            fresh = (time.time() - last_t) < 2.5

            if frame is not None and fresh:
                return True, frame.copy()

        if allow_placeholder:
            return True, self._generate_placeholder_frame(camera_name)

        return False, None

    def get_active_frame(self, allow_placeholder=True):
        """Return (has_frame, frame) for current active camera."""
        return self.get_frame(self.active_camera, allow_placeholder=allow_placeholder)

    def get_source_info(self, camera_name=None):
        """Return source type (ROS2/RTSP) and latency/freshness status."""
        cam = camera_name or self.active_camera
        with self._lock:
            fresh = (time.time() - self._last_frame_times.get(cam, 0)) < 2.5
            source = self._source_types.get(cam, "NONE") if fresh else "CONNECTING..."
            return {
                "camera": cam,
                "source": source,
                "connected": fresh,
            }

    # ---------------------------------------------------------------------
    # Localization Accessors & Control Methods
    # ---------------------------------------------------------------------
    def get_localization_data(self) -> dict:
        """Returns a thread-safe copy of the latest localization & sensor data."""
        with self._loc_lock:
            data = dict(self._localization_data)
            now = time.time()
            data["fresh"] = (now - data.get("last_update", 0.0)) < 3.0
            data["has_localization"] = data["has_localization"] and data["fresh"]
            # Copy path array
            data["path"] = list(self._localization_data.get("path", []))
            return data

    def reset_odometry(self):
        """Calls /ductbot/reset_odometry service asynchronously."""
        if not self._cli_reset:
            print("[Bridge] Reset service not available.")
            return False

        def _call():
            try:
                if self._cli_reset.service_is_ready():
                    req = RosTrigger.Request()
                    future = self._cli_reset.call_async(req)
                    future.add_done_callback(lambda f: print(f"[Bridge] Reset Odometry: {f.result().message}"))
                else:
                    print("[Bridge] Reset service not ready.")
            except Exception as e:
                print(f"[Bridge] Reset error: {e}")

        threading.Thread(target=_call, daemon=True).start()
        with self._loc_lock:
            self._localization_data["x"] = 0.0
            self._localization_data["y"] = 0.0
            self._localization_data["path"] = []
        return True

    def pause_tracking(self):
        """Calls /ductbot/pause_tracking service asynchronously."""
        if not self._cli_pause:
            return False

        def _call():
            try:
                if self._cli_pause.service_is_ready():
                    req = RosTrigger.Request()
                    self._cli_pause.call_async(req)
            except Exception as e:
                print(f"[Bridge] Pause tracking error: {e}")

        threading.Thread(target=_call, daemon=True).start()
        return True

    def resume_tracking(self):
        """Calls /ductbot/resume_tracking service asynchronously."""
        if not self._cli_resume:
            return False

        def _call():
            try:
                if self._cli_resume.service_is_ready():
                    req = RosTrigger.Request()
                    self._cli_resume.call_async(req)
            except Exception as e:
                print(f"[Bridge] Resume tracking error: {e}")

        threading.Thread(target=_call, daemon=True).start()
        return True

    # ---------------------------------------------------------------------
    # Video Comparison Accessors & Trigger Methods
    # ---------------------------------------------------------------------
    def get_comparison_status(self) -> dict:
        """Returns the current state of video comparison."""
        with self._comp_lock:
            return dict(self._comparison_state)

    def trigger_video_comparison(self, before_video: str, after_video: str, before_csv: str = None, after_csv: str = None):
        """Publishes a trigger request to /ductbot/trigger_comparison."""
        payload = {
            "before_video": os.path.abspath(before_video),
            "after_video": os.path.abspath(after_video),
        }
        if before_csv:
            payload["before_csv"] = os.path.abspath(before_csv)
        if after_csv:
            payload["after_csv"] = os.path.abspath(after_csv)

        if self._pub_trigger_comp:
            msg = RosString()
            msg.data = json.dumps(payload)
            self._pub_trigger_comp.publish(msg)
            print(f"[Bridge] Published video comparison trigger: {payload}")
            with self._comp_lock:
                self._comparison_state["is_active"] = True
                self._comparison_state["progress_percent"] = 0.0
                self._comparison_state["status"] = "Dispatched comparison to ROS 2 node..."
            return True
        return False

    def stop(self):
        """Stop all workers and cleanup ROS2 and RTSP connections."""
        self.running = False
        threads = list(self._rtsp_threads.values())
        for t in threads:
            t.stop()
        for t in threads:
            try:
                t.join(timeout=0.6)
            except Exception:
                pass
        self._rtsp_threads.clear()
        if self._ros_node:
            try:
                self._ros_node.destroy_node()
            except Exception:
                pass


# Export alias
DuctbotROSBridge = CameraBridge
