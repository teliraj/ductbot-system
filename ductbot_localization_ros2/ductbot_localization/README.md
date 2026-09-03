# Duct Bot ROS 2 Localization & Video Comparison Package (`ductbot_localization`)

This package ports the full Duct Bot software stack from `fresh_repo` into a production-ready **ROS 2 Humble** package:
1. **Real-Time Localization & Checkpoint Generation** (`RPi_Localization_Logger`)
2. **Video Localization & DTW Before/After Comparison Engine** (`GUI/video_localization.py`)

---

## 1. Package Architecture

```text
                                 ┌──────────────────────────────────────────────┐
                                 │          Master ESP32 USB Serial             │
                                 └──────────────────────┬───────────────────────┘
                                                        │ (100Hz Telemetry Stream)
                                                        ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     ductbot_localization_node                                         │
│  - Kinematics: Asymmetric Ticks (15055/16260), Backlash (450 ticks), Swept Circular Arc Integration    │
│  - Coordinate Transforms: odom -> base_link -> front_face_link, imu_link, tof_left, tof_right          │
│  - Logs: 10mm spatial checkpoints CSV (14 columns matching V3)                                         │
└────────────┬─────────────┬─────────────┬─────────────┬─────────────┬─────────────┬─────────────────────┘
             │             │             │             │             │             │
             ▼             ▼             ▼             ▼             ▼             ▼
          /odom     /ductbot/pose  /ductbot/path /ductbot/imu  /ductbot/tof/* /ductbot/environment
      (nav_msgs)    (PoseStamped)   (nav_msgs)   (sensor_msgs) (sensor_msgs)    (Float32MultiArray)
                                                                                   │
                                                                                   │ (10mm Checkpoints CSV)
                                                                                   ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    ductbot_video_comparison_node                                      │
│  - Algorithm: Kabsch SE(2) Rigid 2D Alignment + Constrained DTW (Elastic Time-Warping on dYaw & dist)  │
│  - Service: /ductbot/compare_latest_runs (Auto-compares two most recent runs)                          │
│  - Trigger Topic: /ductbot/trigger_comparison (JSON: {"before_video": "...", "after_video": "..."})     │
│  - Progress Topic: /ductbot/video_comparison_progress (Float32: 0-100%)                                │
│  - Output: Side-by-side synchronized video (before_vs_after.mp4) + match_map.json                      │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. ROS 2 Topics Reference (For Jetson Nano / Orin Developers)

| Topic Name | Message Type | Rate | Description |
| :--- | :--- | :--- | :--- |
| **`/odom`** | `nav_msgs/msg/Odometry` | $100\text{ Hz}$ | Robot center $(X,Y,Z)$ in meters, orientation quaternion, linear & angular velocity |
| **`/ductbot/pose`** | `geometry_msgs/msg/PoseStamped` | $100\text{ Hz}$ | Front-face camera position $(X,Y)$ and heading |
| **`/ductbot/path`** | `nav_msgs/msg/Path` | Latched | Visual 3D trajectory trail for RViz display |
| **`/ductbot/imu`** | `sensor_msgs/msg/Imu` | $100\text{ Hz}$ | Fused IMU orientation, angular velocity ($\text{rad/s}$), linear acceleration ($\text{m/s}^2$) |
| **`/ductbot/tof/left`** | `sensor_msgs/msg/Range` | $100\text{ Hz}$ | Left Time-of-Flight wall distance in meters |
| **`/ductbot/tof/right`** | `sensor_msgs/msg/Range` | $100\text{ Hz}$ | Right Time-of-Flight wall distance in meters |
| **`/ductbot/environment`** | `std_msgs/msg/Float32MultiArray` | $100\text{ Hz}$ | `[Temp_C, Humidity_pct, VOC_index, CO2_ppm, MQ2_raw, Dust_raw]` |
| **`/tf`** | `tf2_msgs/msg/TFMessage` | $100\text{ Hz}$ | Dynamic: `odom` $\rightarrow$ `base_link`, Static: `base_link` $\rightarrow$ `front_face_link`, `imu_link`, `tof_left_link`, `tof_right_link` |
| **`/ductbot/video_comparison_progress`** | `std_msgs/msg/Float32` | On event | Video comparison progress percentage ($0.0$ to $100.0\%$) |
| **`/ductbot/video_comparison_status`** | `std_msgs/msg/String` | On event | JSON status string with current stage and details |

---

## 3. ROS 2 Services Reference

| Service Name | Service Type | How to Call | What it Does |
| :--- | :--- | :--- | :--- |
| **`/ductbot/pause_tracking`** | `std_srvs/srv/Trigger` | `ros2 service call /ductbot/pause_tracking std_srvs/srv/Trigger` | Pauses distance accumulation & checkpoint logging |
| **`/ductbot/resume_tracking`** | `std_srvs/srv/Trigger` | `ros2 service call /ductbot/resume_tracking std_srvs/srv/Trigger` | Resumes distance tracking & logging |
| **`/ductbot/reset_odometry`** | `std_srvs/srv/Trigger` | `ros2 service call /ductbot/reset_odometry std_srvs/srv/Trigger` | Resets odometry origin back to $(0,0,0)$ and clears path |
| **`/ductbot/compare_latest_runs`** | `std_srvs/srv/Trigger` | `ros2 service call /ductbot/compare_latest_runs std_srvs/srv/Trigger` | Auto-detects the 2 latest runs in recordings directory and generates side-by-side video |

---

## 4. How to Run in WSL2 / Jetson Orin

### Step 1: Build the Package
```bash
cd ~/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select ductbot_localization
source install/setup.bash
```

### Step 2: Launch Real-Time Localization
* **With Physical Hardware (Master ESP32 USB)**:
  ```bash
  ros2 launch ductbot_localization localization.launch.py port:=/dev/ttyUSB0 baudrate:=115200
  ```
* **In Simulation Mode (No hardware needed)**:
  ```bash
  ros2 launch ductbot_localization localization_sim.launch.py
  ```
* **With 3D RViz2 Visualization**:
  ```bash
  ros2 launch ductbot_localization localization_rviz.launch.py
  ```

### Step 3: Launch Video Comparison Service
```bash
ros2 launch ductbot_localization video_comparison.launch.py
```

### Step 4: Launch Full System (Localization + Video Comparison)
```bash
ros2 launch ductbot_localization full_system.launch.py port:=/dev/ttyUSB0
```

---

## 5. Python Code Template for Jetson Developers

```python
import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from geometry_msgs.msg import PoseStamped
from sensor_msgs.msg import Range, Imu
from std_msgs.msg import Float32MultiArray, String
import json

class JetsonDuctBotClient(Node):
    def __init__(self):
        super().__init__('jetson_ductbot_client')
        
        # Subscriptions
        self.create_subscription(Odometry, '/odom', self.odom_cb, 10)
        self.create_subscription(PoseStamped, '/ductbot/pose', self.pose_cb, 10)
        self.create_subscription(Range, '/ductbot/tof/left', self.tof_l_cb, 10)
        self.create_subscription(Range, '/ductbot/tof/right', self.tof_r_cb, 10)
        self.create_subscription(Float32MultiArray, '/ductbot/environment', self.env_cb, 10)
        
        # Trigger Video Comparison Publisher
        self.trigger_pub = self.create_publisher(String, '/ductbot/trigger_comparison', 10)

    def odom_cb(self, msg: Odometry):
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y
        speed = msg.twist.twist.linear.x

    def pose_cb(self, msg: PoseStamped):
        front_x = msg.pose.position.x
        front_y = msg.pose.position.y

    def tof_l_cb(self, msg: Range):
        left_dist_m = msg.range

    def tof_r_cb(self, msg: Range):
        right_dist_m = msg.range

    def env_cb(self, msg: Float32MultiArray):
        temp, hum, voc, co2, mq2, dust = msg.data

    def trigger_video_comparison(self, before_mp4_path, after_mp4_path):
        payload = json.dumps({
            "before_video": before_mp4_path,
            "after_video": after_mp4_path
        })
        msg = String(data=payload)
        self.trigger_pub.publish(msg)
```
