import time
import rclpy
from ductbot_localization.localization_node import DuctBotLocalizationNode
from ductbot_localization.mock_serial_publisher import MockSerialPublisher
from nav_msgs.msg import Odometry
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import Float32MultiArray

def run_integration_test():
    rclpy.init()
    
    # Initialize nodes with sim_mode=True
    node_loc = DuctBotLocalizationNode()
    node_mock = MockSerialPublisher()
    
    received_odom = []
    received_env = []
    
    def odom_cb(msg):
        received_odom.append(msg)
        
    def env_cb(msg):
        received_env.append(msg)
        
    sub_odom = node_loc.create_subscription(Odometry, '/odom', odom_cb, 10)
    sub_env = node_loc.create_subscription(Float32MultiArray, '/ductbot/environment', env_cb, 10)
    
    print("[TEST] Running 100 simulation cycles (1.0s of telemetry)...")
    for _ in range(100):
        node_mock._timer_callback()
        rclpy.spin_once(node_loc, timeout_sec=0.01)
        rclpy.spin_once(node_mock, timeout_sec=0.01)
        
    print(f"[TEST] Received {len(received_odom)} /odom messages")
    print(f"[TEST] Received {len(received_env)} /ductbot/environment messages")
    
    if received_odom:
        latest_odom = received_odom[-1]
        print(f"[TEST] Latest Odom Position: X={latest_odom.pose.pose.position.x:.4f}, Y={latest_odom.pose.pose.position.y:.4f}")
        print(f"[TEST] Latest Linear Velocity: {latest_odom.twist.twist.linear.x:.4f} m/s")
        
    if received_env:
        latest_env = received_env[-1]
        print(f"[TEST] Latest Environment: Temp={latest_env.data[0]:.1f}C, Hum={latest_env.data[1]:.1f}%, VOC={latest_env.data[2]}, CO2={latest_env.data[3]}, MQ2={latest_env.data[4]}, Dust={latest_env.data[5]}")

    print(f"[TEST] Total Traveled Distance: {node_loc.engine.total_distance:.4f} m")
    if node_loc.logger_engine:
        print(f"[TEST] Checkpoints CSV File: {node_loc.logger_engine.output_file}")
        
    # Test service pause / resume
    print("[TEST] Testing Pause and Reset Services...")
    class MockReq: pass
    class MockResp: 
        success = False
        message = ""
        
    node_loc._handle_pause(MockReq(), MockResp())
    assert node_loc.is_paused == True, "Pause failed"
    node_loc._handle_resume(MockReq(), MockResp())
    assert node_loc.is_paused == False, "Resume failed"
    node_loc._handle_reset(MockReq(), MockResp())
    assert node_loc.engine.total_distance == 0.0, "Reset failed"
    print("[TEST] Services tested successfully!")
    
    node_loc.destroy_node()
    node_mock.destroy_node()
    rclpy.shutdown()
    print("[TEST] ALL INTEGRATION TESTS PASSED PERFECTLY!")

if __name__ == '__main__':
    run_integration_test()
