#!/usr/bin/env bash
set -e

# Source ROS 2 Humble
if [ -f "/opt/ros/humble/setup.bash" ]; then
    source /opt/ros/humble/setup.bash
fi

# Source ductbot_localization install if built
if [ -f "/app/ductbot-system/ductbot_localization_ros2/install/setup.bash" ]; then
    source /app/ductbot-system/ductbot_localization_ros2/install/setup.bash
fi

# Setup Python paths
export PYTHONPATH="/app/ductbot-system/ductbot_localization_ros2/ductbot_localization:/app/ductbot-system/DuctbotsUI/Basic-Ductbots-main:$PYTHONPATH"
export DUCTBOT_PASSIVE_SERIAL=1

# Ensure runtime directories exist
mkdir -p /app/ductbot-system/DuctbotsUI/Basic-Ductbots-main/videos/merged_videos
mkdir -p /app/ductbot-system/DuctbotsUI/Basic-Ductbots-main/database

# Execute requested command or default launcher
exec "$@"
