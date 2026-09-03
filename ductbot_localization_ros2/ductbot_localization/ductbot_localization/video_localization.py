import os
import json
import math
import time
from datetime import datetime
import cv2

import numpy as np
try:
    import pandas as pd
except ImportError:
    pd = None

try:
    from scipy.signal import savgol_filter
except Exception:
    def savgol_filter(x, window_length=51, polyorder=3):
        w = min(window_length, len(x))
        if w % 2 == 0:
            w -= 1
        if w <= 1:
            return np.array(x)
        kernel = np.ones(w) / w
        return np.convolve(x, kernel, mode='same')

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

def draw_sharp_badge(frame, label_text="BEFORE", accent_color=(245, 158, 11), time_text=None, dist_text=None, is_bgr=True):
    """
    Renders high-definition, sharp, anti-aliased HUD badges onto video frames.
    Uses TrueType fonts with Pillow for crisp typography, with smooth fallbacks.
    accent_color in RGB: (245, 158, 11) for Before (gold), (16, 185, 129) for After (emerald).
    """
    h, w = frame.shape[:2]

    if HAS_PIL:
        if is_bgr:
            img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        else:
            img_pil = Image.fromarray(frame)
        draw = ImageDraw.Draw(img_pil)

        font_main = None
        for f_path in [
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ]:
            if os.path.exists(f_path):
                try:
                    font_main = ImageFont.truetype(f_path, 19)
                    break
                except Exception:
                    pass
        if font_main is None:
            font_main = ImageFont.load_default()

        pad_x, pad_y = 12, 10
        badge_w, badge_h = 132, 38

        # Outer shadow
        draw.rounded_rectangle(
            (pad_x - 1, pad_y - 1, pad_x + badge_w + 1, pad_y + badge_h + 1),
            radius=9,
            outline=(0, 0, 0),
            width=1
        )
        # Main pill
        draw.rounded_rectangle(
            (pad_x, pad_y, pad_x + badge_w, pad_y + badge_h),
            radius=8,
            fill=(10, 14, 22),
            outline=accent_color,
            width=2
        )

        # Glowing indicator dot
        pip_r = 5
        pip_cx, pip_cy = pad_x + 16, pad_y + badge_h // 2
        draw.ellipse(
            (pip_cx - pip_r, pip_cy - pip_r, pip_cx + pip_r, pip_cy + pip_r),
            fill=accent_color
        )

        # Main text (BEFORE / AFTER)
        text_x = pad_x + 30
        text_y = pad_y + 8
        draw.text((text_x, text_y), label_text, font=font_main, fill=(255, 255, 255))

        if is_bgr:
            return cv2.cvtColor(np.asarray(img_pil), cv2.COLOR_RGB2BGR)
        else:
            return np.asarray(img_pil)
    else:
        out = frame.copy()
        color_bgr = (accent_color[2], accent_color[1], accent_color[0]) if is_bgr else accent_color
        cv2.rectangle(out, (10, 10), (128, 40), (10, 14, 22), -1)
        cv2.rectangle(out, (10, 10), (128, 40), color_bgr, 1, cv2.LINE_AA)
        cv2.circle(out, (24, 25), 4, color_bgr, -1, cv2.LINE_AA)
        cv2.putText(out, label_text, (36, 31), cv2.FONT_HERSHEY_DUPLEX, 0.58, (255, 255, 255), 1, cv2.LINE_AA)
        return out

def kabsch_se2(A, B):
    """
    Calculates the optimal rigid 2D transform (Translation + Rotation) 
    that aligns points B to points A. (B_aligned = B @ R.T + t)
    Ported directly from fresh_repo/GUI/video_localization.py.
    """
    if len(A) == 0 or len(B) == 0:
        return np.eye(2), np.zeros(2)
        
    centroid_A = np.mean(A, axis=0)
    centroid_B = np.mean(B, axis=0)
    
    AA = A - centroid_A
    BB = B - centroid_B
    
    H = BB.T @ AA
    U, S, Vt = np.linalg.svd(H)
    
    R = Vt.T @ U.T
    
    # Handle reflection
    if np.linalg.det(R) < 0:
        Vt[1, :] *= -1
        R = Vt.T @ U.T
        
    t = centroid_A.T - R @ centroid_B.T
    return R, t

def apply_se2(B, R, t):
    """Apply SE(2) transform to point array B."""
    return (R @ B.T).T + t

def constrained_dtw(seq_A, seq_B, w_xy=0.0, w_yaw=5.0, w_path=1.0, window_pct=0.3):
    """
    Compute DTW path between seq_A and seq_B using Elastic Time-Warping.
    seq: [N, 4] array (x, y, dYaw, dist)
    Ported directly from fresh_repo/GUI/video_localization.py.
    """
    N = len(seq_A)
    M = len(seq_B)
    
    if N == 0 or M == 0:
        return [], 0.0, 0.0, 0.0
    
    window = int(max(N, M) * window_pct)
    window = max(window, 5) # Minimum window
    
    dtw_matrix = np.full((N + 1, M + 1), np.inf)
    dtw_matrix[0, 0] = 0
    
    for i in range(1, N + 1):
        for j in range(max(1, i - window), min(M + 1, i + window + 1)):
            a = seq_A[i-1]
            b = seq_B[j-1]
            
            yaw_diff = abs(a[2] - b[2])
            yaw_diff = min(yaw_diff, 360 - yaw_diff)
            yaw_cost = yaw_diff / 180.0
            
            # Dynamic length scaling for stretch penalty
            len_ratio = M / N if N > 0 else 1.0
            expected_dist = a[3] * len_ratio
            stretch_penalty = abs(b[3] - expected_dist)
            
            cost = (w_yaw * yaw_cost * 100) + (w_path * stretch_penalty * 10)
            
            dtw_matrix[i, j] = cost + min(
                dtw_matrix[i-1, j],
                dtw_matrix[i, j-1],
                dtw_matrix[i-1, j-1]
            )
            
    path = []
    i, j = N, M
    while i > 0 and j > 0:
        path.append((i-1, j-1))
        neighbors = [dtw_matrix[i-1, j-1], dtw_matrix[i-1, j], dtw_matrix[i, j-1]]
        min_idx = np.argmin(neighbors)
        if min_idx == 0:
            i -= 1; j -= 1
        elif min_idx == 1:
            i -= 1
        else:
            j -= 1
    while i > 1: i -= 1; path.append((i-1, 0))
    while j > 1: j -= 1; path.append((0, j-1))
    path.reverse()
    
    return path, 0.0, 0.0, 0.0

class VideoLocalization:
    """
    VideoLocalization Engine for Duct Bot.
    
    Ported directly from fresh_repo/GUI/video_localization.py.
    
    Aligns before-cleaning and after-cleaning video runs using:
    1. Spatial Resampling (fixed 20mm/50mm intervals)
    2. Kabsch SE(2) Rigid 2D path alignment
    3. Elastic DTW on angular velocity (dYaw) and cumulative distances
    4. Frame-by-frame extraction and side-by-side synchronized comparison video rendering.
    """
    def __init__(self, output_dir=None, resample_spacing_m=0.02):
        if output_dir is None:
            output_dir = os.path.expanduser("~/ductbot_recordings")
        self.output_dir = output_dir
        self.resample_spacing_m = resample_spacing_m  # 20mm = 0.02m
        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except OSError:
            pass

    def _parse_csv_with_frame_times(self, csv_path, video_path):
        """Parse CSV and sync with frame times if available."""
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Checkpoint CSV not found: {csv_path}")
            
        if pd is None:
            raise ImportError("pandas is required for video localization CSV processing. Please install pandas: pip install pandas")

        raw_df = pd.read_csv(csv_path)
        
        # Calculate video start time BEFORE filtering out the 'START' event
        raw_df['Timestamp'] = pd.to_datetime(raw_df['Timestamp'])
        video_start = raw_df['Timestamp'].min()
        
        df = raw_df[raw_df['Distance (m)'] != '-'].copy()
        
        if len(df) == 0:
            return pd.DataFrame()
            
        df['Distance (m)'] = df['Distance (m)'].astype(float)
        
        for col in ['X Coordinate', 'Y Coordinate', 'Yaw Value', 'TOFL (mm)', 'TOFR (mm)']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
        df['seconds'] = (df['Timestamp'] - video_start).dt.total_seconds()
        df['unix_time'] = df['Timestamp'].apply(lambda x: x.to_pydatetime().timestamp())
        
        df['frame_idx'] = -1
        frame_times_path = video_path.replace(".mp4", "_frame_times.csv")
        
        if os.path.exists(frame_times_path):
            try:
                ft_df = pd.read_csv(frame_times_path)
                if 'timestamp' in ft_df.columns and len(ft_df) > 0:
                    ft_times = ft_df['timestamp'].values
                    ft_indices = ft_df['written_frame_index'].values
                    
                    unix_times = df['unix_time'].values
                    indices = []
                    for t in unix_times:
                        idx = (np.abs(ft_times - t)).argmin()
                        indices.append(ft_indices[idx])
                    
                    df['frame_idx'] = indices
            except Exception as e:
                print(f"Frame times sync warning for {frame_times_path}: {e}")
                
        return df

    def _resample_path(self, df):
        """Resample path at exact cumulative distance intervals."""
        dists = df['Distance (m)'].values
        unique_idx = np.unique(dists, return_index=True)[1]
        unique_idx = np.sort(unique_idx)
        
        if len(unique_idx) < 2:
            return pd.DataFrame()
            
        df_u = df.iloc[unique_idx].copy()
        d_u = df_u['Distance (m)'].values
        
        max_dist = d_u[-1]
        if max_dist < 0.20:
            # Reject runs under 20cm
            return pd.DataFrame()
            
        target_dists = np.arange(d_u[0], max_dist, self.resample_spacing_m)
        
        resampled = pd.DataFrame({'Distance (m)': target_dists})
        
        for col in ['X Coordinate', 'Y Coordinate', 'seconds', 'frame_idx']:
            if col in df_u.columns:
                resampled[col] = np.interp(target_dists, d_u, df_u[col].values)
                
        for col in ['TOFL (mm)', 'TOFR (mm)']:
            if col in df_u.columns:
                vals = pd.to_numeric(df_u[col], errors='coerce').fillna(1000).values
                resampled[col] = np.interp(target_dists, d_u, vals)
                
        if 'Yaw Value' in df_u.columns:
            yaws = df_u['Yaw Value'].values
            yaws_unrolled = np.unwrap(np.deg2rad(yaws))
            res_yaw_rad = np.interp(target_dists, d_u, yaws_unrolled)
            resampled['Yaw Value'] = np.rad2deg(res_yaw_rad) % 360.0
            
        orig_indices = []
        for d in target_dists:
            idx = (np.abs(d_u - d)).argmin()
            orig_indices.append(df_u.index[idx])
        resampled['orig_row_idx'] = orig_indices
        
        return resampled

    def compare_runs(self, before_video, after_video, before_csv=None, after_csv=None, output_filename=None, progress_callback=None):
        """
        Executes full DTW alignment and generates synchronized side-by-side comparison video.
        
        Parameters:
        - before_video: Path to before cleaning MP4
        - after_video: Path to after cleaning MP4
        - before_csv: Optional explicit path to before checkpoints CSV
        - after_csv: Optional explicit path to after checkpoints CSV
        - output_filename: Optional output comparison MP4 path
        - progress_callback: Optional callable func(pct_0_to_100, status_str)
        
        Returns:
        - dict with {'success': bool, 'output_video': str, 'match_map': str, 'pairs_count': int, 'message': str}
        """
        if progress_callback: progress_callback(5.0, "Parsing checkpoint CSV logs...")
        
        before_base = os.path.splitext(before_video)[0]
        after_base = os.path.splitext(after_video)[0]
        
        b_csv = before_csv or f"{before_base}_checkpoints.csv"
        a_csv = after_csv or f"{after_base}_checkpoints.csv"
        
        if not os.path.exists(b_csv):
            return {'success': False, 'message': f"Before CSV not found: {b_csv}"}
        if not os.path.exists(a_csv):
            return {'success': False, 'message': f"After CSV not found: {a_csv}"}
        if not os.path.exists(before_video):
            return {'success': False, 'message': f"Before Video not found: {before_video}"}
        if not os.path.exists(after_video):
            return {'success': False, 'message': f"After Video not found: {after_video}"}

        before_df = self._parse_csv_with_frame_times(b_csv, before_video)
        after_df = self._parse_csv_with_frame_times(a_csv, after_video)

        if len(before_df) < 3 or len(after_df) < 3:
            if progress_callback:
                progress_callback(10.0, "Checkpoints < 3 (stationary run). Falling back to time-synchronized comparison...")
            return self._compare_runs_temporal(before_video, after_video, output_filename, progress_callback)

        if progress_callback: progress_callback(15.0, "Resampling trajectories...")
        b_res = self._resample_path(before_df)
        a_res = self._resample_path(after_df)
        
        if len(b_res) == 0 or len(a_res) == 0:
            if progress_callback:
                progress_callback(10.0, "Run distance < 0.20m. Falling back to time-synchronized comparison...")
            return self._compare_runs_temporal(before_video, after_video, output_filename, progress_callback)

        if progress_callback: progress_callback(30.0, "Computing DTW alignment...")
        
        b_distances = b_res['Distance (m)'].values
        a_distances = a_res['Distance (m)'].values
        
        b_yaw = b_res['Yaw Value'].values if 'Yaw Value' in b_res.columns else np.zeros(len(b_res))
        a_yaw = a_res['Yaw Value'].values if 'Yaw Value' in a_res.columns else np.zeros(len(a_res))
        
        def smooth(y, box_pts=5):
            if len(y) < box_pts: return y
            box = np.ones(box_pts) / box_pts
            return np.convolve(y, box, mode='same')
            
        b_yaw_s = smooth(b_yaw)
        a_yaw_s = smooth(a_yaw)
        
        b_dyaw = np.zeros_like(b_yaw_s)
        b_dyaw[1:] = (np.diff(b_yaw_s) + 180) % 360 - 180
        
        a_dyaw = np.zeros_like(a_yaw_s)
        a_dyaw[1:] = (np.diff(a_yaw_s) + 180) % 360 - 180
        
        seq_A = np.zeros((len(b_res), 4))
        seq_A[:, 2] = b_dyaw
        seq_A[:, 3] = b_distances
        
        seq_B = np.zeros((len(a_res), 4))
        seq_B[:, 2] = a_dyaw
        seq_B[:, 3] = a_distances
        
        raw_path, _, _, _ = constrained_dtw(seq_A, seq_B, w_xy=0.0, w_yaw=5.0, w_path=1.0, window_pct=0.3)
        
        j_mapped = np.zeros(len(seq_A))
        last_i = -1
        for (i, j) in raw_path:
            if i > last_i:
                j_mapped[i] = j
                last_i = i
            else:
                j_mapped[i] = j
                
        if len(j_mapped) > 51:
            j_smooth = savgol_filter(j_mapped, window_length=51, polyorder=3)
            j_smooth = np.maximum.accumulate(j_smooth)
            j_smooth = np.clip(j_smooth, 0, len(seq_B)-1).astype(int)
        else:
            j_smooth = np.maximum.accumulate(j_mapped).astype(int)
            
        final_path = [(i, j_smooth[i]) for i in range(len(b_distances))]
        
        if progress_callback: progress_callback(50.0, "Extracting synchronized video frames...")
        
        # Try moviepy / fallback to cv2 for fast rendering on Jetson
        try:
            try:
                from moviepy.editor import VideoFileClip, ImageSequenceClip, clips_array
            except ImportError:
                from moviepy import VideoFileClip, ImageSequenceClip, clips_array
            
            before_clip = VideoFileClip(before_video)
            after_clip = VideoFileClip(after_video)
            
            b_fps = before_clip.fps if before_clip.fps > 0 else 30
            a_fps = after_clip.fps if after_clip.fps > 0 else 30
            
            before_frames = []
            after_frames = []
            match_map = []
            
            total_frames = len(final_path)
            for out_idx, (b_idx, a_idx) in enumerate(final_path):
                b_row = b_res.iloc[b_idx]
                a_row = a_res.iloc[a_idx]
                
                b_t = b_row['frame_idx'] / b_fps if b_row['frame_idx'] != -1 else b_row['seconds']
                a_t = a_row['frame_idx'] / a_fps if a_row['frame_idx'] != -1 else a_row['seconds']
                
                if b_t >= before_clip.duration: b_t = max(0.0, before_clip.duration - 0.1)
                if a_t >= after_clip.duration: a_t = max(0.0, after_clip.duration - 0.1)
                
                try:
                    b_frame = before_clip.get_frame(b_t)
                    a_frame = after_clip.get_frame(a_t)
                    
                    b_frame = draw_sharp_badge(
                        b_frame, label_text="BEFORE", accent_color=(245, 158, 11), is_bgr=False
                    )
                    a_frame = draw_sharp_badge(
                        a_frame, label_text="AFTER", accent_color=(16, 185, 129), is_bgr=False
                    )

                    before_frames.append(b_frame)
                    after_frames.append(a_frame)
                    
                    match_map.append({
                        "output_frame": out_idx,
                        "distance_m": round(float(b_row['Distance (m)']), 3),
                        "before_time_s": round(float(b_t), 3),
                        "after_time_s": round(float(a_t), 3)
                    })
                except Exception as e:
                    print(f"Warning extracting frame at {b_idx}, {a_idx}: {e}")
                    
                if progress_callback and out_idx % 20 == 0:
                    pct = 50.0 + (float(out_idx) / total_frames) * 35.0
                    progress_callback(pct, f"Extracting frame {out_idx}/{total_frames}...")

            if progress_callback: progress_callback(85.0, "Stitching side-by-side comparison video...")
            
            if not output_filename:
                b_name = os.path.basename(os.path.splitext(before_video)[0])
                a_name = os.path.basename(os.path.splitext(after_video)[0])
                merged_dir = os.path.join(self.output_dir, "merged_videos")
                os.makedirs(merged_dir, exist_ok=True)
                output_filename = os.path.join(merged_dir, f"{b_name}_vs_{a_name}.mp4")
                
            map_path = output_filename.replace(".mp4", "_match_map.json")
            with open(map_path, 'w') as f:
                json.dump({
                    "algorithm": "dtw_elastic_v3",
                    "total_distance_m": float(b_distances[-1]),
                    "frames_count": len(match_map),
                    "pairs": match_map
                }, f, indent=2)
                
            before_seq = ImageSequenceClip(before_frames, fps=5)
            after_seq = ImageSequenceClip(after_frames, fps=5)
            final_clip = clips_array([[before_seq, after_seq]])
            final_clip.write_videofile(output_filename, logger=None, ffmpeg_params=['-g', '1'])
            
            if progress_callback: progress_callback(100.0, "Comparison complete!")
            
            return {
                'success': True,
                'output_video': output_filename,
                'match_map': map_path,
                'pairs_count': len(match_map),
                'message': f"Successfully generated comparison video: {output_filename}"
            }
            
        except Exception as e:
            return {'success': False, 'message': f"Video rendering error: {e}"}

    def _compare_runs_temporal(self, before_video, after_video, output_filename=None, progress_callback=None):
        """
        Fallback comparison for stationary or short-distance bench runs (< 20cm).
        Generates a side-by-side synchronized comparison video based on playback timestamps.
        """
        if progress_callback:
            progress_callback(20.0, "Synchronizing video streams side-by-side...")

        cap_b = cv2.VideoCapture(before_video)
        cap_a = cv2.VideoCapture(after_video)

        if not cap_b.isOpened() or not cap_a.isOpened():
            if cap_b.isOpened(): cap_b.release()
            if cap_a.isOpened(): cap_a.release()
            return {'success': False, 'message': "Failed to open input video files."}

        fps_b = cap_b.get(cv2.CAP_PROP_FPS) or 25.0
        fps_a = cap_a.get(cv2.CAP_PROP_FPS) or 25.0
        cnt_b = int(cap_b.get(cv2.CAP_PROP_FRAME_COUNT) or 1)
        cnt_a = int(cap_a.get(cv2.CAP_PROP_FRAME_COUNT) or 1)
        dur_b = cnt_b / fps_b
        dur_a = cnt_a / fps_a

        out_fps = min(fps_b, fps_a, 30.0)
        target_dur = max(dur_b, dur_a)
        total_out_frames = max(1, int(target_dur * out_fps))

        out_w_single = 640
        out_h_single = 360
        total_w = out_w_single * 2
        total_h = out_h_single

        if not output_filename:
            b_name = os.path.basename(os.path.splitext(before_video)[0])
            a_name = os.path.basename(os.path.splitext(after_video)[0])
            merged_dir = os.path.join(self.output_dir, "merged_videos")
            os.makedirs(merged_dir, exist_ok=True)
            output_filename = os.path.join(merged_dir, f"{b_name}_vs_{a_name}.mp4")

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out_writer = cv2.VideoWriter(output_filename, fourcc, out_fps, (total_w, total_h))

        last_fb = None
        last_fa = None

        for idx in range(total_out_frames):
            cur_time = idx / out_fps
            if cur_time <= dur_b:
                ret_b, fb = cap_b.read()
                if ret_b and fb is not None:
                    last_fb = fb
            if cur_time <= dur_a:
                ret_a, fa = cap_a.read()
                if ret_a and fa is not None:
                    last_fa = fa

            fb_use = last_fb if last_fb is not None else np.zeros((out_h_single, out_w_single, 3), dtype=np.uint8)
            fa_use = last_fa if last_fa is not None else np.zeros((out_h_single, out_w_single, 3), dtype=np.uint8)

            fb_resized = cv2.resize(fb_use, (out_w_single, out_h_single))
            fa_resized = cv2.resize(fa_use, (out_w_single, out_h_single))

            # Sharp HUD Badges: BEFORE (Left) & AFTER (Right) - compact, no timer
            fb_resized = draw_sharp_badge(
                fb_resized, label_text="BEFORE", accent_color=(245, 158, 11), is_bgr=True
            )
            fa_resized = draw_sharp_badge(
                fa_resized, label_text="AFTER", accent_color=(16, 185, 129), is_bgr=True
            )

            combined = np.hstack((fb_resized, fa_resized))
            out_writer.write(combined)

            if progress_callback and idx % 20 == 0:
                pct = 20.0 + (float(idx) / total_out_frames) * 75.0
                progress_callback(pct, f"Stitching frame {idx}/{total_out_frames}...")

        cap_b.release()
        cap_a.release()
        out_writer.release()

        map_path = output_filename.replace(".mp4", "_match_map.json")
        try:
            with open(map_path, 'w') as f:
                json.dump({
                    "algorithm": "temporal_side_by_side",
                    "duration_s": target_dur,
                    "frames_count": total_out_frames,
                    "status": "synchronized"
                }, f, indent=2)
        except Exception:
            pass

        if progress_callback:
            progress_callback(100.0, "Comparison complete!")

        return {
            'success': True,
            'output_video': output_filename,
            'match_map': map_path,
            'pairs_count': total_out_frames,
            'mode': 'temporal_sync',
            'message': f"Successfully generated synchronized comparison video: {output_filename}"
        }
