from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from dashboard_ui import (
    RoundedButton,
    StopIcon, RecordRingIcon,
    COL_PANEL, COL_RED, COL_GREEN, COL_TEXT, COL_TEXT_DIM, COL_BORDER,
    _bind_text_size,
)


class BottomControlBar(BoxLayout):
    """Bottom nav: START RECORDING | STOP, as solid pill buttons."""

    def __init__(self, callbacks, **kwargs):
        super().__init__(size_hint_y=None, height=dp(56), spacing=dp(14), **kwargs)
        callbacks = callbacks or {}

        self.btn_play = RoundedButton(
            text="START RECORDING", icon_cls=RecordRingIcon, icon_color=(1, 1, 1, 1),
            bg_color=COL_GREEN, fg_color=(1, 1, 1, 1), radius=28,
        )
        self.btn_play.bind(on_press=callbacks.get("play_pause", lambda x: None))
        self.add_widget(self.btn_play)

        divider = Widget(size_hint_x=None, width=dp(1))
        with divider.canvas:
            Color(*COL_BORDER)
            divider._line = Line(points=[0, 0, 0, 0], width=1)
        def _update_divider(inst, *_a):
            inst._line.points = [inst.center_x, inst.y + inst.height * 0.15,
                                  inst.center_x, inst.top - inst.height * 0.15]
        divider.bind(pos=_update_divider, size=_update_divider)
        self.add_widget(divider)

        self.btn_stop = RoundedButton(
            text="STOP", icon_cls=StopIcon, icon_color=(1, 1, 1, 1),
            bg_color=COL_RED, fg_color=(1, 1, 1, 1), radius=28,
        )
        self.btn_stop.bind(on_press=callbacks.get("stop", lambda x: None))
        self.add_widget(self.btn_stop)

    def set_recording_label(self, text, icon_cls=None):
        self.btn_play.label.text = text


class PlaybackInfoPanel(BoxLayout):
    """Horizontal metadata bar shown below the video while a specific
    recording is being played back."""

    def __init__(self, callbacks, rec_data, **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(48))
        kwargs.setdefault("padding", (dp(16), dp(6)))
        kwargs.setdefault("spacing", dp(18))
        super().__init__(orientation="horizontal", **kwargs)
        callbacks = callbacks or {}

        with self.canvas.before:
            Color(*COL_PANEL)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
            Color(*COL_BORDER)
            self._border = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, dp(8)), width=1.1)
        self.bind(pos=self._update, size=self._update)

        self.btn_stop = RoundedButton(
            text="BACK TO LIST", icon_cls=StopIcon, icon_color=COL_RED,
            bg_color=(0, 0, 0, 0), fg_color=COL_RED, border_color=COL_RED,
            size_hint_x=None, width=dp(150), font_size=12,
        )
        self.btn_stop.bind(on_press=callbacks.get("stop", lambda x: None))
        self.add_widget(self.btn_stop)

        details = [
            ("Client", rec_data.get("client", "")),
            ("Area", rec_data.get("area", "")),
            ("Side", rec_data.get("side", "")),
            ("Cond", rec_data.get("condition", "")),
            ("Cam", rec_data.get("camera", "")),
        ]
        for name, value in details:
            box = BoxLayout(orientation="vertical", size_hint_x=None, width=dp(110))
            name_lbl = Label(
                text=name.upper(), font_size="10sp", bold=True, color=COL_TEXT_DIM,
                size_hint_y=None, height=dp(14), halign="left", valign="bottom",
            )
            _bind_text_size(name_lbl)
            value_lbl = Label(
                text=str(value), font_size="12.5sp", bold=True, color=COL_TEXT,
                size_hint_y=None, height=dp(18), halign="left", valign="top",
            )
            _bind_text_size(value_lbl)
            box.add_widget(name_lbl)
            box.add_widget(value_lbl)
            self.add_widget(box)

        self.add_widget(Widget())

    def _update(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._border.rounded_rectangle = (self.x, self.y, self.width, self.height, dp(8))
