#!/usr/bin/env bash
set -e

# Determine script root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source ROS 2 Humble environment
if [ -f "/opt/ros/humble/setup.bash" ]; then
    source /opt/ros/humble/setup.bash
fi

# Source ductbot_localization package if built in repo or local workspace
if [ -f "$SCRIPT_DIR/ductbot_localization_ros2/install/setup.bash" ]; then
    source "$SCRIPT_DIR/ductbot_localization_ros2/install/setup.bash"
elif [ -f "/home/roboserv-4i/Downloads/ductbot_localization_ros2/install/setup.bash" ]; then
    source "/home/roboserv-4i/Downloads/ductbot_localization_ros2/install/setup.bash"
fi

# Set python search path
export PYTHONPATH="$SCRIPT_DIR/ductbot_localization_ros2/ductbot_localization:$SCRIPT_DIR/DuctbotsUI/Basic-Ductbots-main:/home/roboserv-4i/Downloads/ductbot_localization_ros2/ductbot_localization:/home/roboserv-4i/Downloads/DuctbotsUI/Basic-Ductbots-main:$PYTHONPATH"
export DUCTBOT_PASSIVE_SERIAL=1

LAUNCH_FILE="$SCRIPT_DIR/DuctbotsUI/Basic-Ductbots-main/launch/ductbot_full_system.launch.py"

# Auto-detect serial port
if [ -e "/dev/ttyUSB0" ]; then
    SERIAL_PORT="/dev/ttyUSB0"
    echo "[DuctBot Launch] Hardware serial detected on $SERIAL_PORT. Starting DuctBot full system..."
    ros2 launch "$LAUNCH_FILE" port:="$SERIAL_PORT" "$@"
elif [ -e "/dev/ttyACM0" ]; then
    SERIAL_PORT="/dev/ttyACM0"
    echo "[DuctBot Launch] Hardware serial detected on $SERIAL_PORT. Starting DuctBot full system..."
    ros2 launch "$LAUNCH_FILE" port:="$SERIAL_PORT" "$@"
else
    echo "[DuctBot Launch] No serial port detected. Starting with sim_mode:=true..."
    ros2 launch "$LAUNCH_FILE" sim_mode:=true "$@"
fi
