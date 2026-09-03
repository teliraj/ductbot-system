import csv
from datetime import datetime
import os

class CheckpointLogger:
    """
    CheckpointLogger handles saving the bot's position into a CSV file.
    
    Ported directly from fresh_repo/RPi_Localization_Logger/checkpoint_logger.py.
    
    Instead of logging every tiny movement, this class only logs when the bot 
    has traveled a specific distance (e.g., every 10 mm = 0.01 m).
    """
    def __init__(self, output_file=None, output_dir=None, interval_m=0.01):
        if output_file is None:
            if output_dir is None:
                output_dir = os.path.expanduser("~/ductbot_logs")
            os.makedirs(output_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            output_file = os.path.join(output_dir, f"checkpoints_{timestamp}.csv")
            
        self.output_file = output_file
        self.checkpoint_interval = interval_m 
        self.last_checkpoint_distance = 0.0
        self.checkpoint_number = 1
        
        # Ensure parent directory exists
        parent_dir = os.path.dirname(os.path.abspath(self.output_file))
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
            
        file_exists = os.path.exists(self.output_file)
        
        with open(self.output_file, mode='a', newline='') as file:
            writer = csv.writer(file)
            if not file_exists:
                writer.writerow([
                    "Timestamp", "Checkpoint Number", "X Coordinate", "Y Coordinate", 
                    "Yaw Value", "Distance (m)", "TOFL (mm)", "TOFR (mm)", 
                    "Temp (C)", "Humidity (%)", "VOC", "CO2 (ppm)", "MQ2", "Dust"
                ])

    def reset(self):
        """Resets distance counter and checkpoint index."""
        self.last_checkpoint_distance = 0.0
        self.checkpoint_number = 1
        if hasattr(self, 'prev_dist'):
            del self.prev_dist
            del self.prev_x
            del self.prev_y
            del self.prev_yaw
            del self.prev_time

    def update(self, total_distance, x, y, yaw, tof=None, env=None):
        """
        Checks if the bot has moved enough distance to log a new checkpoint (10mm).
        
        Parameters:
        - total_distance: Total physical distance traveled so far (meters).
        - x: Current X coordinate (meters).
        - y: Current Y coordinate (meters).
        - yaw: Current heading/rotation (degrees).
        - tof: Optional [TOFL, TOFR] array in mm.
        - env: Optional [Temp, Humidity, VOC, CO2, MQ2, Dust] array.
        
        Returns:
        - List of logged checkpoint dicts (if any triggered during this step).
        """
        if not hasattr(self, 'prev_dist'):
            self.prev_dist = total_distance
            self.prev_x = x
            self.prev_y = y
            self.prev_yaw = yaw
            self.prev_time = datetime.now().timestamp()
            
        current_time = datetime.now().timestamp()
        logged_entries = []
        
        while total_distance - self.last_checkpoint_distance >= self.checkpoint_interval:
            target_dist = self.last_checkpoint_distance + self.checkpoint_interval
            
            dist_diff = total_distance - self.prev_dist
            if dist_diff > 0.0001:
                alpha = (target_dist - self.prev_dist) / dist_diff
            else:
                alpha = 1.0
                
            interp_x = self.prev_x + alpha * (x - self.prev_x)
            interp_y = self.prev_y + alpha * (y - self.prev_y)
            
            interp_time = self.prev_time + alpha * (current_time - self.prev_time)
            dt_obj = datetime.fromtimestamp(interp_time)
            timestamp_str = dt_obj.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            
            dyaw = yaw - self.prev_yaw
            if dyaw > 180.0: dyaw -= 360.0
            elif dyaw < -180.0: dyaw += 360.0
            interp_yaw = (self.prev_yaw + alpha * dyaw) % 360.0
            
            row = [
                timestamp_str, self.checkpoint_number, 
                round(interp_x, 4), round(interp_y, 4), 
                round(interp_yaw, 2), round(target_dist, 4)
            ]
            
            if tof is not None:
                row.extend([int(tof[0]), int(tof[1])])
            else:
                row.extend(["-", "-"])
                
            if env is not None and len(env) >= 6:
                row.extend([
                    round(float(env[0]), 1), round(float(env[1]), 1), 
                    int(env[2]), int(env[3]), int(env[4]), int(env[5])
                ])
            else:
                row.extend(["-", "-", "-", "-", "-", "-"])
            
            with open(self.output_file, mode='a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(row)
                
            logged_entries.append({
                'checkpoint': self.checkpoint_number,
                'timestamp': timestamp_str,
                'x': interp_x,
                'y': interp_y,
                'yaw': interp_yaw,
                'dist': target_dist
            })
            
            self.checkpoint_number += 1
            self.last_checkpoint_distance = target_dist
            
        self.prev_dist = total_distance
        self.prev_x = x
        self.prev_y = y
        self.prev_yaw = yaw
        self.prev_time = current_time
        
        return logged_entries

    def log_event(self, event_type):
        """
        Logs a system event (START, STOP, PAUSE, RESUME, RESET) inline in the checkpoint CSV.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with open(self.output_file, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([timestamp, "EVENT", event_type, "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-"])
