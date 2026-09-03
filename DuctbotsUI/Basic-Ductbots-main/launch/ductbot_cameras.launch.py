import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():
    front_rtsp_default = "rtsp://admin:dvr%40robo4i@192.168.1.130:554/cam/realmonitor?channel=1&subtype=0"
    rear_rtsp_default = "rtsp://admin:dvr%40robo4i@192.168.1.130:554/cam/realmonitor?channel=2&subtype=0"

    return LaunchDescription([
        # Launch Arguments
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
        DeclareLaunchArgument(
            'latency_ms',
            default_value='100',
            description='RTSP buffer latency in ms'
        ),

        # Front Camera Node
        Node(
            package='ductbot_core',
            executable='camera_node',
            name='camera_front',
            parameters=[{
                'rtsp_url': LaunchConfiguration('front_rtsp_url'),
                'topic_name': '/ductbot/camera/front',
                'frame_id': 'camera_front_optical_frame',
                'latency_ms': LaunchConfiguration('latency_ms')
            }],
            output='screen'
        ),

        # Rear Camera Node
        Node(
            package='ductbot_core',
            executable='camera_node',
            name='camera_rear',
            parameters=[{
                'rtsp_url': LaunchConfiguration('rear_rtsp_url'),
                'topic_name': '/ductbot/camera/rear',
                'frame_id': 'camera_rear_optical_frame',
                'latency_ms': LaunchConfiguration('latency_ms')
            }],
            output='screen'
        ),
    ])
