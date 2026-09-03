import math
import time
import numpy as np

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

class MockSerialPublisher(Node):
    """
    Simulates the Master ESP32 serial output at 100Hz.
    
    Generates synthetic telemetry packets formatted identically to Master ESP32:
    ENC1=123 ENC2=456 | ACC: x y z | GYRO: x y z | ANG: r p y | TOFL: 52 TOFR: 48 | ENV: temp hum voc co2 mq2 dust
    
    Trajectory pattern:
    1. Drive straight for 2.0 meters
    2. Turn 90 degrees right
    3. Drive straight for 1.5 meters
    4. Turn 90 degrees right
    5. Loop continuously
    """
    def __init__(self):
        super().__init__('mock_serial_publisher')
        
        self.pub = self.create_publisher(String, '/ductbot/sim_telemetry', 10)
        self.timer_period = 0.01  # 100 Hz
        self.timer = self.create_timer(self.timer_period, self._timer_callback)
        
        self.ticks_per_m = 15055.0
        self.enc1 = 0.0
        self.enc2 = 0.0
        
        self.step = 0
        self.state = 'STRAIGHT_1'
        self.state_step = 0
        self.current_yaw = 90.0  # Physical 90 deg = Engine 0 deg (facing forward)
        
        self.get_logger().info("=== DuctBot Mock Telemetry Publisher Started (100Hz) ===")
        self.get_logger().info("Publishing simulated ESP32 strings to /ductbot/sim_telemetry")

    def _timer_callback(self):
        self.step += 1
        self.state_step += 1
        
        speed_mps = 0.15 # 15 cm/sec
        ticks_per_step = (speed_mps * self.timer_period) * self.ticks_per_m # ~22.5 ticks/step
        
        acc = [0.0, 0.0, 1.0] # 1g on Z
        gyro = [0.0, 0.0, 0.0]
        
        # State Machine
        if self.state == 'STRAIGHT_1':
            # Drive straight for 2.0m (~1333 steps at 100Hz = 13.3s)
            self.enc1 += ticks_per_step
            self.enc2 += ticks_per_step
            gyro = [0.0, 0.0, 0.0]
            if self.state_step >= 1333:
                self.state = 'TURN_1'
                self.state_step = 0
                self.get_logger().info("Sim: Turning Right 90 deg...")

        elif self.state == 'TURN_1':
            # Turn 90 degrees right over 3 seconds (300 steps)
            turn_rate_degps = -30.0 # -30 deg/s
            self.current_yaw += turn_rate_degps * self.timer_period
            # Wheel differential during spot turn
            self.enc1 += 15
            self.enc2 -= 15
            gyro = [0.0, 0.0, -30.0] # deg/s
            if self.state_step >= 300:
                self.current_yaw = 0.0
                self.state = 'STRAIGHT_2'
                self.state_step = 0
                self.get_logger().info("Sim: Driving straight on leg 2...")

        elif self.state == 'STRAIGHT_2':
            # Drive straight for 1.5m (1000 steps = 10s)
            self.enc1 += ticks_per_step
            self.enc2 += ticks_per_step
            gyro = [0.0, 0.0, 0.0]
            if self.state_step >= 1000:
                self.state = 'TURN_2'
                self.state_step = 0
                self.get_logger().info("Sim: Turning Right 90 deg (2nd turn)...")

        elif self.state == 'TURN_2':
            # Turn another 90 degrees right over 3 seconds
            turn_rate_degps = -30.0
            self.current_yaw += turn_rate_degps * self.timer_period
            self.enc1 += 15
            self.enc2 -= 15
            gyro = [0.0, 0.0, -30.0]
            if self.state_step >= 300:
                self.current_yaw = 270.0
                self.state = 'STRAIGHT_1'
                self.state_step = 0
                self.get_logger().info("Sim: Completed loop, driving straight...")

        # Keep yaw in 0-360
        self.current_yaw = self.current_yaw % 360.0
        ang = [0.0, 0.0, self.current_yaw]
        
        # Synthetic ToF range values with slight realistic noise (120mm to left wall, 130mm to right wall)
        tof_l = int(120 + 5 * math.sin(self.step * 0.05))
        tof_r = int(130 - 5 * math.sin(self.step * 0.05))
        
        # Synthetic V3 environmental data: Temp=24.5C, Humidity=48.2%, VOC=115, CO2=425, MQ2=38, Dust=14
        temp = 24.5 + 0.5 * math.sin(self.step * 0.01)
        hum = 48.2 + 0.8 * math.cos(self.step * 0.01)
        voc = 115
        co2 = 425
        mq2 = 38
        dust = 14
        
        # Compile exact serial string matching C6 Master output
        line = (
            f"ENC1={int(self.enc1)} ENC2={int(self.enc2)} | "
            f"ACC: {acc[0]:.2f} {acc[1]:.2f} {acc[2]:.2f} | "
            f"GYRO: {gyro[0]:.2f} {gyro[1]:.2f} {gyro[2]:.2f} | "
            f"ANG: {ang[0]:.2f} {ang[1]:.2f} {ang[2]:.2f} | "
            f"TOFL: {tof_l} TOFR: {tof_r} | "
            f"ENV: {temp:.1f} {hum:.1f} {voc} {co2} {mq2} {dust}"
        )
        
        msg = String()
        msg.data = line
        self.pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = MockSerialPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Stopping Mock Telemetry Publisher...")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
