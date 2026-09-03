import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():
    pkg_share = get_package_share_directory('ductbot_localization')
    default_params_file = os.path.join(pkg_share, 'config', 'params.yaml')
    default_rviz_config = os.path.join(pkg_share, 'rviz', 'ductbot_view.rviz')

    use_sim_arg = DeclareLaunchArgument(
        'use_sim',
        default_value='true',
        description='Launch with mock telemetry publisher'
    )
    port_arg = DeclareLaunchArgument(
        'port',
        default_value='/dev/ttyUSB0',
        description='Physical serial port if use_sim is false'
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

    # 2. Mock Publisher
    mock_node = Node(
        package='ductbot_localization',
        executable='mock_serial_publisher',
        name='mock_serial_publisher',
        output='screen'
    )

    # 3. RViz2 Node
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=['-d', default_rviz_config],
        output='screen'
    )

    return LaunchDescription([
        use_sim_arg,
        port_arg,
        localization_node,
        mock_node,
        rviz_node
    ])
