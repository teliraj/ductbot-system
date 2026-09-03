import os
import json
import threading
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Float32
from std_srvs.srv import Trigger

from .video_localization import VideoLocalization

class DuctBotVideoComparisonNode(Node):
    """
    ROS 2 Node for Video Localization and Before/After Comparison.
    
    Provides services and topic triggers for aligning two inspection runs
    using Dynamic Time Warping (DTW) and generating synchronized side-by-side videos.
    """
    def __init__(self):
        super().__init__('ductbot_video_comparison_node')
        
        # 1. Parameters
        self.declare_parameter('recordings_dir', os.path.expanduser('~/ductbot_recordings'))
        self.declare_parameter('resample_spacing_m', 0.02)
        
        self.recordings_dir = self.get_parameter('recordings_dir').get_parameter_value().string_value
        self.resample_spacing_m = self.get_parameter('resample_spacing_m').get_parameter_value().double_value
        
        self.get_logger().info("=== DuctBot Video Comparison Node Initialized ===")
        self.get_logger().info(f"Recordings Directory: {self.recordings_dir}")
        self.get_logger().info(f"Resample Spacing: {self.resample_spacing_m * 1000.0} mm")
        
        # 2. Engine
        self.engine = VideoLocalization(
            output_dir=self.recordings_dir,
            resample_spacing_m=self.resample_spacing_m
        )
        
        # 3. Publishers
        self.progress_pub = self.create_publisher(Float32, '/ductbot/video_comparison_progress', 10)
        self.status_pub = self.create_publisher(String, '/ductbot/video_comparison_status', 10)
        
        # 4. Subscriber for JSON triggers
        # Format: {"before_video": "path/run1.mp4", "after_video": "path/run2.mp4"}
        self.trigger_sub = self.create_subscription(
            String,
            '/ductbot/trigger_comparison',
            self._handle_trigger_msg,
            10
        )
        
        # 5. Service for Auto-Comparing latest two runs
        self.auto_compare_srv = self.create_service(
            Trigger,
            '/ductbot/compare_latest_runs',
            self._handle_compare_latest_srv
        )
        
        self.is_busy = False
        self.lock = threading.Lock()

    def _publish_progress(self, pct: float, status_text: str):
        """Broadcasts progress to ROS 2 topics."""
        p_msg = Float32()
        p_msg.data = float(pct)
        self.progress_pub.publish(p_msg)
        
        s_msg = String()
        s_msg.data = json.dumps({
            "progress_percent": round(pct, 1),
            "status": status_text
        })
        self.status_pub.publish(s_msg)
        self.get_logger().info(f"[Video Comp {pct:.0f}%]: {status_text}")

    def _handle_trigger_msg(self, msg: String):
        """Handles comparison requests sent as JSON strings on /ductbot/trigger_comparison."""
        try:
            payload = json.loads(msg.data)
            before_video = payload.get("before_video")
            after_video = payload.get("after_video")
            before_csv = payload.get("before_csv")
            after_csv = payload.get("after_csv")
            
            if not before_video or not after_video:
                self.get_logger().error("Trigger JSON must contain 'before_video' and 'after_video' paths.")
                return
                
            self._start_comparison_thread(before_video, after_video, before_csv, after_csv)
            
        except Exception as e:
            self.get_logger().error(f"Failed to parse trigger message JSON: {e}")

    def _handle_compare_latest_srv(self, request, response):
        """Finds the two most recent video files in recordings_dir and compares them."""
        with self.lock:
            if self.is_busy:
                response.success = False
                response.message = "Video comparison already in progress. Please wait."
                return response
                
        # Scan for mp4 files
        video_files = []
        if os.path.exists(self.recordings_dir):
            for root, _, files in os.walk(self.recordings_dir):
                for f in files:
                    if f.endswith(".mp4") and not "_vs_" in f:
                        full_path = os.path.join(root, f)
                        video_files.append((os.path.getmtime(full_path), full_path))
                        
        video_files.sort(reverse=True)
        if len(video_files) < 2:
            response.success = False
            response.message = f"Need at least 2 recorded videos in {self.recordings_dir} to compare. Found {len(video_files)}."
            return response
            
        after_video = video_files[0][1]   # Most recent
        before_video = video_files[1][1]  # Second most recent
        
        self.get_logger().info(f"Auto-comparing:\nBefore: {before_video}\nAfter: {after_video}")
        self._start_comparison_thread(before_video, after_video)
        
        response.success = True
        response.message = f"Started comparison between {os.path.basename(before_video)} and {os.path.basename(after_video)}"
        return response

    def _start_comparison_thread(self, before_video, after_video, before_csv=None, after_csv=None):
        with self.lock:
            if self.is_busy:
                self.get_logger().warn("Comparison job already running. Ignoring new request.")
                return
            self.is_busy = True
            
        thread = threading.Thread(
            target=self._run_comparison_worker,
            args=(before_video, after_video, before_csv, after_csv),
            daemon=True
        )
        thread.start()

    def _run_comparison_worker(self, before_video, after_video, before_csv, after_csv):
        try:
            self._publish_progress(0.0, "Starting DTW Video Comparison...")
            res = self.engine.compare_runs(
                before_video=before_video,
                after_video=after_video,
                before_csv=before_csv,
                after_csv=after_csv,
                progress_callback=self._publish_progress
            )
            
            if res.get('success'):
                self._publish_progress(100.0, f"SUCCESS: Video saved to {res.get('output_video')}")
            else:
                self._publish_progress(0.0, f"FAILED: {res.get('message')}")
                
        except Exception as e:
            self.get_logger().error(f"Unexpected error in video comparison worker: {e}")
            self._publish_progress(0.0, f"ERROR: {e}")
        finally:
            with self.lock:
                self.is_busy = False


def main(args=None):
    rclpy.init(args=args)
    node = DuctBotVideoComparisonNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Shutting down DuctBot Video Comparison Node...")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
