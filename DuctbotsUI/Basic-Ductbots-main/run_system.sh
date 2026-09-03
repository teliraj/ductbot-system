#!/usr/bin/env bash
set -e

# Source ROS 2 Humble environment
source /opt/ros/humble/setup.bash

# Source ductbot_localization package if built
if [ -f "/home/roboserv-4i/Downloads/ductbot_localization_ros2/install/setup.bash" ]; then
    source "/home/roboserv-4i/Downloads/ductbot_localization_ros2/install/setup.bash"
fi

# Set python search path
export PYTHONPATH="/home/roboserv-4i/Downloads/ductbot_localization_ros2/ductbot_localization:/home/roboserv-4i/Downloads/DuctbotsUI/Basic-Ductbots-main:$PYTHONPATH"
export DUCTBOT_PASSIVE_SERIAL=1

# Auto-detect serial port
if [ -e "/dev/ttyUSB0" ]; then
    SERIAL_PORT="/dev/ttyUSB0"
    echo "[DuctBot Launch] Hardware serial detected on $SERIAL_PORT. Starting DuctBot full system..."
    ros2 launch /home/roboserv-4i/Downloads/DuctbotsUI/Basic-Ductbots-main/launch/ductbot_full_system.launch.py port:="$SERIAL_PORT" "$@"
elif [ -e "/dev/ttyACM0" ]; then
    SERIAL_PORT="/dev/ttyACM0"
    echo "[DuctBot Launch] Hardware serial detected on $SERIAL_PORT. Starting DuctBot full system..."
    ros2 launch /home/roboserv-4i/Downloads/DuctbotsUI/Basic-Ductbots-main/launch/ductbot_full_system.launch.py port:="$SERIAL_PORT" "$@"
else
    echo "[DuctBot Launch] No serial port detected. Starting with sim_mode:=true..."
    ros2 launch /home/roboserv-4i/Downloads/DuctbotsUI/Basic-Ductbots-main/launch/ductbot_full_system.launch.py sim_mode:=true "$@"
fi
