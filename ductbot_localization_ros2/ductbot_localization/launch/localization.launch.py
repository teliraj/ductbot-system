import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():
    pkg_share = get_package_share_directory('ductbot_localization')
    default_params_file = os.path.join(pkg_share, 'config', 'params.yaml')

    # Declare CLI Arguments
    port_arg = DeclareLaunchArgument(
        'port',
        default_value='/dev/ttyUSB0',
        description='Serial port of Master ESP32 (e.g., /dev/ttyUSB0 or COM3)'
    )
    baud_arg = DeclareLaunchArgument(
        'baudrate',
        default_value='115200',
        description='Baud rate for Master ESP32'
    )
    params_arg = DeclareLaunchArgument(
        'params_file',
        default_value=default_params_file,
        description='Path to YAML parameter file'
    )

    # Localization Node
    localization_node = Node(
        package='ductbot_localization',
        executable='localization_node',
        name='ductbot_localization_node',
        output='screen',
        parameters=[
            LaunchConfiguration('params_file'),
            {
                'port': LaunchConfiguration('port'),
                'baudrate': LaunchConfiguration('baudrate'),
                'sim_mode': False
            }
        ]
    )

    return LaunchDescription([
        port_arg,
        baud_arg,
        params_arg,
        localization_node
    ])
