# DuctBot Inspection & Localization System

An integrated robotics and touchscreen inspection dashboard for **4i Roboserv** HVAC and industrial duct-cleaning inspection robots.

---

## 🌟 Overview

The **DuctBot System** provides real-time robot teleoperation, localization, sensor telemetry visualization, and dual-camera inspection monitoring. It includes automated Pre-Inspection ("Before") and Post-Inspection ("After") recording comparison powered by Dynamic Time Warping (DTW) and Kabsch trajectory alignment.

### Key Components

1. **Ductbots UI (`DuctbotsUI/Basic-Ductbots-main`)**
   - Modern dark-themed touchscreen dashboard built with Kivy.
   - Dual-camera live streaming (Front and Rear RTSP streams with instantaneous switching).
   - Side-by-side **Before** and **After** cleaning inspection playback panes.
   - Integrated touchscreen virtual on-screen keyboard for field operator input.
   - USB export modal with automatic drive detection, folder creation, and progress tracking.
   - Solid, high-contrast modal dialog styling.

2. **DuctBot Localization (`ductbot_localization_ros2/ductbot_localization`)**
   - ROS 2 Humble package for dead-reckoning kinematics and wheel odometry.
   - Master ESP32 serial telemetry parser (wheel encoders, IMU, dual TOF distance sensors).
   - DTW temporal alignment and Kabsch 2D rigid registration for synchronized Before vs. After comparison videos.
   - TrueType anti-aliased HUD overlay rendering for video export.

3. **System Launch Orchestrator (`run_system.sh`)**
   - Single-command automated hardware detection (`/dev/ttyUSB0` / `/dev/ttyACM0`).
   - Seamless coordination between ROS 2 localization nodes and Kivy UI.
   - Simulation fallback mode (`sim_mode:=true`) when no hardware is attached.

---

## 📁 Repository Structure

```
ductbot-system/
├── DuctbotsUI/
│   └── Basic-Ductbots-main/
│       ├── app.py                      # Main Kivy application & UI lifecycle
│       ├── dashboard_ui.py             # UI design system, virtual keyboard & overlays
│       ├── controls.py                 # Bottom control bar & playback status panel
│       ├── esp32_reader.py             # Telemetry reader & ROS 2 sensor publisher
│       ├── ros_bridge.py               # ROS 2 camera & localization bridge
│       ├── launch/                     # ROS 2 launch files
│       │   ├── ductbot_full_system.launch.py
│       │   └── ductbot_cameras.launch.py
│       ├── database/                   # SQLite inspection recordings database
│       └── videos/                     # Inspection recordings & comparisons
├── ductbot_localization_ros2/
│   └── ductbot_localization/           # ROS 2 Humble Package
│       ├── package.xml
│       ├── setup.py
│       └── ductbot_localization/
│           ├── localization_node.py    # Odometry, kinematics & serial communication
│           ├── video_localization.py   # DTW & Kabsch video comparison pipeline
│           ├── video_comparison_node.py# ROS 2 video comparison service node
│           └── checkpoint_logger.py    # Spatial checkpoint logger
├── run_system.sh                       # Top-level one-command launch script
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites
- **OS**: Ubuntu 22.04 LTS (Jammy Jellyfish)
- **ROS 2**: Humble Hawksbill
- **Python**: 3.10+
- **Kivy**: 2.3.0+
- **OpenCV & SciPy**: OpenCV 4.x, SciPy, Pillow, NumPy

### Dependencies Installation
```bash
sudo apt update
sudo apt install -y python3-pip python3-kivy libgl1-mesa-dev libgles2-mesa-dev
pip install opencv-python pillow scipy numpy pyserial
```

### Build ROS 2 Package (Optional if already built)
```bash
cd ductbot_localization_ros2
colcon build --symlink-install
source install/setup.bash
cd ..
```

### Run the System
Simply execute the launch script from the repository root:
```bash
./run_system.sh
```

---

## 🎮 Features & Usage

### 1. Live Inspection HUD
- Displays camera view with **LIVE MODE - FRONT** or **LIVE MODE - REAR** status badge.
- Live telemetry indicators: Left/Right TOF wall distance, robot speed, odometry distance.
- One-touch camera toggle (`CAM: FRONT` / `CAM: REAR`).

### 2. Pre & Post-Inspection Recording
- Tap **START RECORDING** to open the centered dialog.
- Type Client Name, Area, and Side/Site using the integrated on-screen touchscreen keyboard.
- Select condition (**Before** cleaning or **After** cleaning).

### 3. Before vs. After Video Comparison
- Switch to the **Comparison** tab or select matching Before & After runs in **Playback**.
- Automated Dynamic Time Warping aligns video frames spatially by traveled duct distance.
- Generates side-by-side synchronized comparison video with sharp TrueType typography badges.

### 4. USB Export
- Select completed recordings from Playback.
- Insert a USB flash drive.
- Dialog automatically resolves clean drive names and allows typing custom folder names via on-screen keyboard.

---

## 🔒 License & Ownership
Copyright © 2026 **4i Roboserv**. All rights reserved.
Proprietary industrial software developed for DuctBot robotic duct-inspection systems.
