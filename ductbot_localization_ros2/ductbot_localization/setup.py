import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'ductbot_localization'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
        (os.path.join('share', package_name, 'rviz'), glob('rviz/*.rviz')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Divyansh Jha',
    maintainer_email='divyansh@roboserv4i.com',
    description='ROS 2 Localization, Odometry, IMU, Telemetry, and Video Comparison package for Duct Bot',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'localization_node = ductbot_localization.localization_node:main',
            'mock_serial_publisher = ductbot_localization.mock_serial_publisher:main',
            'video_comparison_node = ductbot_localization.video_comparison_node:main',
        ],
    },
)
