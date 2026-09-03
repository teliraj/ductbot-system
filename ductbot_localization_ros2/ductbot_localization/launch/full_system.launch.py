import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():
    pkg_share = get_package_share_directory('ductbot_localization')
    default_params_file = os.path.join(pkg_share, 'config', 'params.yaml')

    port_arg = DeclareLaunchArgument(
        'port',
        default_value='/dev/ttyUSB0',
        description='Serial port for Master ESP32'
    )
    sim_mode_arg = DeclareLaunchArgument(
        'use_sim',
        default_value='false',
        description='Enable simulation mode'
    )

    # 1. Localization Node
    localization_node = Node(
        package='ductbot_localization',
        executable='localization_node',
        name='ductbot_localization_node',
        output='screen',
        parameters=[
            default_params_file,
            {
                'port': LaunchConfiguration('port'),
                'sim_mode': LaunchConfiguration('use_sim')
            }
        ]
    )

    # 2. Video Comparison Node
    video_node = Node(
        package='ductbot_localization',
        executable='video_comparison_node',
        name='ductbot_video_comparison_node',
        output='screen',
        parameters=[default_params_file]
    )

    return LaunchDescription([
        port_arg,
        sim_mode_arg,
        localization_node,
        video_node
    ])
