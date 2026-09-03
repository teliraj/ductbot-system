import os
import sys
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.substitutions import LaunchConfiguration
from launch.conditions import IfCondition
from launch_ros.actions import Node

def generate_launch_description():
    ui_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    ui_script_path = os.path.join(ui_dir, 'app.py')

    front_rtsp_default = "rtsp://admin:dvr%40robo4i@192.168.1.130:554/cam/realmonitor?channel=1&subtype=0"
    rear_rtsp_default = "rtsp://admin:dvr%40robo4i@192.168.1.130:554/cam/realmonitor?channel=2&subtype=0"

    return LaunchDescription([
        # Hardware Serial Arguments
        DeclareLaunchArgument(
            'port',
            default_value='/dev/ttyUSB0',
            description='Serial port for Master ESP32 telemetry'
        ),
        DeclareLaunchArgument(
            'baudrate',
            default_value='115200',
            description='Baud rate for Master ESP32'
        ),
        DeclareLaunchArgument(
            'sim_mode',
            default_value='false',
            description='Enable simulation mode for localization'
        ),
        DeclareLaunchArgument(
            'launch_ui',
            default_value='true',
            description='Whether to launch the Ductbots Kivy UI automatically'
        ),

        # Camera RTSP Arguments
        DeclareLaunchArgument(
            'front_rtsp_url',
            default_value=front_rtsp_default,
            description='RTSP URL for front camera'
        ),
        DeclareLaunchArgument(
            'rear_rtsp_url',
            default_value=rear_rtsp_default,
            description='RTSP URL for rear camera'
        ),

        # 1. DuctBot Localization Node (Kinematics, Odometry, TF, Checkpoints)
        Node(
            package='ductbot_localization',
            executable='localization_node',
            name='ductbot_localization_node',
            output='screen',
            parameters=[{
                'port': LaunchConfiguration('port'),
                'baudrate': LaunchConfiguration('baudrate'),
                'sim_mode': LaunchConfiguration('sim_mode'),
                'publish_tf': True,
                'enable_checkpoint_logging': True,
            }]
        ),

        # 2. DuctBot Video Comparison Node (DTW Kabsch alignment service & topics)
        Node(
            package='ductbot_localization',
            executable='video_comparison_node',
            name='ductbot_video_comparison_node',
            output='screen',
            parameters=[{
                'recordings_dir': os.path.join(ui_dir, 'videos'),
                'resample_spacing_m': 0.02,
            }]
        ),

        # 3. Ductbots UI Process
        ExecuteProcess(
            condition=IfCondition(LaunchConfiguration('launch_ui')),
            cmd=[sys.executable, ui_script_path],
            output='screen'
        )
    ])
