"""
ESP32 Sensor Telemetry Serial Reader & ROS2 Publisher for Ductbots.
Auto-detects ESP32 connected via USB (/dev/ttyACM*, /dev/ttyUSB*), parses
real-time IMU, Encoders, Speed/Odometry, TOF distance, and Environmental sensor metrics,
and publishes them to dedicated ROS2 topics as well as keeping a thread-safe cache.

Kinematics Specification:
- Wheel Radius: 50 mm (0.05 m) -> Diameter: 100 mm (0.10 m)
- Wheel Circumference: 2 * pi * 0.05 m = 0.314159265 m
- Base Motor: 5800 RPM, Gear Ratio: 1:30
- Encoder: Quad 13 PPR -> 52 CPR at motor shaft
- CPR at Output Shaft / Wheel: 52 * 30 = 1560 ticks / revolution
- Ticks per Meter: 1560 / (2 * pi * 0.05) = 4965.6341775 ticks / meter (4.9656 ticks / mm)
"""

import os
import sys
import math
import time
import json
import glob
import threading
import serial

# Mechanical and Kinematic Constants
WHEEL_RADIUS_M = 0.050                          # 50 mm radius (100 mm diameter)
WHEEL_CIRCUMFERENCE_M = 2.0 * math.pi * WHEEL_RADIUS_M  # ~0.314159265 m (314.16 mm)
MOTOR_PPR = 13.0                                # Pulses per revolution
QUAD_CPR = MOTOR_PPR * 4.0                      # 52 CPR at motor shaft
GEAR_RATIO = 90.0                               # 1:90 Gearbox reduction
OUTPUT_CPR = QUAD_CPR * GEAR_RATIO              # 4680 ticks per wheel revolution
TICKS_PER_METER_DEFAULT = OUTPUT_CPR / WHEEL_CIRCUMFERENCE_M  # ~14896.90253 ticks/m (14.897 ticks/mm)

# Ensure ductbot_localization package from Downloads is prioritized on sys.path
_DOWNLOADS_PKG_DIR = "/home/roboserv-4i/Downloads/ductbot_localization_ros2/ductbot_localization"
if os.path.exists(_DOWNLOADS_PKG_DIR):
    if _DOWNLOADS_PKG_DIR in sys.path:
        sys.path.remove(_DOWNLOADS_PKG_DIR)
    sys.path.insert(0, _DOWNLOADS_PKG_DIR)

try:
    from ductbot_localization.localization_engine import LocalizationEngine
    LOCALIZATION_ENGINE_AVAILABLE = True
except Exception:
    LOCALIZATION_ENGINE_AVAILABLE = False

ROS2_AVAILABLE = False
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
    try:
        from std_msgs.msg import Float32, String, Int32
        from sensor_msgs.msg import Temperature, RelativeHumidity, Imu, Range
        from geometry_msgs.msg import Vector3
    except ImportError:
        Float32 = None
        String = None
        Temperature = None
        RelativeHumidity = None
        Imu = None
        Vector3 = None
    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False


class ESP32Reader(threading.Thread):
    """
    Background worker thread that connects to ESP32 via serial,
    continuously reads lines, parses telemetry data, calculates speed/odometry
    using exact robot kinematics, and publishes to individual ROS2 topics.
    """

    def __init__(self, port=None, baudrate=115200, enable_ros2=True):
        super().__init__(daemon=True, name="ESP32-Telemetry-Reader")
        self.explicit_port = port
        self.baudrate = baudrate
        self.enable_ros2 = enable_ros2 and ROS2_AVAILABLE
        self.running = True
        self.ser = None
        self._lock = threading.Lock()
        self._external_active = False
        self.passive_mode = os.environ.get("DUCTBOT_PASSIVE_SERIAL", "0") == "1"

        # Odometry configuration
        self.ticks_per_meter = float(os.environ.get("DUCTBOT_TICKS_PER_METER", str(TICKS_PER_METER_DEFAULT)))
        self._last_enc1 = None
        self._last_enc2 = None
        self._last_enc_time = 0.0
        self._smooth_speed = 0.0

        # Telemetry State
        self.telemetry = {
            "connected": False,
            "port": "None",
            "last_update": 0.0,
            # Position
            "x": 0.0,
            "y": 0.0,
            # Encoders & Speed Odometry
            "ENC1": 0.0,
            "ENC2": 0.0,
            "speed_mps": 0.0,          # Meters per second (m/s)
            "speed_cmps": 0.0,         # Centimeters per second (cm/s)
            "speed_m_min": 0.0,        # Meters per minute (m/min)
            "wheel_rpm": 0.0,          # Wheel RPM
            "total_distance_m": 0.0,   # Total forward distance (meters)
            "left_distance_m": 0.0,    # Left wheel distance (meters)
            "right_distance_m": 0.0,   # Right wheel distance (meters)
            # IMU Acceleration (g)
            "acc_x": 0.0,
            "acc_y": 0.0,
            "acc_z": 1.0,
            # IMU Gyro (deg/s)
            "gyro_x": 0.0,
            "gyro_y": 0.0,
            "gyro_z": 0.0,
            # Robot Orientation / Tilt (degrees)
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 0.0,
            # Time of Flight Distance Sensors (mm)
            "TOF_L": 0.0,
            "TOF_R": 0.0,
            # Environmental Metrics
            "temperature": 0.0,   # °C
            "humidity": 0.0,      # % RH
            "air_quality": 0.0,   # AQI / VOC
            "pressure": 0.0,      # hPa
            "gas_ppm": 0.0,       # PPM
            "status_code": 0
        }

        # ROS2 Node & Publishers
        self.ros_node = None
        self.pubs = {}
        if self.enable_ros2:
            self._init_ros2_publishers()

    def _init_ros2_publishers(self):
        try:
            if not rclpy.ok():
                rclpy.init(args=None)
            self.ros_node = Node("ductbot_esp32_sensor_publisher")
            qos = QoSProfile(
                reliability=ReliabilityPolicy.RELIABLE,
                history=HistoryPolicy.KEEP_LAST,
                depth=10
            )

            if Float32:
                self.pubs["temp_f32"] = self.ros_node.create_publisher(Float32, "/ductbot/sensors/temperature", qos)
                self.pubs["hum_f32"] = self.ros_node.create_publisher(Float32, "/ductbot/sensors/humidity", qos)
                self.pubs["aqi"] = self.ros_node.create_publisher(Float32, "/ductbot/sensors/air_quality", qos)
                self.pubs["gas_ppm"] = self.ros_node.create_publisher(Float32, "/ductbot/sensors/gas_ppm", qos)
                self.pubs["pressure"] = self.ros_node.create_publisher(Float32, "/ductbot/sensors/pressure", qos)
                self.pubs["tof_l"] = self.ros_node.create_publisher(Float32, "/ductbot/sensors/tof_left", qos)
                self.pubs["tof_r"] = self.ros_node.create_publisher(Float32, "/ductbot/sensors/tof_right", qos)
                self.pubs["speed"] = self.ros_node.create_publisher(Float32, "/ductbot/robot/speed", qos)
                self.pubs["distance"] = self.ros_node.create_publisher(Float32, "/ductbot/robot/distance", qos)

            if Vector3:
                self.pubs["orientation"] = self.ros_node.create_publisher(Vector3, "/ductbot/sensors/orientation", qos)
                self.pubs["accel"] = self.ros_node.create_publisher(Vector3, "/ductbot/sensors/acceleration", qos)
                self.pubs["gyro"] = self.ros_node.create_publisher(Vector3, "/ductbot/sensors/gyro", qos)
                self.pubs["encoders"] = self.ros_node.create_publisher(Vector3, "/ductbot/sensors/encoders", qos)

            if String:
                self.pubs["json"] = self.ros_node.create_publisher(String, "/ductbot/sensors/telemetry_json", qos)

            print("[ESP32Reader] Initialized ROS2 Sensor & Robot Speed Publishers on /ductbot/*")
        except Exception as e:
            print(f"[ESP32Reader] ROS2 publisher init error: {e}")
            self.ros_node = None

    def _publish_ros2(self, data: dict):
        if not self.ros_node:
            return
        try:
            if "temp_f32" in self.pubs:
                m = Float32()
                m.data = float(data.get("temperature", 0.0))
                self.pubs["temp_f32"].publish(m)

            if "hum_f32" in self.pubs:
                m = Float32()
                m.data = float(data.get("humidity", 0.0))
                self.pubs["hum_f32"].publish(m)

            if "aqi" in self.pubs:
                m = Float32()
                m.data = float(data.get("air_quality", 0.0))
                self.pubs["aqi"].publish(m)

            if "gas_ppm" in self.pubs:
                m = Float32()
                m.data = float(data.get("gas_ppm", 0.0))
                self.pubs["gas_ppm"].publish(m)

            if "pressure" in self.pubs:
                m = Float32()
                m.data = float(data.get("pressure", 0.0))
                self.pubs["pressure"].publish(m)

            if "tof_l" in self.pubs:
                m = Float32()
                m.data = float(data.get("TOF_L", 0.0))
                self.pubs["tof_l"].publish(m)

            if "tof_r" in self.pubs:
                m = Float32()
                m.data = float(data.get("TOF_R", 0.0))
                self.pubs["tof_r"].publish(m)

            if "speed" in self.pubs:
                m = Float32()
                m.data = float(data.get("speed_mps", 0.0))
                self.pubs["speed"].publish(m)

            if "distance" in self.pubs:
                m = Float32()
                m.data = float(data.get("total_distance_m", 0.0))
                self.pubs["distance"].publish(m)

            if "orientation" in self.pubs:
                v = Vector3()
                v.x = float(data.get("roll", 0.0))
                v.y = float(data.get("pitch", 0.0))
                v.z = float(data.get("yaw", 0.0))
                self.pubs["orientation"].publish(v)

            if "encoders" in self.pubs:
                v = Vector3()
                v.x = float(data.get("ENC1", 0.0))
                v.y = float(data.get("ENC2", 0.0))
                v.z = float(data.get("speed_mps", 0.0))
                self.pubs["encoders"].publish(v)

            if "json" in self.pubs:
                s = String()
                s.data = json.dumps(data)
                self.pubs["json"].publish(s)

        except Exception:
            pass

    def _find_esp32_port(self):
        if self.explicit_port and os.path.exists(self.explicit_port):
            return self.explicit_port

        # Search /dev/ttyACM* and /dev/ttyUSB*
        candidates = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))
        for p in candidates:
            if os.path.exists(p):
                return p
        return None

    def _parse_line(self, line: str):
        parts = line.strip().split('|')
        updates = {}
        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Encoders: ENC1=0 ENC2=0
            if 'ENC1=' in part or 'ENC2=' in part:
                tokens = part.split()
                for tok in tokens:
                    if '=' in tok:
                        k, v = tok.split('=', 1)
                        try:
                            updates[k] = float(v)
                        except ValueError:
                            pass

            # Acceleration: ACC: 0.00 0.03 1.00
            elif part.startswith('ACC:'):
                vals = part.replace('ACC:', '').strip().split()
                if len(vals) >= 3:
                    try:
                        updates['acc_x'] = float(vals[0])
                        updates['acc_y'] = float(vals[1])
                        updates['acc_z'] = float(vals[2])
                    except ValueError:
                        pass

            # Gyro: GYRO: 0.00 0.00 0.00
            elif part.startswith('GYRO:'):
                vals = part.replace('GYRO:', '').strip().split()
                if len(vals) >= 3:
                    try:
                        updates['gyro_x'] = float(vals[0])
                        updates['gyro_y'] = float(vals[1])
                        updates['gyro_z'] = float(vals[2])
                    except ValueError:
                        pass

            # Robot Angle / Orientation: ANG: 1.79 -0.35 0.10
            elif part.startswith('ANG:'):
                vals = part.replace('ANG:', '').strip().split()
                if len(vals) >= 3:
                    try:
                        updates['roll'] = float(vals[0])
                        updates['pitch'] = float(vals[1])
                        updates['yaw'] = float(vals[2])
                    except ValueError:
                        pass

            # TOF Sensors: TOFL: 274 TOFR: -2
            elif 'TOFL:' in part or 'TOFR:' in part:
                tokens = part.split()
                i = 0
                while i < len(tokens):
                    if tokens[i].startswith('TOFL:'):
                        v = tokens[i].replace('TOFL:', '') or (tokens[i+1] if i+1 < len(tokens) else '0')
                        try:
                            updates['TOF_L'] = float(v)
                        except ValueError:
                            pass
                    elif tokens[i].startswith('TOFR:'):
                        v = tokens[i].replace('TOFR:', '') or (tokens[i+1] if i+1 < len(tokens) else '0')
                        try:
                            updates['TOF_R'] = float(v)
                        except ValueError:
                            pass
                    i += 1

            # Environmental Sensors: ENV: 26.80 71.90 49 870 23 0
            elif part.startswith('ENV:'):
                vals = part.replace('ENV:', '').strip().split()
                if len(vals) >= 2:
                    try:
                        updates['temperature'] = float(vals[0])
                        updates['humidity'] = float(vals[1])
                        if len(vals) > 2:
                            updates['air_quality'] = float(vals[2])
                        if len(vals) > 3:
                            updates['pressure'] = float(vals[3])
                        if len(vals) > 4:
                            updates['gas_ppm'] = float(vals[4])
                        if len(vals) > 5:
                            updates['status_code'] = int(vals[5])
                    except ValueError:
                        pass

        # Calculate exact speed and odometry from encoder ticks
        if "ENC1" in updates or "ENC2" in updates:
            enc1 = updates.get("ENC1", self.telemetry.get("ENC1", 0.0))
            enc2 = updates.get("ENC2", self.telemetry.get("ENC2", 0.0))
            now = time.time()

            # Cumulative distance in meters
            left_m = enc1 / self.ticks_per_meter
            right_m = enc2 / self.ticks_per_meter
            total_dist_m = (left_m + right_m) / 2.0

            updates["left_distance_m"] = round(left_m, 3)
            updates["right_distance_m"] = round(right_m, 3)
            updates["total_distance_m"] = round(total_dist_m, 3)

            if self._last_enc_time > 0 and (now - self._last_enc_time) > 0.005:
                dt = now - self._last_enc_time
                d_enc1 = enc1 - (self._last_enc1 if self._last_enc1 is not None else enc1)
                d_enc2 = enc2 - (self._last_enc2 if self._last_enc2 is not None else enc2)

                if d_enc1 == 0 and d_enc2 == 0:
                    # Decelerate / drop to 0 when stationary
                    self._smooth_speed = 0.0
                else:
                    avg_dticks = (d_enc1 + d_enc2) / 2.0
                    dist_delta = avg_dticks / self.ticks_per_meter
                    raw_speed = dist_delta / dt

                    # Exponential Moving Average filter
                    self._smooth_speed = 0.65 * self._smooth_speed + 0.35 * raw_speed

                speed_mps = round(self._smooth_speed, 3)
                updates["speed_mps"] = speed_mps
                updates["speed_cmps"] = round(speed_mps * 100.0, 1)
                updates["speed_m_min"] = round(speed_mps * 60.0, 1)
                updates["wheel_rpm"] = round((speed_mps * 60.0) / WHEEL_CIRCUMFERENCE_M, 1)

            self._last_enc1 = enc1
            self._last_enc2 = enc2
            self._last_enc_time = now

        if updates:
            with self._lock:
                self.telemetry.update(updates)
                self.telemetry["last_update"] = time.time()
                self.telemetry["connected"] = True
                curr_data = dict(self.telemetry)

            # Publish to ROS2 topics
            if self.enable_ros2:
                self._publish_ros2(curr_data)

    def update_from_bridge(self, data: dict):
        """Updates internal telemetry cache from ROS 2 localization bridge."""
        if not data or not data.get("has_localization", False):
            return
        with self._lock:
            self._external_active = True
            if "total_distance_m" in data and float(data["total_distance_m"]) > 0.0:
                self.telemetry["total_distance_m"] = round(float(data["total_distance_m"]), 3)
            elif "x" in data and "y" in data:
                self.telemetry["total_distance_m"] = round(math.sqrt(data["x"]**2 + data["y"]**2), 3)

            if "linear_speed" in data:
                spd = float(data["linear_speed"])
                self.telemetry["speed_mps"] = spd
                self.telemetry["speed_cmps"] = round(spd * 100.0, 1)
                self.telemetry["speed_m_min"] = round(spd * 60.0, 1)
            for k in ("x", "y", "roll", "pitch", "yaw", "TOF_L", "TOF_R", "temperature", "humidity", "air_quality", "gas_ppm", "pressure", "status_code"):
                if k in data:
                    self.telemetry[k] = data[k]
            self.telemetry["connected"] = True
            self.telemetry["port"] = "ROS2 (/odom)"
            self.telemetry["last_update"] = time.time()

    def run(self):
        if self.passive_mode:
            print("[ESP32Reader] Passive bridge mode active (serial port owned exclusively by ROS 2 localization node).")
            while self.running:
                time.sleep(0.5)
            return

        last_log_time = 0.0
        while self.running:
            # If external ROS 2 localization is active, yield the serial port to prevent conflicts
            if self._external_active and (time.time() - self.telemetry.get("last_update", 0.0)) < 3.0:
                if self.ser:
                    try:
                        self.ser.close()
                    except Exception:
                        pass
                    self.ser = None
                time.sleep(0.25)
                continue

            port = self._find_esp32_port()
            if not port:
                with self._lock:
                    if not self._external_active:
                        self.telemetry["connected"] = False
                        self.telemetry["port"] = "None"
                now = time.time()
                if now - last_log_time > 10.0:
                    print("[ESP32Reader] Searching for ESP32 serial port (/dev/ttyACM*, /dev/ttyUSB*)...")
                    last_log_time = now
                time.sleep(2.0)
                continue

            try:
                self.ser = serial.Serial(port, self.baudrate, timeout=1.0)
                with self._lock:
                    self.telemetry["port"] = port
                    self.telemetry["connected"] = True
                print(f"[ESP32Reader] Connected to ESP32 on {port} @ {self.baudrate} baud.")

                while self.running:
                    # Check if external ROS 2 localization started
                    if self._external_active and (time.time() - self.telemetry.get("last_update", 0.0)) < 3.0:
                        print("[ESP32Reader] Yielding serial port to active ROS 2 localization node.")
                        break

                    line = self.ser.readline()
                    if line:
                        try:
                            decoded = line.decode('utf-8', errors='replace').strip()
                            if decoded:
                                self._parse_line(decoded)
                        except Exception:
                            pass
                    else:
                        # Check if connection timed out
                        if time.time() - self.telemetry["last_update"] > 3.0:
                            with self._lock:
                                self.telemetry["connected"] = False

            except Exception as e:
                with self._lock:
                    if not self._external_active:
                        self.telemetry["connected"] = False
                print(f"[ESP32Reader] Serial error on {port}: {e}")
                time.sleep(2.0)
            finally:
                if self.ser:
                    try:
                        self.ser.close()
                    except Exception:
                        pass
                    self.ser = None

    def get_telemetry(self) -> dict:
        """Returns a thread-safe copy of the latest telemetry dictionary."""
        with self._lock:
            data = dict(self.telemetry)
            data["fresh"] = (time.time() - data.get("last_update", 0.0)) < 3.0
            return data

    def stop(self):
        self.running = False
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
        if self.ros_node:
            try:
                self.ros_node.destroy_node()
            except Exception:
                pass


# Global singleton instance
_esp32_reader_instance = None

def get_esp32_reader(port=None, baudrate=115200) -> ESP32Reader:
    global _esp32_reader_instance
    if _esp32_reader_instance is None:
        _esp32_reader_instance = ESP32Reader(port=port, baudrate=baudrate)
        _esp32_reader_instance.start()
    return _esp32_reader_instance
