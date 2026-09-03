import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():
    pkg_share = get_package_share_directory('ductbot_localization')
    default_params_file = os.path.join(pkg_share, 'config', 'params.yaml')

    params_arg = DeclareLaunchArgument(
        'params_file',
        default_value=default_params_file,
        description='Path to YAML parameter file'
    )

    video_comparison_node = Node(
        package='ductbot_localization',
        executable='video_comparison_node',
        name='ductbot_video_comparison_node',
        output='screen',
        parameters=[LaunchConfiguration('params_file')]
    )

    return LaunchDescription([
        params_arg,
        video_comparison_node
    ])
