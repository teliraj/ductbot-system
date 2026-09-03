from kivy.config import Config
Config.set('graphics', 'fullscreen', '0')
Config.set('graphics', 'resizable', '1')
Config.set('graphics', 'width', '1280')
Config.set('graphics', 'height', '720')

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.core.window import Window
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.graphics.texture import Texture
from kivy.graphics import Color, Rectangle, RoundedRectangle, Line
from kivy.metrics import dp, Metrics
Metrics.fontscale = 1.22
from kivy.uix.spinner import Spinner
from kivy.uix.checkbox import CheckBox
from kivy.uix.progressbar import ProgressBar
from kivy.uix.widget import Widget
import cv2
import threading
import json
import csv
import math
import os
import sys
import time
import sqlite3
import ctypes
import string
import shutil

# Ensure ductbot_localization package from Downloads is prioritized on sys.path
_DOWNLOADS_PKG_DIR = "/home/roboserv-4i/Downloads/ductbot_localization_ros2/ductbot_localization"
if os.path.exists(_DOWNLOADS_PKG_DIR):
    if _DOWNLOADS_PKG_DIR in sys.path:
        sys.path.remove(_DOWNLOADS_PKG_DIR)
    sys.path.insert(0, _DOWNLOADS_PKG_DIR)

try:
    from ductbot_localization.video_localization import VideoLocalization
    from ductbot_localization.checkpoint_logger import CheckpointLogger
    import inspect
    print(f"[DuctbotUI] Using VideoLocalization from: {inspect.getfile(VideoLocalization)}")
    LOCALIZATION_MODULES_AVAILABLE = True
except Exception as _e:
    print(f"[DuctbotUI] Warning: could not import ductbot_localization: {_e}")
    LOCALIZATION_MODULES_AVAILABLE = False

from controls import BottomControlBar, PlaybackInfoPanel
from dashboard_ui import (
    HeaderBar, NavSidebar, VideoOverlay, RoundedButton, FormField, SegmentButton,
    PlayIcon, UploadIcon, StopIcon, PersonIcon, MapIcon, GridIcon, SunIcon,
    CameraIcon, SendIcon, CloseIcon, VideoIcon, CompareIcon, VideoComparisonPopup,
    PlaybackSectionHeader, RecordingRowWidget, OnScreenKeyboard,
    COL_BG, COL_PANEL, COL_PANEL_ALT, COL_BORDER, COL_BLUE, COL_RED, COL_YELLOW, COL_GREEN, COL_TEXT, COL_TEXT_DIM,
)
from splash_fx import SplashLoader
from ros_bridge import CameraBridge
from esp32_reader import get_esp32_reader

class CV2Colors:
    YELLOW = (0, 255, 255)
    GREEN = (0, 255, 0)

class DuctbotUI(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='horizontal', **kwargs)

        with self.canvas.before:
            Color(*COL_BG)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        self.camera_bridge = CameraBridge()
        self.esp32_reader = get_esp32_reader()
        self.capture = None
        self.is_camera_flipped = False
        self.lane_enabled = False
        self.map_enabled = False
        self.is_recording = False
        self.is_recording_paused = False
        self.video_writer = None
        self.is_paused = False
        self.playback_mode = False
        self.current_mode = 'live'
        self._last_set_mode = 'live'
        self.is_fullscreen = False
        self._record_start_time = None
        self._record_elapsed = 0.0
        self._frame_times_file = None
        self._frame_times_writer = None
        self._recorded_frame_count = 0
        self._active_checkpoint_logger = None

        self.video_dir = "videos"
        if not os.path.exists(self.video_dir):
            os.makedirs(self.video_dir)
            
        self.db_dir = "database"
        if not os.path.exists(self.db_dir):
            os.makedirs(self.db_dir)
            
        # Move existing database to the new folder if it exists in the root
        if os.path.exists('recordings.db') and not os.path.exists(os.path.join(self.db_dir, 'recordings.db')):
            try:
                shutil.move('recordings.db', os.path.join(self.db_dir, 'recordings.db'))
                print("Moved recordings.db to database folder.")
            except Exception as e:
                print(f"Failed to move database: {e}")
                
        self.db_conn = sqlite3.connect(os.path.join(self.db_dir, 'recordings.db'))
        self.setup_database()
        
        self.recordings = self.load_recordings()
        
        # Mock sensor lock and data for the lane guides
        self.sensor_lock = threading.Lock()
        self.sensor_data = {"TOF_L": 100, "TOF_R": 100}

        self._viewing_single_video = False

        # Left navigation sidebar (Live / Playback)
        self.nav_sidebar = NavSidebar(on_nav=self.set_mode)
        self.add_widget(self.nav_sidebar)

        # Main column: header on top, body (video/list + status + controls) below
        self.main_column = BoxLayout(orientation='vertical')
        self.add_widget(self.main_column)

        self.header = HeaderBar(on_shutdown=lambda x: self.confirm_shutdown())
        self.main_column.add_widget(self.header)

        self._body_padding = (dp(16), dp(14), dp(16), dp(14))
        self.body = BoxLayout(orientation='vertical', padding=self._body_padding, spacing=dp(12))
        self.main_column.add_widget(self.body)

        # Display area (Can hold either Video or List)
        self.display_area = BoxLayout(orientation='vertical')
        self.body.add_widget(self.display_area)

        # Video feed area, with REC/mode badges and Flip/Fullscreen buttons
        # layered on top
        # Kivy's Image always paints a rectangle tinted by `color` behind its
        # texture (part of its stencil-mask kv rule), even with no texture
        # set - that shows as a solid white block until the first frame
        # arrives. Start transparent and reveal it once a texture is set.
        self.image = Image(allow_stretch=True, keep_ratio=False, color=(0, 0, 0, 0))
        self.video_overlay = VideoOverlay(
            self.image, on_toggle_fullscreen=self.toggle_fullscreen,
            on_flip=lambda: self.flip_camera(),
            on_toggle_lane=self.toggle_lane,
            on_switch_cam=self.switch_camera,
            on_toggle_map=self.toggle_map,
            on_reset_odom=self.reset_odometry,
        )
        self.display_area.add_widget(self.video_overlay)

        # Playback list area (hidden by default)
        self.list_view = ScrollView(size_hint=(1, 1))

        with self.list_view.canvas.before:
            Color(*COL_BG)
            self.list_view.lv_bg = Rectangle(size=self.list_view.size, pos=self.list_view.pos)
        def update_lv_bg(instance, value):
            instance.lv_bg.pos = instance.pos
            instance.lv_bg.size = instance.size
        self.list_view.bind(pos=update_lv_bg, size=update_lv_bg)

        self.list_layout = GridLayout(cols=1, spacing=2, padding=10, size_hint_y=None)
        self.list_layout.bind(minimum_height=self.list_layout.setter('height'))
        self.list_view.add_widget(self.list_layout)

        # Selection toolbar (select all / export / delete) above the list,
        # and the container that holds toolbar + list together
        self.selection_checkboxes = {}
        self.row_widgets = {}
        self.playback_filter = 'ALL'
        self.playback_container = BoxLayout(orientation='vertical', spacing=dp(8))

        self.selection_toolbar = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        self.selection_label = Label(
            text='0 selected', color=COL_TEXT_DIM, bold=True, font_size='12sp',
            size_hint_x=None, width=dp(280), halign='left', valign='middle',
        )
        self.selection_label.bind(size=lambda w, *_: setattr(w, 'text_size', w.size))
        self.selection_toolbar.add_widget(self.selection_label)

        # Segmented Filter: ALL | BEFORE | AFTER
        self.btn_filter_all = RoundedButton(text='ALL', bg_color=COL_BLUE, fg_color=(1, 1, 1, 1), size_hint_x=None, width=dp(68), font_size=11, radius=6)
        self.btn_filter_before = RoundedButton(text='BEFORE', bg_color=COL_PANEL_ALT, fg_color=COL_TEXT, size_hint_x=None, width=dp(80), font_size=11, radius=6)
        self.btn_filter_after = RoundedButton(text='AFTER', bg_color=COL_PANEL_ALT, fg_color=COL_TEXT, size_hint_x=None, width=dp(80), font_size=11, radius=6)
        self.btn_filter_all.bind(on_press=lambda x: self._set_playback_filter('ALL'))
        self.btn_filter_before.bind(on_press=lambda x: self._set_playback_filter('BEFORE'))
        self.btn_filter_after.bind(on_press=lambda x: self._set_playback_filter('AFTER'))
        self.selection_toolbar.add_widget(self.btn_filter_all)
        self.selection_toolbar.add_widget(self.btn_filter_before)
        self.selection_toolbar.add_widget(self.btn_filter_after)

        self.selection_toolbar.add_widget(BoxLayout())

        self.btn_select_all = RoundedButton(
            text='SELECT ALL', bg_color=COL_PANEL_ALT, fg_color=COL_TEXT, border_color=COL_BORDER,
            size_hint_x=None, width=dp(130), font_size=12,
        )
        self.btn_select_all.bind(on_press=lambda x: self.toggle_select_all())
        self.selection_toolbar.add_widget(self.btn_select_all)

        self.btn_export_selected = RoundedButton(
            text='EXPORT', icon_cls=UploadIcon, icon_color=(1, 1, 1, 1),
            bg_color=COL_BLUE, fg_color=(1, 1, 1, 1), size_hint_x=None, width=dp(120), font_size=12,
        )
        self.btn_export_selected.bind(on_press=lambda x: self.export_selected())
        self.selection_toolbar.add_widget(self.btn_export_selected)

        self.btn_compare_selected = RoundedButton(
            text='COMPARE (BEFORE vs AFTER)', icon_cls=CompareIcon, icon_color=(1, 1, 1, 1),
            bg_color=COL_YELLOW, fg_color=(0.02, 0.03, 0.06, 1), size_hint_x=None, width=dp(250), font_size=12,
        )
        self.btn_compare_selected.bind(on_press=lambda x: self.open_comparison_dialog())
        self.selection_toolbar.add_widget(self.btn_compare_selected)

        self.btn_delete_selected = RoundedButton(
            text='DELETE', icon_cls=StopIcon, icon_color=COL_RED,
            bg_color=(0, 0, 0, 0), fg_color=COL_RED, border_color=COL_RED,
            size_hint_x=None, width=dp(120), font_size=12,
        )
        self.btn_delete_selected.bind(on_press=lambda x: self.confirm_delete_selected())
        self.selection_toolbar.add_widget(self.btn_delete_selected)

        self.playback_container.add_widget(self.selection_toolbar)
        self.playback_content_area = BoxLayout(orientation='vertical', size_hint=(1, 1))
        self.playback_container.add_widget(self.playback_content_area)
        self.update_selection_count()

        # Bottom control bar: Start Recording / Stop
        bottom_callbacks = {
            'play_pause': self.play_pause,
            'stop': lambda x: self.confirm_stop(),
        }
        self.control_bar = BottomControlBar(bottom_callbacks)
        self.body.add_widget(self.control_bar)

        # Update frame / dashboard periodically
        Clock.schedule_interval(self.update_frame, 1.0 / 30.0)
        Clock.schedule_interval(self.update_dashboard, 0.3)

    def _update_bg(self, *args):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size

    def _set_playback_filter(self, flt):
        self.playback_filter = flt
        if hasattr(self, 'btn_filter_all'):
            self.btn_filter_all.bg_color = COL_BLUE if flt == 'ALL' else COL_PANEL_ALT
            self.btn_filter_all._bgcol.rgba = COL_BLUE if flt == 'ALL' else COL_PANEL_ALT
            self.btn_filter_before.bg_color = COL_YELLOW if flt == 'BEFORE' else COL_PANEL_ALT
            self.btn_filter_before._bgcol.rgba = COL_YELLOW if flt == 'BEFORE' else COL_PANEL_ALT
            self.btn_filter_before.label.color = (0.02, 0.03, 0.06, 1) if flt == 'BEFORE' else COL_TEXT
            self.btn_filter_after.bg_color = COL_GREEN if flt == 'AFTER' else COL_PANEL_ALT
            self.btn_filter_after._bgcol.rgba = COL_GREEN if flt == 'AFTER' else COL_PANEL_ALT
            self.btn_filter_after.label.color = (1, 1, 1, 1) if flt == 'AFTER' else COL_TEXT
        self.populate_playback_list()

    def setup_database(self):
        cursor = self.db_conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recordings (
                serial INTEGER PRIMARY KEY AUTOINCREMENT,
                client TEXT,
                area TEXT,
                side TEXT,
                filename TEXT
            )
        ''')
        try:
            cursor.execute("ALTER TABLE recordings ADD COLUMN condition TEXT")
        except sqlite3.OperationalError:
            pass # column exists
            
        try:
            cursor.execute("ALTER TABLE recordings ADD COLUMN camera TEXT")
        except sqlite3.OperationalError:
            pass # column exists
            
        self.db_conn.commit()
        
        # Migrate old JSON data if exists
        if os.path.exists('recordings.json'):
            try:
                with open('recordings.json', 'r') as f:
                    old_data = json.load(f)
                
                for rec in old_data:
                    cursor.execute(
                        "INSERT INTO recordings (client, area, side, filename) VALUES (?, ?, ?, ?)",
                        (rec.get('client', ''), rec.get('area', ''), rec.get('side', ''), rec.get('filename', ''))
                    )
                self.db_conn.commit()
                os.rename('recordings.json', 'recordings.json.bak')
                print("Migrated recordings.json to SQLite database.")
            except Exception as e:
                print(f"Error migrating JSON to SQL: {e}")

    def load_recordings(self):
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT serial, client, area, side, filename, condition, camera FROM recordings ORDER BY serial ASC")
        rows = cursor.fetchall()
        recordings = []
        for row in rows:
            fn = os.path.normpath(str(row[4]).replace('\\', os.sep))
            recordings.append({
                "serial": row[0],
                "client": row[1],
                "area": row[2],
                "side": row[3],
                "filename": fn,
                "condition": row[5] if row[5] else "N/A",
                "camera": row[6] if row[6] else "N/A"
            })
        return recordings

    def shutdown_system(self):
        print("Shutting down system...")
        if hasattr(self, 'camera_bridge'):
            self.camera_bridge.stop()
        if hasattr(self, 'esp32_reader'):
            self.esp32_reader.stop()
        if hasattr(self, 'db_conn'):
            self.db_conn.close()
        App.get_running_app().stop()

    def show_confirm(self, title, message, on_confirm, confirm_text='CONFIRM', danger=True):
        content = BoxLayout(orientation='vertical', spacing=dp(16), padding=dp(18))
        lbl = Label(text=message, color=COL_TEXT, halign='center', valign='middle')
        lbl.bind(size=lambda w, *_a: setattr(w, 'text_size', w.size))
        content.add_widget(lbl)

        popup = Popup(
            title=title, content=content, size_hint=(0.4, 0.3), auto_dismiss=False,
            background_color=COL_PANEL, title_color=COL_TEXT, separator_color=COL_BORDER,
        )

        btn_row = BoxLayout(spacing=dp(10), size_hint_y=None, height=dp(44))
        btn_cancel = RoundedButton(
            text='CANCEL', bg_color=COL_PANEL_ALT, fg_color=COL_TEXT, border_color=COL_BORDER,
        )
        btn_cancel.bind(on_press=lambda x: popup.dismiss())
        btn_confirm = RoundedButton(
            text=confirm_text, bg_color=COL_RED if danger else COL_BLUE, fg_color=(1, 1, 1, 1),
        )
        def do_confirm(x):
            popup.dismiss()
            on_confirm()
        btn_confirm.bind(on_press=do_confirm)
        btn_row.add_widget(btn_cancel)
        btn_row.add_widget(btn_confirm)
        content.add_widget(btn_row)
        popup.open()

    def show_message(self, title, message):
        content = BoxLayout(orientation='vertical', spacing=dp(16), padding=dp(18))
        lbl = Label(text=message, color=COL_TEXT, halign='center', valign='middle')
        lbl.bind(size=lambda w, *_a: setattr(w, 'text_size', w.size))
        content.add_widget(lbl)
        popup = Popup(
            title=title, content=content, size_hint=(0.4, 0.28),
            background_color=COL_PANEL, title_color=COL_TEXT, separator_color=COL_BORDER,
        )
        btn_ok = RoundedButton(
            text='OK', bg_color=COL_BLUE, fg_color=(1, 1, 1, 1), size_hint_y=None, height=dp(40),
        )
        btn_ok.bind(on_press=lambda x: popup.dismiss())
        content.add_widget(btn_ok)
        popup.open()

    def confirm_shutdown(self):
        self.show_confirm(
            title='Shutdown System',
            message='Shut down the application?',
            on_confirm=self.shutdown_system,
            confirm_text='SHUTDOWN',
        )

    def confirm_stop(self):
        if not self.playback_mode and self.is_recording:
            self.show_confirm(
                title='Stop Recording',
                message='Stop the current recording? The saved video will remain in your recordings.',
                on_confirm=self.stop_video,
                confirm_text='STOP RECORDING',
            )
        else:
            self.stop_video()

    def _refresh_status_row(self):
        """Show the playback metadata bar between the video and the bottom
        control bar while viewing a specific recording; otherwise show
        nothing there (the selection toolbar covers that role while
        browsing the recordings list)."""
        if hasattr(self, 'playback_info_panel') and self.playback_info_panel.parent:
            self.body.remove_widget(self.playback_info_panel)
        if self.is_fullscreen:
            return
        # Insert just above the control bar when it's present (normal
        # mode-switching); otherwise (mid fullscreen-restore, before the
        # control bar has been re-added) prepend so the control bar ends
        # up below it once it's added back.
        insert_index = 1 if self.control_bar in self.body.children else 0
        if self._viewing_single_video:
            self.body.add_widget(self.playback_info_panel, index=insert_index)

    def set_mode(self, mode):
        self.current_mode = mode
        playback = (mode in ('playback', 'comparison'))
        self.nav_sidebar.set_active(mode)
        if playback == self.playback_mode and mode == getattr(self, '_last_set_mode', None):
            return
        self._last_set_mode = mode

        if self.capture:
            self.capture.release()
            self.capture = None

        self.playback_mode = playback
        self._viewing_single_video = False

        if playback:
            self.control_bar.set_recording_label('START / PAUSE')
            if self.is_recording:
                self.stop_recording()

            # Show list, hide video
            self.display_area.clear_widgets()
            self.display_area.add_widget(self.playback_container)
            self.populate_playback_list()
        else:
            self.control_bar.set_recording_label('START RECORDING')

            # Show video, hide list
            self.display_area.clear_widgets()
            self.display_area.add_widget(self.video_overlay)
            self.capture = None
            self.video_overlay.set_flip_visible(True)

        self._refresh_status_row()

    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            # Hide everything except the video itself: nav sidebar, header,
            # status/info row, and the bottom control bar.
            if self.nav_sidebar.parent:
                self.remove_widget(self.nav_sidebar)
            if self.header.parent:
                self.main_column.remove_widget(self.header)
            if hasattr(self, 'playback_info_panel') and self.playback_info_panel.parent:
                self.body.remove_widget(self.playback_info_panel)
            if self.control_bar.parent:
                self.body.remove_widget(self.control_bar)
            self.body.padding = (0, 0, 0, 0)
        else:
            if not self.nav_sidebar.parent:
                self.add_widget(self.nav_sidebar, index=len(self.children))
            if not self.header.parent:
                self.main_column.add_widget(self.header, index=len(self.main_column.children))
            self._refresh_status_row()
            if not self.control_bar.parent:
                self.body.add_widget(self.control_bar)
            self.body.padding = self._body_padding
        self.video_overlay.set_fullscreen(self.is_fullscreen)

    def populate_playback_list(self):
        if not hasattr(self, 'playback_content_area'):
            self.playback_content_area = BoxLayout(orientation='vertical', size_hint=(1, 1))
            self.playback_container.clear_widgets()
            self.playback_container.add_widget(self.selection_toolbar)
            self.playback_container.add_widget(self.playback_content_area)

        self.playback_content_area.clear_widgets()
        self.selection_checkboxes = {}
        self.row_widgets = {}

        is_comp_mode = (getattr(self, 'current_mode', 'playback') == 'comparison')
        filter_mode = getattr(self, 'playback_filter', 'ALL')

        # Hide or show filter buttons based on mode
        if hasattr(self, 'btn_filter_all'):
            self.btn_filter_all.opacity = 0 if is_comp_mode else 1
            self.btn_filter_before.opacity = 0 if is_comp_mode else 1
            self.btn_filter_after.opacity = 0 if is_comp_mode else 1
            self.btn_filter_all.disabled = is_comp_mode
            self.btn_filter_before.disabled = is_comp_mode
            self.btn_filter_after.disabled = is_comp_mode

        if is_comp_mode:
            self.btn_compare_selected.label.text = 'NEW COMPARISON'
            self.btn_compare_selected.bg_color = COL_BLUE
            self.btn_compare_selected._bgcol.rgba = COL_BLUE
            self.btn_compare_selected.fg_color = (1, 1, 1, 1)
            self.btn_compare_selected.disabled = False
            self.btn_compare_selected.opacity = 1.0
        else:
            self.btn_compare_selected.label.text = 'COMPARE (BEFORE vs AFTER)'
            self.btn_compare_selected.bg_color = COL_YELLOW
            self.btn_compare_selected._bgcol.rgba = COL_YELLOW
            self.btn_compare_selected.fg_color = (0.02, 0.03, 0.06, 1)

        def _make_col_header(is_comparison=False):
            header = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(28),
                               spacing=dp(6), padding=[dp(10), 0])
            with header.canvas.before:
                Color(*COL_PANEL)
                header.bg_rect = Rectangle(size=header.size, pos=header.pos)
            header.bind(pos=lambda inst, v: setattr(inst.bg_rect, 'pos', inst.pos),
                        size=lambda inst, v: setattr(inst.bg_rect, 'size', inst.size))

            header.add_widget(Label(text='', size_hint_x=None, width=dp(30)))
            if is_comparison:
                cols = [("Client", 0.26), ("Area", 0.26), ("Pairing", 0.22),
                        ("Type", 0.14), ("Cam", 0.12)]
            else:
                cols = [("Client", 0.26), ("Area", 0.26), ("Side/Site", 0.22),
                        ("Cond", 0.14), ("Cam", 0.12)]
            for t, w in cols:
                header.add_widget(Label(text=t, size_hint_x=w, bold=True, font_size='11sp', color=COL_TEXT_DIM))
            header.add_widget(Label(text="Action", size_hint_x=None, width=dp(64), bold=True, font_size='11sp', color=COL_TEXT_DIM))
            return header

        if is_comp_mode:
            comps = [r for r in self.recordings if r.get('condition') == 'Comparison' or '_vs_' in r.get('filename', '')]
            comp_box = BoxLayout(orientation='vertical', spacing=dp(4), size_hint=(1, 1))
            comp_box.add_widget(PlaybackSectionHeader("COMPARED VIDEOS (BEFORE vs AFTER)", count=len(comps), badge_color=COL_BLUE))
            comp_box.add_widget(_make_col_header(is_comparison=True))

            scroll = ScrollView(size_hint=(1, 1))
            layout = GridLayout(cols=1, spacing=dp(4), padding=[dp(4), dp(4)], size_hint_y=None)
            layout.bind(minimum_height=layout.setter('height'))
            scroll.add_widget(layout)

            if not comps:
                layout.add_widget(Label(
                    text="No comparison videos found yet. Click 'NEW COMPARISON' or select Before and After runs from Playback.",
                    size_hint_y=None, height=dp(44), color=COL_TEXT_DIM
                ))
            else:
                for rec in reversed(comps):
                    row = RecordingRowWidget(
                        rec=rec,
                        on_play=self.start_playback_video,
                        on_check=self.update_selection_count,
                        is_comp_mode=True
                    )
                    self.selection_checkboxes[rec['filename']] = row.cb
                    self.row_widgets[rec['filename']] = row
                    layout.add_widget(row)

            comp_box.add_widget(scroll)
            self.playback_content_area.add_widget(comp_box)
            self.update_selection_count()
            return

        # -------------------------------------------------------------
        # Playback Mode: SIDE-BY-SIDE (BEFORE ON LEFT, AFTER ON RIGHT)
        # -------------------------------------------------------------
        all_non_comp = [r for r in self.recordings if r.get('condition') != 'Comparison' and '_vs_' not in r.get('filename', '')]
        befores = [r for r in all_non_comp if r.get('condition') == 'Before']
        afters = [r for r in all_non_comp if r.get('condition') == 'After']

        side_by_side = BoxLayout(orientation='horizontal', spacing=dp(10), size_hint=(1, 1))

        # Left Column: BEFORE RUNS
        if filter_mode in ('ALL', 'BEFORE'):
            left_col = BoxLayout(orientation='vertical', spacing=dp(4), size_hint_x=0.5 if filter_mode == 'ALL' else 1.0)
            left_col.add_widget(PlaybackSectionHeader("BEFORE CLEANING RUNS (PRE-INSPECTION)", count=len(befores), badge_color=COL_YELLOW))
            left_col.add_widget(_make_col_header(is_comparison=False))

            left_scroll = ScrollView(size_hint=(1, 1))
            left_layout = GridLayout(cols=1, spacing=dp(4), padding=[dp(2), dp(4)], size_hint_y=None)
            left_layout.bind(minimum_height=left_layout.setter('height'))
            left_scroll.add_widget(left_layout)

            if not befores:
                left_layout.add_widget(Label(
                    text="No 'Before' recordings found.", size_hint_y=None, height=dp(44), color=COL_TEXT_DIM
                ))
            else:
                for rec in reversed(befores):
                    row = RecordingRowWidget(
                        rec=rec,
                        on_play=self.start_playback_video,
                        on_check=self.update_selection_count,
                        is_comp_mode=False
                    )
                    self.selection_checkboxes[rec['filename']] = row.cb
                    self.row_widgets[rec['filename']] = row
                    left_layout.add_widget(row)

            left_col.add_widget(left_scroll)
            side_by_side.add_widget(left_col)

        # Right Column: AFTER RUNS
        if filter_mode in ('ALL', 'AFTER'):
            right_col = BoxLayout(orientation='vertical', spacing=dp(4), size_hint_x=0.5 if filter_mode == 'ALL' else 1.0)
            right_col.add_widget(PlaybackSectionHeader("AFTER CLEANING RUNS (POST-INSPECTION)", count=len(afters), badge_color=COL_GREEN))
            right_col.add_widget(_make_col_header(is_comparison=False))

            right_scroll = ScrollView(size_hint=(1, 1))
            right_layout = GridLayout(cols=1, spacing=dp(4), padding=[dp(2), dp(4)], size_hint_y=None)
            right_layout.bind(minimum_height=right_layout.setter('height'))
            right_scroll.add_widget(right_layout)

            if not afters:
                right_layout.add_widget(Label(
                    text="No 'After' recordings found.", size_hint_y=None, height=dp(44), color=COL_TEXT_DIM
                ))
            else:
                for rec in reversed(afters):
                    row = RecordingRowWidget(
                        rec=rec,
                        on_play=self.start_playback_video,
                        on_check=self.update_selection_count,
                        is_comp_mode=False
                    )
                    self.selection_checkboxes[rec['filename']] = row.cb
                    self.row_widgets[rec['filename']] = row
                    right_layout.add_widget(row)

            right_col.add_widget(right_scroll)
            side_by_side.add_widget(right_col)

        self.playback_content_area.add_widget(side_by_side)
        self.update_selection_count()

    def toggle_select_all(self):
        if not self.selection_checkboxes:
            return
        all_selected = all(cb.active for cb in self.selection_checkboxes.values())
        for cb in self.selection_checkboxes.values():
            cb.active = not all_selected

    def _check_run_match(self, rec_a, rec_b):
        """
        Verifies if rec_a and rec_b belong to the same inspection run:
        Matches Client name, Area name, and Site/Side name.
        Case-insensitive and whitespace-trimmed.
        Returns:
          2 = Verified 3-way match: Client, Area, and Site/Side
          1 = Partial match: Client & Area
          0 = No match
        """
        if not rec_a or not rec_b:
            return 0
        def _n(v):
            return str(v or "").strip().lower()

        c_match = _n(rec_a.get('client')) == _n(rec_b.get('client'))
        a_match = _n(rec_a.get('area')) == _n(rec_b.get('area'))
        s_match = _n(rec_a.get('side')) == _n(rec_b.get('side'))

        if c_match and a_match and s_match:
            return 2
        elif c_match and a_match:
            return 1
        return 0

    def update_selection_count(self, *args):
        selected_fns = [f for f, cb in self.selection_checkboxes.items() if cb.active]
        n = len(selected_fns)

        self.btn_export_selected.disabled = (n == 0)
        self.btn_export_selected.opacity = 1 if n else 0.45
        self.btn_delete_selected.disabled = (n == 0)
        self.btn_delete_selected.opacity = 1 if n else 0.45

        is_comp_mode = (getattr(self, 'current_mode', 'playback') == 'comparison')
        if is_comp_mode:
            self.selection_label.text = f"{n} selected"
            self.btn_compare_selected.label.text = "NEW COMPARISON"
            self.btn_compare_selected.disabled = False
            self.btn_compare_selected.opacity = 1.0
            for row in self.row_widgets.values():
                row.set_highlight('selected' if row.cb.active else None)
            return

        # Find selected records
        selected_recs = [r for r in self.recordings if r['filename'] in selected_fns]
        selected_befores = [r for r in selected_recs if r.get('condition') == 'Before']
        selected_afters = [r for r in selected_recs if r.get('condition') == 'After']

        # DYNAMIC RECIPROCAL HIGHLIGHTING (VERIFIED WITH CLIENT, SITE, AREA):
        if len(selected_befores) == 1 and len(selected_afters) == 0:
            sel_b = selected_befores[0]
            c_name = sel_b.get('client', '')
            a_name = sel_b.get('area', '')
            s_name = sel_b.get('side', '')
            self.selection_label.text = f"Before selected: {c_name} | {a_name} | {s_name}"
            self.btn_compare_selected.label.text = "SELECT MATCHING AFTER RUN"
            self.btn_compare_selected.disabled = True
            self.btn_compare_selected.opacity = 0.65
            self.btn_compare_selected.bg_color = COL_YELLOW
            self.btn_compare_selected._bgcol.rgba = COL_YELLOW
            self.btn_compare_selected.fg_color = (0.02, 0.03, 0.06, 1)

            for fn, row in self.row_widgets.items():
                if row.cb.active:
                    row.set_highlight('selected')
                elif row.condition == 'After':
                    match_code = self._check_run_match(sel_b, row.rec)
                    if match_code == 2:
                        row.set_highlight('highlight_after', recommended=True, match_text="MATCH (SITE+AREA)")
                    elif match_code == 1:
                        row.set_highlight('highlight_after', recommended=False, match_text="DIFF SITE")
                    else:
                        row.set_highlight(None)
                else:
                    row.set_highlight(None)

        elif len(selected_afters) == 1 and len(selected_befores) == 0:
            sel_a = selected_afters[0]
            c_name = sel_a.get('client', '')
            a_name = sel_a.get('area', '')
            s_name = sel_a.get('side', '')
            self.selection_label.text = f"After selected: {c_name} | {a_name} | {s_name}"
            self.btn_compare_selected.label.text = "SELECT MATCHING BEFORE RUN"
            self.btn_compare_selected.disabled = True
            self.btn_compare_selected.opacity = 0.65
            self.btn_compare_selected.bg_color = COL_GREEN
            self.btn_compare_selected._bgcol.rgba = COL_GREEN
            self.btn_compare_selected.fg_color = (1, 1, 1, 1)

            for fn, row in self.row_widgets.items():
                if row.cb.active:
                    row.set_highlight('selected')
                elif row.condition == 'Before':
                    match_code = self._check_run_match(sel_a, row.rec)
                    if match_code == 2:
                        row.set_highlight('highlight_before', recommended=True, match_text="MATCH (SITE+AREA)")
                    elif match_code == 1:
                        row.set_highlight('highlight_before', recommended=False, match_text="DIFF SITE")
                    else:
                        row.set_highlight(None)
                else:
                    row.set_highlight(None)

        elif len(selected_befores) == 1 and len(selected_afters) == 1:
            sel_b = selected_befores[0]
            sel_a = selected_afters[0]
            match_code = self._check_run_match(sel_b, sel_a)
            if match_code == 2:
                self.selection_label.text = f"Verified: {sel_b.get('client')} | {sel_b.get('area')} | {sel_b.get('side')}"
            elif match_code == 1:
                self.selection_label.text = f"Pair: {sel_b.get('client')} ({sel_b.get('side')} vs {sel_a.get('side')})"
            else:
                self.selection_label.text = f"Pair: {sel_b.get('client')} vs {sel_a.get('client')}"

            self.btn_compare_selected.label.text = "COMPARE SELECTED RUNS"
            self.btn_compare_selected.disabled = False
            self.btn_compare_selected.opacity = 1.0
            self.btn_compare_selected.bg_color = (0.12, 0.65, 0.35, 1)
            self.btn_compare_selected._bgcol.rgba = (0.12, 0.65, 0.35, 1)
            self.btn_compare_selected.fg_color = (1, 1, 1, 1)

            for fn, row in self.row_widgets.items():
                if row.cb.active:
                    row.set_highlight('selected')
                else:
                    row.set_highlight(None)

        else:
            self.selection_label.text = f"{n} selected"
            base_recs = [r for r in self.recordings if not '_vs_' in r.get('filename', '')]
            can_compare = (n == 2) or (n == 0 and len(base_recs) >= 2)
            self.btn_compare_selected.label.text = "COMPARE (BEFORE vs AFTER)"
            self.btn_compare_selected.disabled = not can_compare
            self.btn_compare_selected.opacity = 1.0 if can_compare else 0.45
            self.btn_compare_selected.bg_color = COL_YELLOW
            self.btn_compare_selected._bgcol.rgba = COL_YELLOW
            self.btn_compare_selected.fg_color = (0.02, 0.03, 0.06, 1)

            for fn, row in self.row_widgets.items():
                row.set_highlight('selected' if row.cb.active else None)

    def get_selected_filenames(self):
        return [f for f, cb in self.selection_checkboxes.items() if cb.active]

    def start_playback_video(self, rec):
        raw_filename = rec.get('filename', '')
        filename = os.path.normpath(str(raw_filename).replace('\\', os.sep))
        if not os.path.isabs(filename):
            base_dir = os.path.dirname(self.video_dir)
            cand1 = os.path.join(base_dir, filename)
            cand2 = os.path.join(self.video_dir, filename)
            if os.path.exists(cand1):
                filename = cand1
            elif os.path.exists(cand2):
                filename = cand2

        if not os.path.exists(filename):
            basename = os.path.basename(filename)
            alt_path = os.path.join(self.video_dir, basename)
            merged_path = os.path.join(self.video_dir, "merged_videos", basename)
            home_merged = os.path.expanduser(f"~/ductbot_recordings/merged_videos/{basename}")
            if os.path.exists(alt_path):
                filename = alt_path
            elif os.path.exists(merged_path):
                filename = merged_path
            elif os.path.exists(home_merged):
                filename = home_merged
            else:
                print(f"[Playback] Playback file not found: {raw_filename}")
                return

        self.playback_mode = True
        self.display_area.clear_widgets()
        self.display_area.add_widget(self.video_overlay)
        if self.capture:
            self.capture.release()
            self.capture = None
        self.capture = cv2.VideoCapture(filename)
        if not self.capture.isOpened():
            self.capture = cv2.VideoCapture(filename, cv2.CAP_FFMPEG)

        if not self.capture.isOpened():
            print(f"[Playback] Failed to open video capture for: {filename}")
            return

        self.is_paused = False
        self._viewing_single_video = True
        self.lane_enabled = False
        if hasattr(self, 'video_overlay'):
            self.video_overlay.set_lane_active(False)
            self.video_overlay.set_flip_visible(False)
            is_comp = (rec.get('condition') == 'Comparison')
            self.video_overlay.set_mode_badge(False, "COMPARISON" if is_comp else "PLAYBACK")

        if hasattr(self, 'playback_info_panel') and self.playback_info_panel.parent:
            self.body.remove_widget(self.playback_info_panel)

        callbacks = {'stop': lambda x: self.stop_video()}
        self.playback_info_panel = PlaybackInfoPanel(callbacks, rec)
        self._refresh_status_row()

    def _reload_and_populate(self):
        self.recordings = self.load_recordings()
        self.populate_playback_list()

    def open_comparison_dialog(self):
        selected_fns = self.get_selected_filenames()
        before_rec = None
        after_rec = None

        if len(selected_fns) == 2:
            recs = [r for r in self.recordings if r['filename'] in selected_fns]
            if len(recs) == 2:
                if recs[0].get('condition') == 'Before' and recs[1].get('condition') == 'After':
                    before_rec, after_rec = recs[0], recs[1]
                elif recs[1].get('condition') == 'Before' and recs[0].get('condition') == 'After':
                    before_rec, after_rec = recs[1], recs[0]
                else:
                    recs.sort(key=lambda r: r.get('serial', 0))
                    before_rec, after_rec = recs[0], recs[1]
        elif len(selected_fns) == 0:
            befores = [r for r in self.recordings if r.get('condition') == 'Before' and not '_vs_' in r.get('filename', '')]
            afters = [r for r in self.recordings if r.get('condition') == 'After' and not '_vs_' in r.get('filename', '')]
            if befores and afters:
                before_rec = befores[-1]
                after_rec = afters[-1]
            elif len(self.recordings) >= 2:
                cand = [r for r in self.recordings if not '_vs_' in r.get('filename', '')]
                if len(cand) >= 2:
                    before_rec = cand[-2]
                    after_rec = cand[-1]

        if not before_rec or not after_rec:
            self.show_message(
                "Video Comparison",
                "Please select 2 recordings (a 'Before' and an 'After' run) from the list to compare."
            )
            return

        def _do_start_comparison(b_rec, a_rec, popup):
            def _worker():
                b_vid = b_rec.get('filename')
                a_vid = a_rec.get('filename')
                b_base = os.path.splitext(b_vid)[0]
                a_base = os.path.splitext(a_vid)[0]
                b_csv = f"{b_base}_checkpoints.csv"
                a_csv = f"{a_base}_checkpoints.csv"

                # 1. Attempt ROS 2 comparison trigger
                triggered = False
                if hasattr(self, 'camera_bridge'):
                    triggered = self.camera_bridge.trigger_video_comparison(
                        before_video=b_vid, after_video=a_vid,
                        before_csv=b_csv if os.path.exists(b_csv) else None,
                        after_csv=a_csv if os.path.exists(a_csv) else None
                    )

                if triggered:
                    # Poll ROS 2 comparison status
                    start_t = time.time()
                    out_vid = None
                    while time.time() - start_t < 180.0:
                        status_info = self.camera_bridge.get_comparison_status()
                        pct = status_info.get("progress_percent", 0.0)
                        st = status_info.get("status", "Processing...")
                        Clock.schedule_once(lambda dt, p=pct, s=st: popup.update_progress(p, s))
                        if "SUCCESS" in st or pct >= 100.0:
                            if "Video saved to " in st:
                                out_vid = st.split("Video saved to ")[-1].strip()
                            break
                        if "FAILED" in st or "ERROR" in st:
                            break
                        time.sleep(0.5)

                    if not out_vid:
                        b_name = os.path.basename(os.path.splitext(b_vid)[0])
                        a_name = os.path.basename(os.path.splitext(a_vid)[0])
                        candidate = os.path.join(self.video_dir, "merged_videos", f"{b_name}_vs_{a_name}.mp4")
                        if os.path.exists(candidate):
                            out_vid = candidate

                    if out_vid and os.path.exists(out_vid):
                        def _save_and_populate_ros(dt, f_path=out_vid):
                            popup.set_result_file(f_path)
                            try:
                                cursor = self.db_conn.cursor()
                                cursor.execute(
                                    "INSERT INTO recordings (client, area, side, condition, camera, filename) VALUES (?, ?, ?, ?, ?, ?)",
                                    (b_rec.get('client', ''), b_rec.get('area', ''), b_rec.get('side', ''), "Comparison", "Both", f_path)
                                )
                                self.db_conn.commit()
                            except Exception as err:
                                print(f"Error inserting comparison into DB: {err}")
                            self.set_mode('comparison')
                            self._reload_and_populate()

                        Clock.schedule_once(_save_and_populate_ros)
                else:
                    # 2. Run directly via VideoLocalization Python engine
                    if LOCALIZATION_MODULES_AVAILABLE:
                        def _prog_cb(pct, status_text):
                            Clock.schedule_once(lambda dt, p=pct, s=status_text: popup.update_progress(p, s))

                        engine = VideoLocalization(output_dir=self.video_dir, resample_spacing_m=0.02)
                        res = engine.compare_runs(
                            before_video=b_vid, after_video=a_vid,
                            before_csv=b_csv if os.path.exists(b_csv) else None,
                            after_csv=a_csv if os.path.exists(a_csv) else None,
                            progress_callback=_prog_cb
                        )
                        if res.get('success'):
                            out_vid = res.get('output_video')
                            def _save_and_populate_py(dt, f_path=out_vid):
                                popup.set_result_file(f_path)
                                try:
                                    cursor = self.db_conn.cursor()
                                    cursor.execute(
                                        "INSERT INTO recordings (client, area, side, condition, camera, filename) VALUES (?, ?, ?, ?, ?, ?)",
                                        (b_rec.get('client', ''), b_rec.get('area', ''), b_rec.get('side', ''), "Comparison", "Both", f_path)
                                    )
                                    self.db_conn.commit()
                                except Exception as err:
                                    print(f"Error inserting comparison into DB: {err}")
                                self.set_mode('comparison')
                                self._reload_and_populate()

                            Clock.schedule_once(_save_and_populate_py)
                        else:
                            msg = res.get('message', 'Comparison failed.')
                            Clock.schedule_once(lambda dt, m=msg: popup.update_progress(0.0, f"Error: {m}"))
                    else:
                        Clock.schedule_once(lambda dt: popup.update_progress(0.0, "VideoLocalization module not found."))

            threading.Thread(target=_worker, daemon=True).start()

        def _do_play_result(result_path):
            rec = {
                "serial": 0,
                "client": before_rec.get('client', ''),
                "area": before_rec.get('area', ''),
                "side": before_rec.get('side', ''),
                "condition": "Comparison",
                "camera": "Both",
                "filename": result_path
            }
            self.start_playback_video(rec)

        popup = VideoComparisonPopup(
            before_rec=before_rec,
            after_rec=after_rec,
            on_start_comparison=_do_start_comparison,
            on_play_result=_do_play_result
        )
        popup.open()

    def play_pause(self, instance):
        if not self.playback_mode:
            # Live Mode -> Recording Control
            if not self.is_recording:
                self.open_recording_form()
            else:
                self.is_recording_paused = not self.is_recording_paused
                if self.is_recording_paused:
                    self._record_elapsed += time.time() - self._record_start_time
                    self.control_bar.set_recording_label('RESUME RECORDING')
                else:
                    self._record_start_time = time.time()
                    self.control_bar.set_recording_label('PAUSE RECORDING')
        else:
            # Playback Mode -> Play/Pause video
            self.is_paused = not self.is_paused

    def open_recording_form(self):
        content = BoxLayout(orientation='vertical', spacing=dp(8), padding=[dp(16), dp(10)])
        with content.canvas.before:
            Color(0.04, 0.06, 0.10, 1.0)
            content._bg = RoundedRectangle(pos=content.pos, size=content.size, radius=[dp(12)])
            Color(*COL_BORDER)
            content._border = Line(rounded_rectangle=(content.x, content.y, content.width, content.height, dp(12)), width=1.2)
        content.bind(
            pos=lambda inst, v: setattr(inst._bg, 'pos', inst.pos) or setattr(inst._border, 'rounded_rectangle', (inst.x, inst.y, inst.width, inst.height, dp(12))),
            size=lambda inst, v: setattr(inst._bg, 'size', inst.size) or setattr(inst._border, 'rounded_rectangle', (inst.x, inst.y, inst.width, inst.height, dp(12)))
        )

        # -------------------------------------------------------------
        # TOP SECTION: RECORDING DETAILS FORM
        # -------------------------------------------------------------
        header_row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(12))

        icon_box = BoxLayout(size_hint=(None, None), size=(dp(42), dp(42)))
        with icon_box.canvas.before:
            Color(*COL_PANEL_ALT)
            icon_bg = RoundedRectangle(pos=icon_box.pos, size=icon_box.size, radius=[dp(8)])
            Color(*COL_BORDER)
            icon_border = Line(rounded_rectangle=(*icon_box.pos, *icon_box.size, dp(8)), width=1.1)
        def _update_icon_box(instance, value):
            icon_bg.pos = instance.pos
            icon_bg.size = instance.size
            icon_border.rounded_rectangle = (*instance.pos, *instance.size, dp(8))
        icon_box.bind(pos=_update_icon_box, size=_update_icon_box)
        icon_anchor = AnchorLayout()
        icon_anchor.add_widget(VideoIcon(color=COL_BLUE, size_dp=22))
        icon_box.add_widget(icon_anchor)
        header_row.add_widget(icon_box)

        title_box = BoxLayout(orientation='vertical', size_hint_x=0.4)
        title_lbl = Label(text='START RECORDING', bold=True, font_size='16sp', color=COL_TEXT,
                           halign='left', valign='bottom')
        title_lbl.bind(size=lambda w, *_a: setattr(w, 'text_size', w.size))
        subtitle_lbl = Label(text='Enter run details then start inspection', font_size='11sp', color=COL_TEXT_DIM,
                              halign='left', valign='top')
        subtitle_lbl.bind(size=lambda w, *_a: setattr(w, 'text_size', w.size))
        title_box.add_widget(title_lbl)
        title_box.add_widget(subtitle_lbl)
        header_row.add_widget(title_box)

        # Active input indicator badge
        self.lbl_active_target = Label(
            text='INPUT: CLIENT NAME', bold=True, font_size='11sp', color=COL_BLUE,
            size_hint_x=0.5, halign='right', valign='middle'
        )
        self.lbl_active_target.bind(size=lambda w, *_a: setattr(w, 'text_size', w.size))
        header_row.add_widget(self.lbl_active_target)

        close_anchor = AnchorLayout(size_hint_x=None, width=dp(36), anchor_x='right', anchor_y='top')
        close_btn = RoundedButton(
            text='', icon_cls=CloseIcon, icon_color=COL_TEXT_DIM, bg_color=(0, 0, 0, 0),
            size_hint=(None, None), size=(dp(34), dp(34)),
        )
        close_btn.bind(on_press=lambda x: self.popup.dismiss())
        close_anchor.add_widget(close_btn)
        header_row.add_widget(close_anchor)
        content.add_widget(header_row)

        # Fields row: Client Name | Area Name | Side/Site Name
        fields_row = BoxLayout(orientation='horizontal', spacing=dp(10), size_hint_y=None, height=dp(48))
        self.inp_client = FormField(PersonIcon, 'Client Name', size_hint_x=0.33)
        self.inp_area = FormField(MapIcon, 'Area Name', size_hint_x=0.33)
        self.inp_side = FormField(GridIcon, 'Side / Site Name', size_hint_x=0.33)
        fields_row.add_widget(self.inp_client)
        fields_row.add_widget(self.inp_area)
        fields_row.add_widget(self.inp_side)
        content.add_widget(fields_row)

        # Space between name fields and before/after selection
        content.add_widget(Widget(size_hint_y=None, height=dp(12)))

        # Controls row: Condition + Camera + Start Recording button
        controls_row = BoxLayout(orientation='horizontal', spacing=dp(10), size_hint_y=None, height=dp(44))

        # Condition buttons
        cond_box = BoxLayout(spacing=dp(6), size_hint_x=0.35)
        cond_lbl = Label(text='Condition:', bold=True, font_size='12sp', color=COL_TEXT_DIM, size_hint_x=None, width=dp(70))
        cond_box.add_widget(cond_lbl)
        self.btn_cond_before = SegmentButton(text='Before', icon_cls=SunIcon, group='condition')
        self.btn_cond_after = SegmentButton(text='After', icon_cls=SunIcon, group='condition')
        self.btn_cond_before.state = 'down'
        cond_box.add_widget(self.btn_cond_before)
        cond_box.add_widget(self.btn_cond_after)
        controls_row.add_widget(cond_box)

        # Camera buttons
        cam_box = BoxLayout(spacing=dp(6), size_hint_x=0.35)
        cam_lbl = Label(text='Camera:', bold=True, font_size='12sp', color=COL_TEXT_DIM, size_hint_x=None, width=dp(60))
        cam_box.add_widget(cam_lbl)
        active_cam = self.camera_bridge.get_active_camera() if hasattr(self, 'camera_bridge') else 'front'
        self.btn_cam_front = SegmentButton(text='Front', icon_cls=CameraIcon, group='camera')
        self.btn_cam_rear = SegmentButton(text='Rear', icon_cls=CameraIcon, group='camera')
        if active_cam == 'rear':
            self.btn_cam_rear.state = 'down'
        else:
            self.btn_cam_front.state = 'down'
        cam_box.add_widget(self.btn_cam_front)
        cam_box.add_widget(self.btn_cam_rear)
        controls_row.add_widget(cam_box)

        submit_btn = RoundedButton(
            text='START RECORDING', icon_cls=SendIcon, icon_color=(1, 1, 1, 1),
            bg_color=COL_RED, fg_color=(1, 1, 1, 1), size_hint_x=0.30, font_size=12,
        )
        submit_btn.bind(on_press=self.submit_recording_form)
        controls_row.add_widget(submit_btn)
        content.add_widget(controls_row)

        # Space between before/after selection and keyboard
        content.add_widget(Widget(size_hint_y=None, height=dp(14)))

        # -------------------------------------------------------------
        # BOTTOM SECTION: ON-SCREEN KEYBOARD
        # -------------------------------------------------------------
        self.active_input = self.inp_client.input

        def _set_active(field_input, name):
            self.active_input = field_input
            self.lbl_active_target.text = f"INPUT: {name.upper()}"

        self.inp_client.input.bind(focus=lambda inst, val: _set_active(inst, "Client Name") if val else None)
        self.inp_area.input.bind(focus=lambda inst, val: _set_active(inst, "Area Name") if val else None)
        self.inp_side.input.bind(focus=lambda inst, val: _set_active(inst, "Side / Site") if val else None)

        def _advance_field():
            if self.active_input == self.inp_client.input:
                self.inp_area.input.focus = True
                _set_active(self.inp_area.input, "Area Name")
            elif self.active_input == self.inp_area.input:
                self.inp_side.input.focus = True
                _set_active(self.inp_side.input, "Side / Site")
            else:
                self.inp_client.input.focus = True
                _set_active(self.inp_client.input, "Client Name")

        self.on_screen_keyboard = OnScreenKeyboard(
            get_target_input=lambda: self.active_input,
            on_submit=lambda: self.submit_recording_form(submit_btn),
            on_next=_advance_field,
            size_hint_y=None,
            height=dp(285),
        )
        content.add_widget(self.on_screen_keyboard)

        # Automatically focus the first input field
        Clock.schedule_once(lambda dt: setattr(self.inp_client.input, 'focus', True), 0.1)

        self.popup = Popup(
            title='', separator_height=0, content=content,
            size_hint=(0.88, None), height=dp(525),
            pos_hint={'center_x': 0.5, 'center_y': 0.5},
            background='',
            background_color=(0, 0, 0, 0),
            overlay_color=[0.02, 0.03, 0.06, 1.0],
        )
        self.popup.open()

    def reset_submit_btn(self, instance):
        instance.label.text = 'START RECORDING'
        instance.set_bg(COL_RED)

    def submit_recording_form(self, instance):
        client = self.inp_client.text.strip()
        area = self.inp_area.text.strip()
        side = self.inp_side.text.strip()

        cond_selected = self.btn_cond_before.state == 'down' or self.btn_cond_after.state == 'down'
        cam_selected = self.btn_cam_front.state == 'down' or self.btn_cam_rear.state == 'down'

        if not client or not area or not side or not cond_selected or not cam_selected:
            instance.label.text = 'Please fill all fields!'
            instance.set_bg(COL_RED)
            Clock.schedule_once(lambda dt: self.reset_submit_btn(instance), 2)
            return
        
        timestamp = int(time.time())
        filename = os.path.join(self.video_dir, f"video_{timestamp}.mp4")
        
        condition = "Before" if getattr(self, 'btn_cond_before', None) and self.btn_cond_before.state == 'down' else "After"
        camera = "Front" if getattr(self, 'btn_cam_front', None) and self.btn_cam_front.state == 'down' else "Rear"
        
        cursor = self.db_conn.cursor()
        cursor.execute(
            "INSERT INTO recordings (client, area, side, condition, camera, filename) VALUES (?, ?, ?, ?, ?, ?)",
            (client, area, side, condition, camera, filename)
        )
        self.db_conn.commit()
        
        # Reload recordings to update the UI list properly
        self.recordings = self.load_recordings()
        serial_no = self.recordings[-1]['serial'] if self.recordings else 0
        
        # Save sidecar metadata JSON
        meta_filename = os.path.join(self.video_dir, f"video_{timestamp}.json")
        frame_times_csv = filename.replace(".mp4", "_frame_times.csv")
        checkpoints_csv = filename.replace(".mp4", "_checkpoints.csv")
        meta_data = {
            "serial": serial_no,
            "client": client,
            "area": area,
            "side": side,
            "condition": condition,
            "camera": camera,
            "timestamp": timestamp,
            "filename": filename,
            "frame_times_csv": frame_times_csv,
            "checkpoints_csv": checkpoints_csv,
        }
        with open(meta_filename, 'w') as f:
            json.dump(meta_data, f, indent=4)
        
        self.popup.dismiss()
        
        self.start_recording(filename)

    def start_recording(self, filename):
        self.is_recording = True
        self.is_recording_paused = False
        self._record_start_time = time.time()
        self._record_elapsed = 0.0
        self._recorded_frame_count = 0
        self.control_bar.set_recording_label('PAUSE RECORDING')

        # Reset & resume tracking on localization node
        if hasattr(self, 'camera_bridge'):
            self.camera_bridge.reset_odometry()
            self.camera_bridge.resume_tracking()
        self.video_overlay.reset_odometry_display()

        # Open frame_times CSV for synchronizing each written frame
        self._frame_times_path = filename.replace(".mp4", "_frame_times.csv")
        try:
            self._frame_times_file = open(self._frame_times_path, mode='w', newline='')
            self._frame_times_writer = csv.writer(self._frame_times_file)
            self._frame_times_writer.writerow(["timestamp", "written_frame_index"])
        except Exception as e:
            print(f"Error initializing frame_times.csv: {e}")
            self._frame_times_file = None
            self._frame_times_writer = None

        # Initialize spatial checkpoint logger if available
        self._checkpoints_path = filename.replace(".mp4", "_checkpoints.csv")
        if LOCALIZATION_MODULES_AVAILABLE:
            try:
                self._active_checkpoint_logger = CheckpointLogger(
                    output_file=self._checkpoints_path,
                    interval_m=0.01
                )
                self._active_checkpoint_logger.log_event("START")
            except Exception as e:
                print(f"Error initializing CheckpointLogger: {e}")
                self._active_checkpoint_logger = None

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        width, height = 1280, 720
        if not self.playback_mode and hasattr(self, 'camera_bridge'):
            has_f, sample_f = self.camera_bridge.get_active_frame()
            if has_f and sample_f is not None:
                height, width = sample_f.shape[:2]
        elif self.capture:
            w = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if w > 0 and h > 0:
                width, height = w, h
        self.video_writer = cv2.VideoWriter(filename, fourcc, 20.0, (width, height))
        print(f"Recording started: {filename} ({width}x{height})")

    def stop_recording(self):
        self.is_recording = False
        self.is_recording_paused = False
        self._record_start_time = None
        self._record_elapsed = 0.0
        self.control_bar.set_recording_label('START RECORDING')
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None

        if self._frame_times_file:
            try:
                self._frame_times_file.close()
            except Exception:
                pass
            self._frame_times_file = None
            self._frame_times_writer = None

        if self._active_checkpoint_logger:
            try:
                self._active_checkpoint_logger.log_event("STOP")
            except Exception:
                pass
            self._active_checkpoint_logger = None

        if hasattr(self, 'camera_bridge'):
            self.camera_bridge.pause_tracking()

        print("Recording stopped.")

    def get_record_elapsed(self):
        if not self.is_recording:
            return 0.0
        if self.is_recording_paused or self._record_start_time is None:
            return self._record_elapsed
        return self._record_elapsed + (time.time() - self._record_start_time)

    def stop_video(self):
        if self.playback_mode:
            if self.capture:
                self.capture.release()
                self.capture = None
                self._viewing_single_video = False
                self._refresh_status_row()

                # Go back to the video list
                self.display_area.clear_widgets()
                self.display_area.add_widget(self.playback_container)
                self.populate_playback_list()
        else:
            # In Live Mode, this stops the recording!
            if self.is_recording:
                self.stop_recording()

    def toggle_lane(self):
        self.lane_enabled = not self.lane_enabled
        self.video_overlay.set_lane_active(self.lane_enabled)

    def flip_camera(self):
        self.is_camera_flipped = not getattr(self, 'is_camera_flipped', False)
        print(f"Camera horizontal flip: {self.is_camera_flipped}")

    def switch_camera(self):
        if hasattr(self, 'camera_bridge'):
            new_cam = self.camera_bridge.toggle_camera()
            info = self.camera_bridge.get_source_info(new_cam)
            self.video_overlay.set_active_camera(new_cam, info.get('source', ''))
            print(f"Switched active camera to: {new_cam.upper()} ({info.get('source', '')})")

    def toggle_map(self):
        self.map_enabled = not self.map_enabled
        self.video_overlay.set_map_active(self.map_enabled)
        print(f"Trajectory map active: {self.map_enabled}")

    def reset_odometry(self):
        if hasattr(self, 'camera_bridge'):
            self.camera_bridge.reset_odometry()
        self.video_overlay.reset_odometry_display()
        print("Odometry origin reset to (0, 0, 0)")

    def _draw_lane_guides(self, frame):
        h, w = frame.shape[:2]
        center_x = w // 2
            
        # Left converging line
        pt_top_left = (int(w * 0.35), int(h * 0.6))
        pt_bottom_left = (int(w * 0.1), h)
        cv2.line(frame, pt_top_left, pt_bottom_left, CV2Colors.YELLOW, 3)
            
        # Right converging line
        pt_top_right = (int(w * 0.65), int(h * 0.6))
        pt_bottom_right = (int(w * 0.9), h)
        cv2.line(frame, pt_top_right, pt_bottom_right, CV2Colors.YELLOW, 3)
            
        # ---------- TOF CENTER ALIGNMENT ----------
        with self.sensor_lock:
            tof_l = self.sensor_data.get("TOF_L", 0)
            tof_r = self.sensor_data.get("TOF_R", 0)

        # Calculate offset based on difference
        try:
            tl = float(tof_l)
            tr = float(tof_r)
            diff = (tr - tl) if (math.isfinite(tl) and math.isfinite(tr)) else 0.0
        except (ValueError, TypeError):
            diff = 0.0
        scale = 0.15
        offset = int(diff * scale)
        offset = max(-200, min(200, offset))
        center_x_dynamic = center_x + offset

        # draw moving center marker
        cv2.drawMarker(frame, (center_x_dynamic, h - 20),
                    CV2Colors.GREEN,
                    cv2.MARKER_CROSS,
                    10,
                    2)

        # TOF numeric readouts are shown as native overlay widgets
        # (VideoOverlay.set_tof), not baked into the frame.
        return frame

    def update_frame(self, dt):
        if self.is_paused and self.playback_mode:
            return
            
        frame = None
        if self.playback_mode:
            if self.capture is not None:
                ret, frame = self.capture.read()
                if not ret:
                    # Loop video if it ends in playback mode
                    self.capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    return
        else:
            if hasattr(self, 'camera_bridge'):
                ret, frame = self.camera_bridge.get_active_frame()
                if not ret or frame is None:
                    return

        if frame is not None:
            # Save clean frame if recording in live mode
            if getattr(self, 'is_recording', False) and getattr(self, 'video_writer', None):
                if not getattr(self, 'is_recording_paused', False):
                    self.video_writer.write(frame)
                    self._recorded_frame_count += 1
                    now = time.time()
                    if getattr(self, '_frame_times_writer', None):
                        try:
                            self._frame_times_writer.writerow([now, self._recorded_frame_count])
                            self._frame_times_file.flush()
                        except Exception:
                            pass

                    # Feed spatial checkpoint logger
                    if getattr(self, '_active_checkpoint_logger', None):
                        try:
                            tdata = self.esp32_reader.get_telemetry() if hasattr(self, 'esp32_reader') else {}
                            loc_data = self.camera_bridge.get_localization_data() if hasattr(self, 'camera_bridge') else {}
                            tot_dist = float(loc_data.get("total_distance_m") or tdata.get("total_distance_m", 0.0))
                            cur_x = float(loc_data.get("x", tdata.get("x", 0.0)))
                            cur_y = float(loc_data.get("y", tdata.get("y", 0.0)))
                            cur_yaw = float(loc_data.get("yaw", tdata.get("yaw", 0.0)))
                            def _c_int(v, d=0):
                                try:
                                    f = float(v)
                                    return int(f) if math.isfinite(f) else d
                                except (ValueError, TypeError):
                                    return d
                            tof = [_c_int(tdata.get("TOF_L", loc_data.get("TOF_L", 0))),
                                   _c_int(tdata.get("TOF_R", loc_data.get("TOF_R", 0)))]
                            env = [
                                float(tdata.get("temperature", loc_data.get("temperature", 0.0))),
                                float(tdata.get("humidity", loc_data.get("humidity", 0.0))),
                                float(tdata.get("air_quality", loc_data.get("air_quality", 0.0))),
                                float(tdata.get("pressure", loc_data.get("pressure", 0.0))),
                                float(tdata.get("gas_ppm", loc_data.get("gas_ppm", 0.0))),
                                float(tdata.get("status_code", loc_data.get("status_code", 0.0))),
                            ]
                            self._active_checkpoint_logger.update(
                                total_distance=tot_dist,
                                x=cur_x,
                                y=cur_y,
                                yaw=cur_yaw,
                                tof=tof,
                                env=env,
                            )
                        except Exception as e:
                            pass

            if getattr(self, 'is_camera_flipped', False):
                frame = cv2.flip(frame, 1)

            if self.lane_enabled:
                frame = self._draw_lane_guides(frame)

            # We need to flip it vertically because Kivy's origin is bottom-left
            frame = cv2.flip(frame, 0)
            buffer = frame.tobytes()
            texture = Texture.create(size=(frame.shape[1], frame.shape[0]), colorfmt='bgr')
            texture.blit_buffer(buffer, colorfmt='bgr', bufferfmt='ubyte')
            self.image.texture = texture
            self.image.color = (1, 1, 1, 1)

    def update_dashboard(self, dt):
        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(self.get_record_elapsed()))
        self.video_overlay.set_recording(self.is_recording, elapsed_str)
        self.video_overlay.set_mode_badge(not self.playback_mode, "LIVE MODE")
        self.video_overlay.set_flip_visible(not self.playback_mode)

        # Coordinate ROS 2 localization bridge with telemetry reader
        loc_data = {}
        if hasattr(self, 'camera_bridge'):
            loc_data = self.camera_bridge.get_localization_data()
            if loc_data.get("has_localization") and hasattr(self, 'esp32_reader'):
                self.esp32_reader.update_from_bridge(loc_data)

        if hasattr(self, 'esp32_reader'):
            tdata = self.esp32_reader.get_telemetry()
            self.video_overlay.update_telemetry(tdata)
            with self.sensor_lock:
                self.sensor_data["TOF_L"] = tdata.get("TOF_L", 100)
                self.sensor_data["TOF_R"] = tdata.get("TOF_R", 100)



        if not self.playback_mode and hasattr(self, 'camera_bridge'):
            info = self.camera_bridge.get_source_info()
            self.video_overlay.set_active_camera(info.get('camera', 'front'), info.get('source', ''))
            self.header.set_live_mode(True)
        else:
            self.header.set_live_mode(not self.playback_mode and self.capture is not None)

    def get_usb_drives(self):
        if sys.platform == 'win32':
            drive_bitmask = ctypes.cdll.kernel32.GetLogicalDrives()
            drives = []
            for i, letter in enumerate(string.ascii_uppercase):
                if (drive_bitmask >> i) & 1:
                    drives.append(f"{letter}:\\")
            usb_drives = [d for d in drives if ctypes.cdll.kernel32.GetDriveTypeW(d) == 2]
            return usb_drives
        else:
            usb_drives = []
            user = os.environ.get('USER', 'roboserv4i')
            candidate_dirs = [f"/media/{user}", "/media", "/run/media", f"/run/media/{user}", "/mnt"]
            for base_dir in candidate_dirs:
                if os.path.exists(base_dir):
                    try:
                        for item in os.listdir(base_dir):
                            p = os.path.join(base_dir, item)
                            if os.path.isdir(p) and p not in usb_drives:
                                usb_drives.append(p)
                    except Exception:
                        pass
            return usb_drives

    def confirm_delete_selected(self):
        selected = self.get_selected_filenames()
        if not selected:
            return
        n = len(selected)
        self.show_confirm(
            title='Delete Recordings',
            message=f"Delete {n} recording{'s' if n != 1 else ''}? This cannot be undone.",
            on_confirm=lambda: self.delete_selected(selected),
            confirm_text='DELETE',
        )

    def delete_selected(self, filenames):
        cursor = self.db_conn.cursor()
        for f in filenames:
            norm_f = os.path.normpath(str(f).replace('\\', os.sep))
            try:
                if os.path.exists(norm_f):
                    os.remove(norm_f)
                else:
                    alt = os.path.join(self.video_dir, os.path.basename(norm_f))
                    if os.path.exists(alt):
                        os.remove(alt)
                json_file = norm_f.replace('.mp4', '.json')
                if os.path.exists(json_file):
                    os.remove(json_file)
                else:
                    alt_json = os.path.join(self.video_dir, os.path.basename(norm_f).replace('.mp4', '.json'))
                    if os.path.exists(alt_json):
                        os.remove(alt_json)
                for ext in ('_frame_times.csv', '_checkpoints.csv', '_match_map.json'):
                    sidecar = norm_f.replace('.mp4', ext)
                    if os.path.exists(sidecar):
                        os.remove(sidecar)
                    alt_sc = os.path.join(self.video_dir, os.path.basename(norm_f).replace('.mp4', ext))
                    if os.path.exists(alt_sc):
                        os.remove(alt_sc)
            except Exception as e:
                print(f"Failed to delete {f}: {e}")
            cursor.execute("DELETE FROM recordings WHERE filename = ? OR filename = ?", (f, norm_f))
        self.db_conn.commit()
        self.recordings = self.load_recordings()
        self.populate_playback_list()

    def export_selected(self):
        selected_files = self.get_selected_filenames()
        if not selected_files:
            self.show_message('Export', 'Select one or more recordings first.')
            return
        self.export_files(selected_files)

    def export_files(self, selected_files):
        # Step 2: Select USB and Folder
        usbs = self.get_usb_drives()
        if not usbs:
            content = BoxLayout(orientation='vertical', padding=[dp(20), dp(16)], spacing=dp(14))
            with content.canvas.before:
                Color(0.04, 0.06, 0.10, 1.0)
                content._bg = RoundedRectangle(pos=content.pos, size=content.size, radius=[dp(12)])
                Color(*COL_BORDER)
                content._border = Line(rounded_rectangle=(content.x, content.y, content.width, content.height, dp(12)), width=1.2)
            content.bind(
                pos=lambda inst, v: setattr(inst._bg, 'pos', inst.pos) or setattr(inst._border, 'rounded_rectangle', (inst.x, inst.y, inst.width, inst.height, dp(12))),
                size=lambda inst, v: setattr(inst._bg, 'size', inst.size) or setattr(inst._border, 'rounded_rectangle', (inst.x, inst.y, inst.width, inst.height, dp(12)))
            )

            # Header with warning icon
            hdr = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(40), spacing=dp(10))
            icon_box = BoxLayout(size_hint=(None, None), size=(dp(38), dp(38)))
            with icon_box.canvas.before:
                Color(*COL_PANEL_ALT)
                RoundedRectangle(pos=icon_box.pos, size=icon_box.size, radius=[dp(8)])
                Color(*COL_YELLOW)
                Line(rounded_rectangle=(*icon_box.pos, *icon_box.size, dp(8)), width=1.1)
            icon_anchor = AnchorLayout()
            icon_anchor.add_widget(UploadIcon(color=COL_YELLOW, size_dp=20))
            icon_box.add_widget(icon_anchor)
            hdr.add_widget(icon_box)

            t_box = BoxLayout(orientation='vertical')
            t_lbl = Label(text='NO USB STORAGE DETECTED', bold=True, font_size='14sp', color=COL_TEXT, halign='left', valign='bottom')
            t_lbl.bind(size=lambda w, *a: setattr(w, 'text_size', w.size))
            s_lbl = Label(text='Please connect a USB flash drive and try again', font_size='11sp', color=COL_TEXT_DIM, halign='left', valign='top')
            s_lbl.bind(size=lambda w, *a: setattr(w, 'text_size', w.size))
            t_box.add_widget(t_lbl)
            t_box.add_widget(s_lbl)
            hdr.add_widget(t_box)
            content.add_widget(hdr)

            # Close button
            btn = RoundedButton(text='CLOSE', bg_color=COL_BLUE, fg_color=(1, 1, 1, 1), size_hint_y=None, height=dp(38), font_size=12)
            content.add_widget(btn)

            popup = Popup(
                title='', separator_height=0, content=content,
                size_hint=(0.46, None), height=dp(145),
                pos_hint={'center_x': 0.5, 'center_y': 0.5},
                background='',
                background_color=(0, 0, 0, 0),
                overlay_color=[0.02, 0.03, 0.06, 1.0]
            )
            btn.bind(on_press=popup.dismiss)
            popup.open()
            return

        # Build clean USB display names (e.g. "SANDISK" instead of full path "/media/user/SANDISK")
        drive_map = {}
        for p in usbs:
            clean_name = os.path.basename(p.rstrip('/\\'))
            if not clean_name:
                clean_name = p
            display_name = clean_name
            dup_idx = 1
            while display_name in drive_map and drive_map[display_name] != p:
                display_name = f"{clean_name} ({dup_idx})"
                dup_idx += 1
            drive_map[display_name] = p

        drive_display_names = list(drive_map.keys())

        folder_content = BoxLayout(orientation='vertical', padding=[dp(20), dp(16)], spacing=dp(10))
        with folder_content.canvas.before:
            Color(0.04, 0.06, 0.10, 1.0)
            folder_content._bg = RoundedRectangle(pos=folder_content.pos, size=folder_content.size, radius=[dp(12)])
            Color(*COL_BORDER)
            folder_content._border = Line(rounded_rectangle=(folder_content.x, folder_content.y, folder_content.width, folder_content.height, dp(12)), width=1.2)
        folder_content.bind(
            pos=lambda inst, v: setattr(inst._bg, 'pos', inst.pos) or setattr(inst._border, 'rounded_rectangle', (inst.x, inst.y, inst.width, inst.height, dp(12))),
            size=lambda inst, v: setattr(inst._bg, 'size', inst.size) or setattr(inst._border, 'rounded_rectangle', (inst.x, inst.y, inst.width, inst.height, dp(12)))
        )

        # Header: Icon + Title + Close
        hdr = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(42), spacing=dp(10))
        icon_box = BoxLayout(size_hint=(None, None), size=(dp(40), dp(40)))
        with icon_box.canvas.before:
            Color(*COL_PANEL_ALT)
            RoundedRectangle(pos=icon_box.pos, size=icon_box.size, radius=[dp(8)])
            Color(*COL_BORDER)
            Line(rounded_rectangle=(*icon_box.pos, *icon_box.size, dp(8)), width=1.1)
        icon_anchor = AnchorLayout()
        icon_anchor.add_widget(UploadIcon(color=COL_BLUE, size_dp=22))
        icon_box.add_widget(icon_anchor)
        hdr.add_widget(icon_box)

        t_box = BoxLayout(orientation='vertical')
        t_lbl = Label(text='SELECT EXPORT DESTINATION', bold=True, font_size='15sp', color=COL_TEXT, halign='left', valign='bottom')
        t_lbl.bind(size=lambda w, *a: setattr(w, 'text_size', w.size))
        s_lbl = Label(text=f'Export {len(selected_files)} recording(s) and metadata to USB', font_size='11sp', color=COL_TEXT_DIM, halign='left', valign='top')
        s_lbl.bind(size=lambda w, *a: setattr(w, 'text_size', w.size))
        t_box.add_widget(t_lbl)
        t_box.add_widget(s_lbl)
        hdr.add_widget(t_box)

        close_anchor = AnchorLayout(size_hint_x=None, width=dp(34), anchor_x='right', anchor_y='top')
        close_btn = RoundedButton(
            text='', icon_cls=CloseIcon, icon_color=COL_TEXT_DIM, bg_color=(0, 0, 0, 0),
            size_hint=(None, None), size=(dp(34), dp(34))
        )
        close_anchor.add_widget(close_btn)
        hdr.add_widget(close_anchor)
        folder_content.add_widget(hdr)

        # Drive selection row
        drive_bar = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(44), spacing=dp(10))
        lbl_drive = Label(text="USB Drive:", bold=True, font_size='12sp', color=COL_TEXT_DIM, size_hint_x=None, width=dp(95), halign='left', valign='middle')
        lbl_drive.bind(size=lambda w, *a: setattr(w, 'text_size', w.size))
        drive_bar.add_widget(lbl_drive)
        usb_spinner = Spinner(
            text=drive_display_names[0], values=drive_display_names,
            background_color=COL_PANEL_ALT, background_normal="", background_down="",
            color=COL_TEXT, font_size='13sp', bold=True,
            padding=(dp(12), dp(10)),
        )
        drive_bar.add_widget(usb_spinner)
        folder_content.add_widget(drive_bar)

        # Folder selection row
        folder_bar = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(44), spacing=dp(10))
        lbl_folder = Label(text="Folder Name:", bold=True, font_size='12sp', color=COL_TEXT_DIM, size_hint_x=None, width=dp(95), halign='left', valign='middle')
        lbl_folder.bind(size=lambda w, *a: setattr(w, 'text_size', w.size))
        folder_bar.add_widget(lbl_folder)
        folder_input = TextInput(
            text="Ductbot_Exports", multiline=False,
            background_color=COL_PANEL_ALT, background_normal="", background_active="",
            foreground_color=COL_TEXT, hint_text_color=COL_TEXT_DIM, cursor_color=COL_BLUE,
            padding=(dp(12), dp(12)), font_size='13sp',
        )
        folder_bar.add_widget(folder_input)
        folder_content.add_widget(folder_bar)

        # Action Buttons
        btn_bar = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(44), spacing=dp(12))
        cancel_select_btn = RoundedButton(
            text="CANCEL", bg_color=COL_PANEL_ALT, fg_color=COL_TEXT, border_color=COL_BORDER,
            size_hint_x=0.45, height=dp(42), font_size=12
        )
        start_btn = RoundedButton(
            text="START EXPORT", icon_cls=UploadIcon, bg_color=COL_GREEN, fg_color=(1, 1, 1, 1),
            size_hint_x=0.55, height=dp(42), font_size=12
        )
        btn_bar.add_widget(cancel_select_btn)
        btn_bar.add_widget(start_btn)
        folder_content.add_widget(btn_bar)

        # Spacer
        folder_content.add_widget(Widget(size_hint_y=None, height=dp(6)))

        def on_start_export(btn):
            folder_popup.dismiss()
            selected_display = usb_spinner.text
            target_drive = drive_map.get(selected_display, selected_display)
            folder_name = folder_input.text.strip()
            if not folder_name:
                folder_name = "Ductbot_Exports"

            export_dir = os.path.join(target_drive, folder_name)
            start_progress_ui(export_dir)

        start_btn.bind(on_press=on_start_export)

        # On-screen keyboard for typing folder name
        keyboard = OnScreenKeyboard(
            get_target_input=lambda: folder_input,
            on_submit=lambda: on_start_export(start_btn),
            size_hint_y=None,
            height=dp(285)
        )
        folder_content.add_widget(keyboard)

        # Automatically focus folder_input
        Clock.schedule_once(lambda dt: setattr(folder_input, 'focus', True), 0.1)

        folder_popup = Popup(
            title='', separator_height=0, content=folder_content,
            size_hint=(0.88, None), height=dp(545),
            pos_hint={'center_x': 0.5, 'center_y': 0.5},
            background='',
            background_color=(0, 0, 0, 0),
            overlay_color=[0.02, 0.03, 0.06, 1.0],
            auto_dismiss=False
        )
        cancel_select_btn.bind(on_press=folder_popup.dismiss)
        close_btn.bind(on_press=folder_popup.dismiss)
        folder_popup.open()

        def start_progress_ui(export_dir):
            progress_content = BoxLayout(orientation='vertical', padding=[dp(20), dp(16)], spacing=dp(12))
            with progress_content.canvas.before:
                Color(0.04, 0.06, 0.10, 1.0)
                progress_content._bg = RoundedRectangle(pos=progress_content.pos, size=progress_content.size, radius=[dp(12)])
                Color(*COL_BORDER)
                progress_content._border = Line(rounded_rectangle=(progress_content.x, progress_content.y, progress_content.width, progress_content.height, dp(12)), width=1.2)
            progress_content.bind(
                pos=lambda inst, v: setattr(inst._bg, 'pos', inst.pos) or setattr(inst._border, 'rounded_rectangle', (inst.x, inst.y, inst.width, inst.height, dp(12))),
                size=lambda inst, v: setattr(inst._bg, 'size', inst.size) or setattr(inst._border, 'rounded_rectangle', (inst.x, inst.y, inst.width, inst.height, dp(12)))
            )

            # Header
            hdr = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(36), spacing=dp(10))
            icon_anchor = AnchorLayout(size_hint_x=None, width=dp(28))
            icon_anchor.add_widget(UploadIcon(color=COL_BLUE, size_dp=20))
            hdr.add_widget(icon_anchor)
            t_lbl = Label(text='EXPORT IN PROGRESS', bold=True, font_size='15sp', color=COL_TEXT, halign='left', valign='middle')
            t_lbl.bind(size=lambda w, *a: setattr(w, 'text_size', w.size))
            hdr.add_widget(t_lbl)
            progress_content.add_widget(hdr)

            self.progress_label = Label(text="Starting export...", font_size='12sp', color=COL_TEXT_DIM, size_hint_y=None, height=dp(28), halign='left', valign='middle')
            self.progress_label.bind(size=lambda w, *a: setattr(w, 'text_size', w.size))
            progress_content.add_widget(self.progress_label)

            self.progress_bar = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(16))
            progress_content.add_widget(self.progress_bar)

            self.cancel_export = False
            def on_cancel(btn):
                self.cancel_export = True
                btn.label.text = "CANCELLING..."
                btn.disabled = True

            cancel_btn = RoundedButton(
                text="CANCEL", size_hint_y=None, height=dp(40),
                bg_color=COL_RED, fg_color=(1, 1, 1, 1), font_size=12
            )
            cancel_btn.bind(on_press=on_cancel)
            progress_content.add_widget(cancel_btn)

            self.progress_popup = Popup(
                title='', separator_height=0, content=progress_content,
                size_hint=(0.52, None), height=dp(195),
                pos_hint={'center_x': 0.5, 'center_y': 0.5},
                background='',
                background_color=(0, 0, 0, 0),
                overlay_color=[0.02, 0.03, 0.06, 1.0],
                auto_dismiss=False
            )
            self.progress_popup.open()
            
            def do_export():
                failed = []
                try:
                    if not os.path.exists(export_dir):
                        os.makedirs(export_dir)

                    total_files = len(selected_files)
                    for i, f in enumerate(selected_files):
                        if self.cancel_export:
                            break

                        basename = os.path.basename(f)
                        Clock.schedule_once(lambda dt, text=f"Exporting {i+1} of {total_files}: {basename}": setattr(self.progress_label, 'text', text), 0)
                        Clock.schedule_once(lambda dt: setattr(self.progress_bar, 'value', 0), 0)

                        # A single missing/unreadable file shouldn't abort
                        # the rest of the batch - record it and move on.
                        dst_mp4 = os.path.join(export_dir, basename)
                        try:
                            # Chunked copy of MP4
                            total_size = os.path.getsize(f)
                            copied = 0
                            with open(f, 'rb') as fsrc, open(dst_mp4, 'wb') as fdst:
                                while True:
                                    if self.cancel_export:
                                        break
                                    buf = fsrc.read(1024 * 1024) # 1MB chunk
                                    if not buf:
                                        break
                                    fdst.write(buf)
                                    copied += len(buf)
                                    if total_size > 0:
                                        pct = (copied / total_size) * 100
                                        Clock.schedule_once(lambda dt, p=pct: setattr(self.progress_bar, 'value', p), 0)

                            if self.cancel_export:
                                try: os.remove(dst_mp4)
                                except Exception: pass
                                break

                            # Copy JSON and CSV sidecars
                            for ext in ('.json', '_frame_times.csv', '_checkpoints.csv', '_match_map.json'):
                                sc_file = f.replace('.mp4', ext)
                                if os.path.exists(sc_file):
                                    shutil.copy2(sc_file, export_dir)
                        except Exception as file_err:
                            failed.append((basename, str(file_err)))
                            try:
                                if os.path.exists(dst_mp4):
                                    os.remove(dst_mp4)
                            except Exception:
                                pass
                            continue

                    if self.cancel_export:
                        Clock.schedule_once(lambda dt: setattr(self.progress_label, 'text', 'Export Cancelled!'), 0)
                    elif failed:
                        names = ", ".join(name for name, _ in failed)
                        msg = f"Done, but {len(failed)} file(s) failed: {names}"
                        Clock.schedule_once(lambda dt, m=msg: setattr(self.progress_label, 'text', m), 0)
                        Clock.schedule_once(lambda dt: setattr(self.progress_bar, 'value', 100), 0)
                    else:
                        Clock.schedule_once(lambda dt: setattr(self.progress_label, 'text', 'Done! Export Successful'), 0)
                        Clock.schedule_once(lambda dt: setattr(self.progress_bar, 'value', 100), 0)

                    Clock.schedule_once(lambda dt: setattr(cancel_btn, 'disabled', True), 0)

                    def close_popups(dt):
                        self.progress_popup.dismiss()

                    Clock.schedule_once(close_popups, 2)
                except Exception as e:
                    # `except ... as e` implicitly deletes `e` once this
                    # block exits, so a Clock-deferred lambda referencing it
                    # directly would raise NameError on the next frame -
                    # capture the message into a plain string first.
                    err_msg = str(e)
                    print(f"Export Error: {err_msg}")
                    Clock.schedule_once(lambda dt, m=err_msg: setattr(self.progress_label, 'text', f'Error: {m}'), 0)
                    Clock.schedule_once(lambda dt: setattr(cancel_btn, 'text', 'Close'), 0)
                    Clock.schedule_once(lambda dt: setattr(cancel_btn, 'disabled', False), 0)
                    cancel_btn.unbind(on_press=on_cancel)
                    cancel_btn.bind(on_press=self.progress_popup.dismiss)

            threading.Thread(target=do_export, daemon=True).start()

class DuctbotApp(App):
    SHOW_STARTUP_ANIMATION = False
    START_FULLSCREEN = False

    def build(self):
        if self.START_FULLSCREEN:
            Window.fullscreen = 'auto'
        else:
            Window.fullscreen = False
            Window.size = (1280, 720)
        self.root = FloatLayout()
        self.main_ui = None

        def build_ui(**kwargs):
            self.main_ui = DuctbotUI(**kwargs)
            return self.main_ui

        if self.SHOW_STARTUP_ANIMATION:
            splash = SplashLoader(build_main_widget=build_ui)
            self.root.add_widget(splash)
        else:
            self.main_ui = build_ui()
            self.root.add_widget(self.main_ui)

        return self.root

    def on_stop(self):
        print("DuctbotApp stopping...")
        if self.main_ui:
            if hasattr(self.main_ui, 'camera_bridge'):
                self.main_ui.camera_bridge.stop()
            if hasattr(self.main_ui, 'esp32_reader'):
                self.main_ui.esp32_reader.stop()
            if hasattr(self.main_ui, 'db_conn'):
                try:
                    self.main_ui.db_conn.close()
                except Exception:
                    pass

if __name__ == '__main__':
    DuctbotApp().run()
