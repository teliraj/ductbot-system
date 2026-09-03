"""
Dashboard UI kit for the 4i Roboserv duct-inspection app: dark theme header,
sidebar status cards, restyled bottom nav, and small canvas-drawn icon
glyphs - built with plain Kivy graphics instructions (no external assets).
"""

import os
import datetime
import math

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line, Mesh, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp, Metrics
Metrics.fontscale = 1.22
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior, ToggleButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.checkbox import CheckBox

# ---------------------------------------------------------------------------
# Palette (matches the 4i Roboserv splash screen)
# ---------------------------------------------------------------------------

COL_BG = (0.024, 0.035, 0.058, 1)
COL_PANEL = (0.055, 0.078, 0.118, 1)
COL_PANEL_ALT = (0.075, 0.10, 0.148, 1)
COL_BORDER = (0.16, 0.22, 0.32, 0.9)
COL_BLUE = (0.29, 0.66, 1.0, 1)
COL_GREEN = (0.30, 0.82, 0.45, 1)
COL_RED = (0.92, 0.28, 0.28, 1)
COL_YELLOW = (0.95, 0.78, 0.25, 1)
COL_TEXT = (0.92, 0.95, 1.0, 1)
COL_TEXT_DIM = (0.55, 0.63, 0.73, 1)


def _bind_text_size(label):
    label.bind(size=lambda w, *_a: setattr(w, "text_size", w.size))


# ---------------------------------------------------------------------------
# Small canvas-drawn icon glyphs (no image assets required)
# ---------------------------------------------------------------------------

class Icon(Widget):
    def __init__(self, color=COL_TEXT, size_dp=16, **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (dp(size_dp), dp(size_dp)))
        super().__init__(**kwargs)
        self.icon_color = color
        self.bind(pos=self._redraw, size=self._redraw)

    def _redraw(self, *a):
        self.canvas.clear()


class PowerIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        cx, cy = x + w / 2, y + h / 2
        r = min(w, h) * 0.36
        with self.canvas:
            Color(*self.icon_color)
            Line(circle=(cx, cy, r, -60, 240), width=dp(1.6))
            Line(points=[cx, cy + r * 1.1, cx, cy - r * 0.1], width=dp(1.6))


class CameraIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        with self.canvas:
            Color(*self.icon_color)
            Line(rounded_rectangle=(x + w * 0.05, y + h * 0.12, w * 0.9, h * 0.62, dp(2)), width=dp(1.4))
            Line(rounded_rectangle=(x + w * 0.35, y + h * 0.68, w * 0.3, h * 0.16, dp(1)), width=dp(1.3))
            Line(circle=(x + w * 0.5, y + h * 0.43, w * 0.16), width=dp(1.4))


class ListIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        with self.canvas:
            Color(*self.icon_color)
            for frac in (0.78, 0.5, 0.22):
                yy = y + h * frac
                Ellipse(pos=(x + w * 0.06, yy - dp(1.6)), size=(dp(3.2), dp(3.2)))
                Line(points=[x + w * 0.24, yy, x + w * 0.94, yy], width=dp(1.6))


class PlayIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        pts = [x + w * 0.28, y + h * 0.18, 0, 0,
               x + w * 0.28, y + h * 0.82, 0, 0,
               x + w * 0.82, y + h * 0.5, 0, 0]
        with self.canvas:
            Color(*self.icon_color)
            Mesh(vertices=pts, indices=[0, 1, 2], mode="triangle_fan")


class RecordRingIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        cx, cy = x + w / 2, y + h / 2
        with self.canvas:
            Color(*self.icon_color)
            Line(circle=(cx, cy, w * 0.42), width=dp(1.8))
            Ellipse(pos=(cx - w * 0.16, cy - w * 0.16), size=(w * 0.32, w * 0.32))


class UploadIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        cx = x + w / 2
        with self.canvas:
            Color(*self.icon_color)
            Line(points=[cx, y + h * 0.32, cx, y + h * 0.85], width=dp(1.6))
            Line(points=[cx - w * 0.18, y + h * 0.58, cx, y + h * 0.85, cx + w * 0.18, y + h * 0.58],
                 width=dp(1.6), joint="round", cap="round")
            Line(points=[x + w * 0.16, y + h * 0.15, x + w * 0.84, y + h * 0.15], width=dp(1.6))


class StopIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        with self.canvas:
            Color(*self.icon_color)
            RoundedRectangle(pos=(x + w * 0.24, y + h * 0.24), size=(w * 0.52, h * 0.52), radius=[dp(2)])


class LaneIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        with self.canvas:
            Color(*self.icon_color)
            Line(points=[x + w * 0.34, y + h * 0.86, x + w * 0.1, y + h * 0.14], width=dp(1.5))
            Line(points=[x + w * 0.66, y + h * 0.86, x + w * 0.9, y + h * 0.14], width=dp(1.5))
            Line(points=[x + w * 0.5, y + h * 0.86, x + w * 0.5, y + h * 0.14],
                 width=dp(1.2), dash_length=dp(2), dash_offset=dp(2))


class FlipIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        cx, cy = x + w / 2, y + h / 2
        r = min(w, h) * 0.32
        with self.canvas:
            Color(*self.icon_color)
            Line(circle=(cx, cy, r, 20, 200), width=dp(1.6))
            Line(circle=(cx, cy, r, 200, 380), width=dp(1.6))


class SwitchCamIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        cx, cy = x + w / 2, y + h / 2
        with self.canvas:
            Color(*self.icon_color)
            # Arrow right (top)
            Line(points=[x + w * 0.2, cy + h * 0.18, x + w * 0.8, cy + h * 0.18], width=dp(1.5), cap="round")
            Line(points=[x + w * 0.58, cy + h * 0.36, x + w * 0.8, cy + h * 0.18, x + w * 0.58, cy], width=dp(1.5), cap="round")
            # Arrow left (bottom)
            Line(points=[x + w * 0.8, cy - h * 0.18, x + w * 0.2, cy - h * 0.18], width=dp(1.5), cap="round")
            Line(points=[x + w * 0.42, cy, x + w * 0.2, cy - h * 0.18, x + w * 0.42, cy - h * 0.36], width=dp(1.5), cap="round")



class PersonIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        cx = x + w / 2
        with self.canvas:
            Color(*self.icon_color)
            r = w * 0.17
            Ellipse(pos=(cx - r, y + h * 0.68 - r), size=(r * 2, r * 2))
            br = w * 0.36
            Ellipse(pos=(cx - br, y - br * 0.55), size=(br * 2, br * 2))


class MapIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        pts = [
            x + w * 0.08, y + h * 0.15, x + w * 0.36, y + h * 0.28, x + w * 0.64, y + h * 0.15,
            x + w * 0.92, y + h * 0.28, x + w * 0.92, y + h * 0.85, x + w * 0.64, y + h * 0.72,
            x + w * 0.36, y + h * 0.85, x + w * 0.08, y + h * 0.72, x + w * 0.08, y + h * 0.15,
        ]
        with self.canvas:
            Color(*self.icon_color)
            Line(points=pts, width=dp(1.4), joint="round")
            Line(points=[x + w * 0.36, y + h * 0.28, x + w * 0.36, y + h * 0.85], width=dp(1.1))
            Line(points=[x + w * 0.64, y + h * 0.15, x + w * 0.64, y + h * 0.72], width=dp(1.1))


class GridIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        s = w * 0.36
        gap = w * 0.10
        cx, cy = x + w / 2, y + h / 2
        with self.canvas:
            Color(*self.icon_color)
            RoundedRectangle(pos=(cx - s - gap / 2, cy + gap / 2), size=(s, s), radius=[dp(1.5)])
            RoundedRectangle(pos=(cx + gap / 2, cy + gap / 2), size=(s, s), radius=[dp(1.5)])
            RoundedRectangle(pos=(cx - s - gap / 2, cy - gap / 2 - s), size=(s, s), radius=[dp(1.5)])
            RoundedRectangle(pos=(cx + gap / 2, cy - gap / 2 - s), size=(s, s), radius=[dp(1.5)])


class SunIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        cx, cy = x + w / 2, y + h / 2
        r = min(w, h) * 0.20
        with self.canvas:
            Color(*self.icon_color)
            Ellipse(pos=(cx - r, cy - r), size=(r * 2, r * 2))
            for i in range(8):
                ang = math.radians(i * 45)
                x0 = cx + math.cos(ang) * r * 1.5
                y0 = cy + math.sin(ang) * r * 1.5
                x1 = cx + math.cos(ang) * r * 2.15
                y1 = cy + math.sin(ang) * r * 2.15
                Line(points=[x0, y0, x1, y1], width=dp(1.3))


class TempIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        cx = x + w / 2
        with self.canvas:
            Color(*self.icon_color)
            Line(circle=(cx, y + h * 0.28, w * 0.22), width=dp(1.4))
            Line(points=[cx - w * 0.1, y + h * 0.44, cx - w * 0.1, y + h * 0.82], width=dp(1.3))
            Line(points=[cx + w * 0.1, y + h * 0.44, cx + w * 0.1, y + h * 0.82], width=dp(1.3))
            Line(circle=(cx, y + h * 0.82, w * 0.1, 0, 180), width=dp(1.3))
            Ellipse(pos=(cx - w * 0.12, y + h * 0.18), size=(w * 0.24, w * 0.24))


class DropIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        cx, cy = x + w / 2, y + h / 2
        with self.canvas:
            Color(*self.icon_color)
            Line(circle=(cx, y + h * 0.35, w * 0.30, -90, 90), width=dp(1.4))
            Line(points=[cx - w * 0.30, y + h * 0.35, cx, y + h * 0.85, cx + w * 0.30, y + h * 0.35], width=dp(1.4), joint="round")


class GasIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        cx, cy = x + w / 2, y + h / 2
        with self.canvas:
            Color(*self.icon_color)
            Line(points=[x + w * 0.2, y + h * 0.7, cx, y + h * 0.8, x + w * 0.8, y + h * 0.7], width=dp(1.4), joint="round")
            Line(points=[x + w * 0.15, cy, cx, y + h * 0.6, x + w * 0.85, cy], width=dp(1.4), joint="round")
            Line(points=[x + w * 0.25, y + h * 0.3, cx, y + h * 0.4, x + w * 0.75, y + h * 0.3], width=dp(1.4), joint="round")


class AngleIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        cx, cy = x + w / 2, y + h / 2
        with self.canvas:
            Color(*self.icon_color)
            Line(circle=(cx, cy, w * 0.4), width=dp(1.4))
            Line(points=[x + w * 0.15, cy, x + w * 0.85, cy], width=dp(1.2), dash_length=dp(2), dash_offset=dp(2))
            Line(points=[cx, y + h * 0.15, cx, y + h * 0.85], width=dp(1.2), dash_length=dp(2), dash_offset=dp(2))
            Line(points=[x + w * 0.25, y + h * 0.35, x + w * 0.75, y + h * 0.65], width=dp(1.6))


class SpeedIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        cx, cy = x + w / 2, y + h / 2
        with self.canvas:
            Color(*self.icon_color)
            Line(circle=(cx, cy - h * 0.1, w * 0.38, -65, 65), width=dp(1.4))
            Line(points=[cx, cy - h * 0.1, cx + w * 0.22, cy + h * 0.22], width=dp(1.6), cap="round")
            Ellipse(pos=(cx - dp(2.5), cy - h * 0.1 - dp(2.5)), size=(dp(5), dp(5)))




class SendIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        pts = [
            x + w * 0.08, y + h * 0.9, 0, 0,
            x + w * 0.92, y + h * 0.5, 0, 0,
            x + w * 0.08, y + h * 0.1, 0, 0,
            x + w * 0.38, y + h * 0.5, 0, 0,
        ]
        with self.canvas:
            Color(*self.icon_color)
            Mesh(vertices=pts, indices=[0, 1, 2, 3], mode="triangle_fan")


class CloseIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        with self.canvas:
            Color(*self.icon_color)
            Line(points=[x + w * 0.22, y + h * 0.22, x + w * 0.78, y + h * 0.78], width=dp(1.8), cap="round")
            Line(points=[x + w * 0.22, y + h * 0.78, x + w * 0.78, y + h * 0.22], width=dp(1.8), cap="round")


class VideoIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        pts = [
            x + w * 0.62, y + h * 0.36, 0, 0,
            x + w * 0.94, y + h * 0.20, 0, 0,
            x + w * 0.94, y + h * 0.80, 0, 0,
            x + w * 0.62, y + h * 0.64, 0, 0,
        ]
        with self.canvas:
            Color(*self.icon_color)
            RoundedRectangle(pos=(x + w * 0.06, y + h * 0.26), size=(w * 0.56, h * 0.48), radius=[dp(2)])
            Mesh(vertices=pts, indices=[0, 1, 2, 3], mode="triangle_fan")


class CompareIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        cx, cy = x + w / 2, y + h / 2
        with self.canvas:
            Color(*self.icon_color)
            # Left frame
            Line(rounded_rectangle=(x + w * 0.06, y + h * 0.16, w * 0.40, h * 0.68, dp(2)), width=dp(1.4))
            # Right frame
            Line(rounded_rectangle=(x + w * 0.54, y + h * 0.16, w * 0.40, h * 0.68, dp(2)), width=dp(1.4))
            # Center connector
            Line(points=[x + w * 0.38, cy, x + w * 0.62, cy], width=dp(1.4))
            Ellipse(pos=(cx - dp(2), cy - dp(2)), size=(dp(4), dp(4)))


class ExpandIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        with self.canvas:
            Color(*self.icon_color)
            Line(points=[x + w * 0.08, y + h * 0.32, x + w * 0.08, y + h * 0.08, x + w * 0.32, y + h * 0.08],
                 width=dp(1.6), joint="round", cap="round")
            Line(points=[x + w * 0.68, y + h * 0.92, x + w * 0.92, y + h * 0.92, x + w * 0.92, y + h * 0.68],
                 width=dp(1.6), joint="round", cap="round")


class CollapseIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        with self.canvas:
            Color(*self.icon_color)
            Line(points=[x + w * 0.30, y + h * 0.10, x + w * 0.30, y + h * 0.30, x + w * 0.10, y + h * 0.30],
                 width=dp(1.6), joint="round", cap="round")
            Line(points=[x + w * 0.70, y + h * 0.90, x + w * 0.70, y + h * 0.70, x + w * 0.90, y + h * 0.70],
                 width=dp(1.6), joint="round", cap="round")


class HomeIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        pts = [
            x + w * 0.5, y + h * 0.92, x + w * 0.08, y + h * 0.52, x + w * 0.22, y + h * 0.52,
            x + w * 0.22, y + h * 0.1, x + w * 0.78, y + h * 0.1, x + w * 0.78, y + h * 0.52,
            x + w * 0.92, y + h * 0.52, x + w * 0.5, y + h * 0.92,
        ]
        with self.canvas:
            Color(*self.icon_color)
            Line(points=pts, width=dp(1.5), joint="round", cap="round")


class MenuIcon(Icon):
    def _redraw(self, *a):
        super()._redraw()
        x, y = self.pos
        w, h = self.size
        with self.canvas:
            Color(*self.icon_color)
            for frac in (0.78, 0.5, 0.22):
                yy = y + h * frac
                Line(points=[x + w * 0.1, yy, x + w * 0.9, yy], width=dp(1.6), cap="round")


class Dot(Widget):
    def __init__(self, color=COL_GREEN, size_dp=8, **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (dp(size_dp), dp(size_dp)))
        super().__init__(**kwargs)
        with self.canvas:
            self._col = Color(*color)
            self._ell = Ellipse(pos=self.pos, size=self.size)
        self.bind(pos=self._update, size=self._update)

    def _update(self, *a):
        self._ell.pos = self.pos
        self._ell.size = self.size

    def set_color(self, color):
        self._col.rgba = color


# ---------------------------------------------------------------------------
# Rounded button (icon + label, press feedback)
# ---------------------------------------------------------------------------

class RoundedButton(ButtonBehavior, BoxLayout):
    def __init__(self, text="", icon_cls=None, icon_color=None,
                 bg_color=COL_PANEL_ALT, fg_color=COL_TEXT, border_color=None,
                 radius=10, font_size=13, bold=True, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        is_icon_only = not bool(text) and icon_cls is not None
        if is_icon_only:
            kwargs.setdefault("spacing", 0)
            kwargs.setdefault("padding", (0, 0))
        else:
            kwargs.setdefault("spacing", dp(8))
            kwargs.setdefault("padding", (dp(14), 0))
        super().__init__(**kwargs)
        self.bg_color = bg_color
        self._pressed_color = tuple(min(1.0, c * 1.3) if i < 3 else c for i, c in enumerate(bg_color))
        self.border_color = border_color
        self.radius = dp(radius)
        with self.canvas.before:
            self._bgcol = Color(*bg_color)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[self.radius])
            if border_color:
                self._bcol = Color(*border_color)
                self._border = Line(
                    rounded_rectangle=(self.x, self.y, self.width, self.height, self.radius), width=1.1
                )
        self.bind(pos=self._update, size=self._update)

        self._icon_anchor = None
        self._icon_color = icon_color or fg_color
        if icon_cls:
            if is_icon_only:
                self._icon_anchor = AnchorLayout(size_hint=(1, 1), anchor_x="center", anchor_y="center")
                self._icon_anchor.add_widget(icon_cls(color=self._icon_color, size_dp=16))
                self.add_widget(self._icon_anchor)
            else:
                self._icon_anchor = AnchorLayout(size_hint_x=None, width=dp(18), anchor_x="center", anchor_y="center")
                self._icon_anchor.add_widget(icon_cls(color=self._icon_color, size_dp=16))
                self.add_widget(self._icon_anchor)

        if text:
            self.label = Label(text=text, color=fg_color, bold=bold, font_size=sp(font_size))
            self.add_widget(self.label)
        else:
            self.label = Label(text="", size_hint=(None, None), size=(0, 0), opacity=0)

    def _update(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size
        if self.border_color:
            self._border.rounded_rectangle = (self.x, self.y, self.width, self.height, self.radius)

    def set_icon(self, icon_cls, color=None):
        if not self._icon_anchor:
            return
        self._icon_anchor.clear_widgets()
        self._icon_anchor.add_widget(icon_cls(color=color or self._icon_color, size_dp=16))

    def set_bg(self, color):
        self.bg_color = color
        self._pressed_color = tuple(min(1.0, c * 1.3) if i < 3 else c for i, c in enumerate(color))
        self._bgcol.rgba = color

    def on_press(self):
        self._bgcol.rgba = self._pressed_color

    def on_release(self):
        self._bgcol.rgba = self.bg_color


# ---------------------------------------------------------------------------
# Form field (icon + text input, dark bordered box) and segment toggle
# ---------------------------------------------------------------------------

class FormField(BoxLayout):
    def __init__(self, icon_cls, hint_text, **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(52))
        kwargs.setdefault("spacing", dp(12))
        kwargs.setdefault("padding", (dp(14), 0))
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*COL_PANEL_ALT)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10)])
            Color(*COL_BORDER)
            self._border = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, dp(10)), width=1.1)
        self.bind(pos=self._update, size=self._update)

        icon_anchor = AnchorLayout(size_hint_x=None, width=dp(22))
        icon_anchor.add_widget(icon_cls(color=COL_BLUE, size_dp=18))
        self.add_widget(icon_anchor)

        self.input = TextInput(
            hint_text=hint_text, multiline=False,
            background_color=(0, 0, 0, 0), background_normal="", background_active="",
            foreground_color=COL_TEXT, hint_text_color=COL_TEXT_DIM, cursor_color=COL_BLUE,
            padding=(0, dp(15)), font_size=sp(14),
        )
        self.add_widget(self.input)

    def _update(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._border.rounded_rectangle = (self.x, self.y, self.width, self.height, dp(10))

    @property
    def text(self):
        return self.input.text

    @text.setter
    def text(self, value):
        self.input.text = value


class SegmentButton(ToggleButtonBehavior, BoxLayout):
    """A toggle-able segment (icon + label) for exclusive-choice rows like
    Condition (Before/After) or Camera (Front/Rear)."""

    def __init__(self, text="", icon_cls=None, group=None, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("spacing", dp(8))
        kwargs.setdefault("padding", (dp(14), 0))
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(52))
        super().__init__(**kwargs)
        if group:
            self.group = group

        with self.canvas.before:
            self._bgcol = Color(*COL_PANEL_ALT)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10)])
            self._bcol = Color(*COL_BORDER)
            self._border = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, dp(10)), width=1.2)
        self.bind(pos=self._update, size=self._update, state=self._update_state)

        self._icon = None
        if icon_cls:
            self._icon = icon_cls(color=COL_TEXT_DIM, size_dp=18)
            icon_anchor = AnchorLayout(size_hint_x=None, width=dp(22))
            icon_anchor.add_widget(self._icon)
            self.add_widget(icon_anchor)

        self.label = Label(text=text, color=COL_TEXT_DIM, bold=True, font_size=sp(14))
        self.add_widget(self.label)

    def _update(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._border.rounded_rectangle = (self.x, self.y, self.width, self.height, dp(10))

    def _update_state(self, *a):
        active = self.state == "down"
        self._bgcol.rgba = (0.10, 0.20, 0.42, 1) if active else COL_PANEL_ALT
        self._bcol.rgba = COL_BLUE if active else COL_BORDER
        self.label.color = COL_TEXT if active else COL_TEXT_DIM
        if self._icon:
            self._icon.icon_color = COL_BLUE if active else COL_TEXT_DIM
            self._icon._redraw()


# ---------------------------------------------------------------------------
# Left navigation sidebar
# ---------------------------------------------------------------------------

class NavButton(ButtonBehavior, BoxLayout):
    def __init__(self, text, icon_cls, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(44))
        kwargs.setdefault("spacing", dp(8))
        kwargs.setdefault("padding", (dp(10), 0))
        super().__init__(**kwargs)
        with self.canvas.before:
            self._bgcol = Color(0, 0, 0, 0)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
        self.bind(pos=self._update, size=self._update)

        self._icon_anchor = AnchorLayout(size_hint=(None, 1), width=dp(20), anchor_x="center", anchor_y="center")
        self._icon = icon_cls(color=COL_TEXT_DIM, size_dp=18)
        self._icon_anchor.add_widget(self._icon)
        self.add_widget(self._icon_anchor)

        self.label = Label(
            text=text, color=COL_TEXT_DIM, bold=True, font_size=sp(13), halign="left", valign="middle",
            shorten=False, max_lines=1
        )
        _bind_text_size(self.label)
        self.add_widget(self.label)

    def _update(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def set_collapsed(self, collapsed):
        if collapsed:
            self.padding = (0, 0)
            self.spacing = 0
            self._icon_anchor.size_hint = (1, 1)
            self._icon_anchor.anchor_x = "center"
            self._icon_anchor.anchor_y = "center"
            self.label.opacity = 0
            self.label.size_hint = (None, None)
            self.label.size = (0, 0)
        else:
            self.padding = (dp(10), 0)
            self.spacing = dp(8)
            self._icon_anchor.size_hint = (None, 1)
            self._icon_anchor.width = dp(20)
            self._icon_anchor.anchor_x = "center"
            self._icon_anchor.anchor_y = "center"
            self.label.opacity = 1
            self.label.size_hint = (1, 1)

    def set_active(self, active):
        self._bgcol.rgba = COL_BLUE if active else (0, 0, 0, 0)
        self.label.color = (1, 1, 1, 1) if active else COL_TEXT_DIM
        self._icon.icon_color = (1, 1, 1, 1) if active else COL_TEXT_DIM
        self._icon._redraw()


class NavSidebar(BoxLayout):
    EXPANDED_WIDTH = dp(180)
    COLLAPSED_WIDTH = dp(64)

    def __init__(self, on_nav, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("size_hint_x", None)
        kwargs.setdefault("width", self.EXPANDED_WIDTH)
        kwargs.setdefault("padding", (dp(12), dp(18), dp(12), dp(14)))
        kwargs.setdefault("spacing", dp(6))
        super().__init__(**kwargs)
        self.expanded = True
        with self.canvas.before:
            Color(*COL_PANEL)
            self._bg = Rectangle(pos=self.pos, size=self.size)
            Color(*COL_BORDER)
            self._bline = Line(points=[self.right, self.y, self.right, self.top], width=1)
        self.bind(pos=self._update, size=self._update)

        logo_box = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(46))
        self.logo_label = Label(
            text="4i", bold=True, font_size=sp(24), color=COL_BLUE,
            size_hint_y=None, height=dp(28), halign="left", valign="bottom",
        )
        _bind_text_size(self.logo_label)
        self.logo_sub = Label(
            text="ROBOSERV", bold=True, font_size=sp(9.5), color=COL_TEXT,
            size_hint_y=None, height=dp(14), halign="left", valign="top",
        )
        _bind_text_size(self.logo_sub)
        logo_box.add_widget(self.logo_label)
        logo_box.add_widget(self.logo_sub)
        self.add_widget(logo_box)
        self.logo_sub_ref = self.logo_sub

        top_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(30))
        self.toggle_btn = RoundedButton(
            text="", icon_cls=MenuIcon, icon_color=COL_TEXT_DIM,
            bg_color=(0, 0, 0, 0), size_hint=(None, None), size=(dp(30), dp(30)),
        )
        self.toggle_btn.bind(on_press=lambda x: self.toggle())
        top_row.add_widget(self.toggle_btn)
        self.add_widget(top_row)

        self.add_widget(Widget(size_hint_y=None, height=dp(14)))

        self.btn_nav_live = NavButton("Live", HomeIcon)
        self.btn_nav_live.bind(on_press=lambda x: on_nav("live"))
        self.add_widget(self.btn_nav_live)

        self.btn_nav_playback = NavButton("Playback", ListIcon)
        self.btn_nav_playback.bind(on_press=lambda x: on_nav("playback"))
        self.add_widget(self.btn_nav_playback)

        self.btn_nav_comparison = NavButton("Comparison", CompareIcon)
        self.btn_nav_comparison.bind(on_press=lambda x: on_nav("comparison"))
        self.add_widget(self.btn_nav_comparison)

        self.add_widget(Widget())
        self.set_active("live")

    def toggle(self):
        self.expanded = not self.expanded
        target = self.EXPANDED_WIDTH if self.expanded else self.COLLAPSED_WIDTH
        Animation.cancel_all(self, "width")
        Animation(width=target, d=0.22, t="out_quad").start(self)
        self.logo_sub_ref.opacity = 1 if self.expanded else 0
        self.btn_nav_live.set_collapsed(not self.expanded)
        self.btn_nav_playback.set_collapsed(not self.expanded)
        self.btn_nav_comparison.set_collapsed(not self.expanded)

    def _update(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._bline.points = [self.right, self.y, self.right, self.top]

    def set_active(self, mode):
        self.btn_nav_live.set_active(mode == "live")
        self.btn_nav_playback.set_active(mode == "playback")
        self.btn_nav_comparison.set_active(mode == "comparison")


# ---------------------------------------------------------------------------
# Header bar
# ---------------------------------------------------------------------------

class HeaderBar(BoxLayout):
    def __init__(self, on_shutdown=None, **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(74))
        kwargs.setdefault("padding", (dp(20), dp(10)))
        kwargs.setdefault("spacing", dp(18))
        super().__init__(orientation="horizontal", **kwargs)
        with self.canvas.before:
            Color(*COL_PANEL)
            self._bg = Rectangle(pos=self.pos, size=self.size)
            Color(*COL_BORDER)
            self._bline = Line(points=[self.x, self.y, self.x + self.width, self.y], width=1)
        self.bind(pos=self._update, size=self._update)

        self.live_badge = Badge(COL_RED, "LIVE")
        self.add_widget(self.live_badge)

        self.add_widget(Widget())

        dt_box = BoxLayout(orientation="vertical", size_hint_x=None, width=dp(130))
        self.time_label = Label(
            text="", bold=True, font_size=sp(15), color=COL_TEXT, halign="right", valign="bottom",
        )
        _bind_text_size(self.time_label)
        self.date_label = Label(
            text="", font_size=sp(11), color=COL_TEXT_DIM, halign="right", valign="top",
        )
        _bind_text_size(self.date_label)
        dt_box.add_widget(self.time_label)
        dt_box.add_widget(self.date_label)
        self.add_widget(dt_box)

        self.btn_shutdown = RoundedButton(
            text="SHUTDOWN", icon_cls=PowerIcon, icon_color=COL_RED,
            bg_color=(0, 0, 0, 0), fg_color=COL_RED, border_color=COL_RED,
            size_hint=(None, None), size=(dp(134), dp(38)), font_size=12,
        )
        if on_shutdown:
            self.btn_shutdown.bind(on_press=on_shutdown)
        shutdown_anchor = AnchorLayout(size_hint_x=None, width=dp(134))
        shutdown_anchor.add_widget(self.btn_shutdown)
        self.add_widget(shutdown_anchor)

        Clock.schedule_interval(self._tick_clock, 1.0)
        self._tick_clock(0)

    def _update(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._bline.points = [self.x, self.y, self.x + self.width, self.y]

    def _tick_clock(self, dt):
        now = datetime.datetime.now()
        self.time_label.text = now.strftime("%I:%M:%S %p")
        self.date_label.text = now.strftime("%B %d, %Y")

    def set_live_mode(self, visible):
        self.live_badge.opacity = 1 if visible else 0


# ---------------------------------------------------------------------------
# Video overlay: REC / LIVE badges + TOF corner readouts, as native widgets
# layered on top of the camera Image instead of being baked into the frame.
# ---------------------------------------------------------------------------

class Badge(BoxLayout):
    def __init__(self, dot_color, text, icon_cls=None, **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("height", dp(32))
        kwargs.setdefault("spacing", dp(6))
        kwargs.setdefault("padding", (dp(10), dp(5)))
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(0.02, 0.03, 0.05, 0.72)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(6)])
        self.bind(pos=self._update, size=self._update)
        dot_anchor = AnchorLayout(size_hint_x=None, width=dp(16) if icon_cls else dp(12))
        self.dot = icon_cls(color=dot_color, size_dp=14) if icon_cls else Dot(color=dot_color, size_dp=8)
        dot_anchor.add_widget(self.dot)
        self.add_widget(dot_anchor)
        self.label = Label(text=text, bold=True, font_size=sp(12), color=COL_TEXT, size_hint_x=None)
        self.label.bind(texture_size=lambda w, ts: setattr(w, "width", ts[0]))
        self.add_widget(self.label)
        self.bind(minimum_width=self.setter("width"))

    def _update(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size


class TelemetryPill(BoxLayout):
    def __init__(self, icon_cls, title, value="--", icon_color=COL_BLUE, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("height", dp(32))
        kwargs.setdefault("spacing", dp(6))
        kwargs.setdefault("padding", (dp(10), dp(4)))
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(0.03, 0.05, 0.09, 0.85)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(6)])
            Color(*COL_BORDER)
            self._border = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, dp(6)), width=1.0)
        self.bind(pos=self._update, size=self._update)

        self.icon_anchor = AnchorLayout(size_hint_x=None, width=dp(16))
        self.icon = icon_cls(color=icon_color, size_dp=14)
        self.icon_anchor.add_widget(self.icon)
        self.add_widget(self.icon_anchor)

        self.lbl_title = Label(text=title, font_size=sp(11), color=COL_TEXT_DIM, bold=True, size_hint_x=None)
        self.lbl_title.bind(texture_size=lambda w, ts: setattr(w, "width", ts[0]))
        self.add_widget(self.lbl_title)

        self.lbl_val = Label(text=value, font_size=sp(12.5), color=COL_TEXT, bold=True, size_hint_x=None)
        self.lbl_val.bind(texture_size=lambda w, ts: setattr(w, "width", ts[0]))
        self.add_widget(self.lbl_val)
        self.bind(minimum_width=self.setter("width"))

    def _update(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._border.rounded_rectangle = (self.x, self.y, self.width, self.height, dp(6))

    def set_value(self, val_str, color=None):
        self.lbl_val.text = str(val_str)
        if color:
            self.lbl_val.color = color


class SensorTelemetryHUD(BoxLayout):
    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("height", dp(34))
        kwargs.setdefault("spacing", dp(8))
        super().__init__(**kwargs)
        self.pill_speed = TelemetryPill(SpeedIcon, "SPD", "0.00 m/s", icon_color=COL_BLUE)
        self.pill_temp = TelemetryPill(TempIcon, "TEMP", "--°C", icon_color=COL_YELLOW)
        self.pill_hum = TelemetryPill(DropIcon, "HUM", "--%", icon_color=COL_BLUE)
        self.pill_air = TelemetryPill(GasIcon, "AIR", "-- AQI", icon_color=COL_GREEN)
        self.pill_tilt = TelemetryPill(AngleIcon, "TILT", "P:0° R:0°", icon_color=COL_BLUE)
        self.pill_tof = TelemetryPill(LaneIcon, "TOF", "L:-- R:--", icon_color=COL_YELLOW)

        self.add_widget(self.pill_speed)
        self.add_widget(self.pill_temp)
        self.add_widget(self.pill_hum)
        self.add_widget(self.pill_air)
        self.add_widget(self.pill_tilt)
        self.add_widget(self.pill_tof)
        self.bind(minimum_width=self.setter("width"))

    def update_data(self, data: dict):
        if not data or not data.get("connected", False):
            self.pill_speed.set_value("-- m/s", color=COL_TEXT_DIM)
            self.pill_temp.set_value("--°C", color=COL_TEXT_DIM)
            self.pill_hum.set_value("--%", color=COL_TEXT_DIM)
            self.pill_air.set_value("OFFLINE", color=COL_RED)
            self.pill_tilt.set_value("P:-- R:--", color=COL_TEXT_DIM)
            self.pill_tof.set_value("L:-- R:--", color=COL_TEXT_DIM)
            return

        # Speed & Odometry
        spd = float(data.get("speed_mps", 0.0))
        dist = float(data.get("total_distance_m", 0.0))
        if abs(spd) < 0.01:
            self.pill_speed.set_value(f"0.00 m/s ({dist:.1f}m)", color=COL_TEXT)
        else:
            self.pill_speed.set_value(f"{spd:.2f} m/s ({dist:.1f}m)", color=COL_GREEN)

        # Temperature
        temp = data.get("temperature", 0.0)
        t_col = COL_RED if temp > 50 else (COL_YELLOW if temp > 35 else COL_TEXT)
        self.pill_temp.set_value(f"{temp:.1f}°C", color=t_col)

        # Humidity
        hum = data.get("humidity", 0.0)
        self.pill_hum.set_value(f"{hum:.1f}%", color=COL_TEXT)

        # Air Quality / Gas
        aqi = int(data.get("air_quality", 0))
        ppm = int(data.get("gas_ppm", 0))
        aqi_col = COL_RED if aqi > 100 else (COL_YELLOW if aqi > 60 else COL_GREEN)
        self.pill_air.set_value(f"{aqi} AQI ({ppm} ppm)", color=aqi_col)

        # Tilt (Pitch and Roll)
        pitch = data.get("pitch", 0.0)
        roll = data.get("roll", 0.0)
        self.pill_tilt.set_value(f"P:{pitch:+.1f}° R:{roll:+.1f}°", color=COL_TEXT)

        # TOF Left / Right
        try:
            tl = float(data.get("TOF_L", 0))
            tof_l_str = f"{int(tl)}" if math.isfinite(tl) and tl < 9999 else ">MAX"
        except (ValueError, TypeError):
            tof_l_str = ">MAX"
        try:
            tr = float(data.get("TOF_R", 0))
            tof_r_str = f"{int(tr)}" if math.isfinite(tr) and tr < 9999 else ">MAX"
        except (ValueError, TypeError):
            tof_r_str = ">MAX"
        self.pill_tof.set_value(f"L:{tof_l_str} R:{tof_r_str} mm", color=COL_TEXT)


class TrajectoryCanvas(Widget):
    """Drawing canvas for the 2D trajectory trail, current robot pose and heading."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.path_points = []
        self.current_x = 0.0
        self.current_y = 0.0
        self.current_yaw = 0.0
        self.tof_l = 100.0
        self.tof_r = 100.0
        self.bind(pos=self._redraw, size=self._redraw)

    def update_pose(self, x, y, yaw, path=None, tof_l=None, tof_r=None):
        self.current_x = x
        self.current_y = y
        self.current_yaw = yaw
        if path is not None and len(path) > 0:
            self.path_points = path
        else:
            # Accumulate locally if not provided
            if not self.path_points or math.hypot(x - self.path_points[-1][0], y - self.path_points[-1][1]) > 0.02:
                self.path_points.append((x, y))
        if tof_l is not None: self.tof_l = tof_l
        if tof_r is not None: self.tof_r = tof_r
        self._redraw()

    def reset_path(self):
        self.path_points = []
        self.current_x = 0.0
        self.current_y = 0.0
        self.current_yaw = 0.0
        self._redraw()

    def _redraw(self, *args):
        self.canvas.clear()
        x, y = self.pos
        w, h = self.size
        cx, cy = x + w / 2, y + h / 2

        with self.canvas:
            # Dark background
            Color(0.04, 0.06, 0.09, 0.90)
            RoundedRectangle(pos=(x, y), size=(w, h), radius=[dp(6)])
            Color(*COL_BORDER)
            Line(rounded_rectangle=(x, y, w, h, dp(6)), width=1.0)

            # Subtle grid lines
            Color(0.14, 0.18, 0.26, 0.6)
            Line(points=[x + dp(6), cy, x + w - dp(6), cy], width=1.0)
            Line(points=[cx, y + dp(6), cx, y + h - dp(6)], width=1.0)

            # Coordinate scaling: standard duct view (~30 pixels per meter)
            scale = 35.0

            def to_screen(wx, wy):
                sx = cx - wy * scale
                sy = cy + wx * scale
                return sx, sy

            # Draw 2D Path Trail
            if len(self.path_points) > 1:
                Color(*COL_BLUE)
                pts = []
                for px, py in self.path_points:
                    sx, sy = to_screen(px, py)
                    pts.extend([sx, sy])
                if len(pts) >= 4:
                    Line(points=pts, width=dp(1.8), joint="round", cap="round")

            # Draw Current Robot Pose & Heading Arrow
            rx, ry = to_screen(self.current_x, self.current_y)
            Color(*COL_GREEN)
            Ellipse(pos=(rx - dp(4.5), ry - dp(4.5)), size=(dp(9), dp(9)))

            yaw_rad = math.radians(self.current_yaw)
            arrow_len = dp(15)
            tip_x = rx - math.sin(yaw_rad) * arrow_len
            tip_y = ry + math.cos(yaw_rad) * arrow_len
            Line(points=[rx, ry, tip_x, tip_y], width=dp(2.0), cap="round")


class TrajectoryMapWidget(BoxLayout):
    """Floating 2D Trajectory Map HUD displaying live path and pose coordinates."""
    def __init__(self, on_reset=None, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (dp(230), dp(220)))
        kwargs.setdefault("padding", dp(8))
        kwargs.setdefault("spacing", dp(4))
        super().__init__(**kwargs)
        self.on_reset = on_reset

        with self.canvas.before:
            Color(0.03, 0.045, 0.07, 0.90)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
            Color(*COL_BORDER)
            self._border = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, dp(8)), width=1.1)
        self.bind(pos=self._update, size=self._update)

        # Header: Title + Reset Button
        hdr = BoxLayout(size_hint_y=None, height=dp(26), spacing=dp(6))
        hdr.add_widget(MapIcon(color=COL_BLUE, size_dp=16))
        self.lbl_title = Label(
            text="TRAJECTORY MAP", bold=True, font_size="10.5sp", color=COL_TEXT,
            halign="left", valign="middle"
        )
        _bind_text_size(self.lbl_title)
        hdr.add_widget(self.lbl_title)

        self.btn_reset = RoundedButton(
            text="ZERO", bg_color=(0.16, 0.22, 0.32, 1), fg_color=COL_TEXT,
            font_size=10, size_hint=(None, None), size=(dp(48), dp(22)), radius=4
        )
        if on_reset:
            self.btn_reset.bind(on_press=lambda x: on_reset())
        hdr.add_widget(self.btn_reset)
        self.add_widget(hdr)

        # Trajectory Canvas
        self.tcanvas = TrajectoryCanvas()
        self.add_widget(self.tcanvas)

        # Coordinate readout
        self.lbl_coords = Label(
            text="X: +0.00m  Y: +0.00m  θ: +0.0°", font_size="10sp", color=COL_TEXT_DIM,
            size_hint_y=None, height=dp(18), halign="center", valign="middle"
        )
        _bind_text_size(self.lbl_coords)
        self.add_widget(self.lbl_coords)

    def _update(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._border.rounded_rectangle = (self.x, self.y, self.width, self.height, dp(8))

    def update_pose(self, x, y, yaw, path=None, tof_l=None, tof_r=None):
        self.tcanvas.update_pose(x, y, yaw, path=path, tof_l=tof_l, tof_r=tof_r)
        self.lbl_coords.text = f"X: {x:+.2f}m  Y: {y:+.2f}m  θ: {yaw:+.1f}°"

    def reset_odometry(self):
        self.tcanvas.reset_path()
        self.lbl_coords.text = "X: +0.00m  Y: +0.00m  θ: +0.0°"


class VideoComparisonPopup(Popup):
    """
    Modal popup for running DTW Before / After Video Comparison.
    Displays run details, live progress bar, and completion status.
    """
    def __init__(self, before_rec, after_rec, on_start_comparison, on_play_result=None, **kwargs):
        kwargs.setdefault("title", "Before / After DTW Video Comparison")
        kwargs.setdefault("size_hint", (0.65, 0.55))
        kwargs.setdefault("auto_dismiss", False)
        kwargs.setdefault("background", "")
        kwargs.setdefault("background_color", (0, 0, 0, 0))
        kwargs.setdefault("overlay_color", [0.02, 0.03, 0.06, 1.0])
        kwargs.setdefault("title_color", COL_TEXT)
        kwargs.setdefault("separator_color", COL_BORDER)
        super().__init__(**kwargs)

        self.before_rec = before_rec
        self.after_rec = after_rec
        self.on_start_comparison = on_start_comparison
        self.on_play_result = on_play_result
        self.result_filename = None

        content = BoxLayout(orientation="vertical", spacing=dp(14), padding=dp(16))
        with content.canvas.before:
            Color(0.04, 0.06, 0.10, 1.0)
            content._bg = RoundedRectangle(pos=content.pos, size=content.size, radius=[dp(12)])
            Color(*COL_BORDER)
            content._border = Line(rounded_rectangle=(content.x, content.y, content.width, content.height, dp(12)), width=1.2)
        content.bind(
            pos=lambda inst, v: setattr(inst._bg, 'pos', inst.pos) or setattr(inst._border, 'rounded_rectangle', (inst.x, inst.y, inst.width, inst.height, dp(12))),
            size=lambda inst, v: setattr(inst._bg, 'size', inst.size) or setattr(inst._border, 'rounded_rectangle', (inst.x, inst.y, inst.width, inst.height, dp(12)))
        )

        # Runs Info Box
        info_box = BoxLayout(orientation="horizontal", spacing=dp(14), size_hint_y=None, height=dp(70))
        with info_box.canvas.before:
            Color(*COL_PANEL_ALT)
            info_box._bg = RoundedRectangle(pos=info_box.pos, size=info_box.size, radius=[dp(6)])
            Color(*COL_BORDER)
            info_box._border = Line(rounded_rectangle=(info_box.x, info_box.y, info_box.width, info_box.height, dp(6)), width=1.0)
        info_box.bind(pos=lambda inst, v: setattr(inst._bg, 'pos', inst.pos) or setattr(inst._border, 'rounded_rectangle', (inst.x, inst.y, inst.width, inst.height, dp(6))),
                      size=lambda inst, v: setattr(inst._bg, 'size', inst.size) or setattr(inst._border, 'rounded_rectangle', (inst.x, inst.y, inst.width, inst.height, dp(6))))

        # Before column
        b_box = BoxLayout(orientation="vertical", padding=dp(8))
        b_title = Label(text="BEFORE CLEANING RUN", font_size="10sp", bold=True, color=COL_YELLOW, size_hint_y=None, height=dp(16), halign="left")
        _bind_text_size(b_title)
        b_box.add_widget(b_title)
        b_name = Label(text=f"#{before_rec.get('serial', '?')} - {os.path.basename(before_rec.get('filename', ''))}", font_size="12sp", bold=True, color=COL_TEXT, size_hint_y=None, height=dp(20), halign="left")
        _bind_text_size(b_name)
        b_box.add_widget(b_name)
        info_box.add_widget(b_box)

        # After column
        a_box = BoxLayout(orientation="vertical", padding=dp(8))
        a_title = Label(text="AFTER CLEANING RUN", font_size="10sp", bold=True, color=COL_GREEN, size_hint_y=None, height=dp(16), halign="left")
        _bind_text_size(a_title)
        a_box.add_widget(a_title)
        a_name = Label(text=f"#{after_rec.get('serial', '?')} - {os.path.basename(after_rec.get('filename', ''))}", font_size="12sp", bold=True, color=COL_TEXT, size_hint_y=None, height=dp(20), halign="left")
        _bind_text_size(a_name)
        a_box.add_widget(a_name)
        info_box.add_widget(a_box)
        content.add_widget(info_box)

        # Status & Progress Box
        prog_box = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None, height=dp(64))
        self.lbl_status = Label(
            text="Ready to align trajectories using DTW and generate comparison video.",
            font_size="12sp", color=COL_TEXT, halign="left", valign="middle"
        )
        _bind_text_size(self.lbl_status)
        prog_box.add_widget(self.lbl_status)

        self.progress_bar = ProgressBar(max=100.0, value=0.0, size_hint_y=None, height=dp(18))
        prog_box.add_widget(self.progress_bar)

        self.lbl_pct = Label(text="0%", font_size="11sp", bold=True, color=COL_TEXT_DIM, size_hint_y=None, height=dp(16), halign="right")
        _bind_text_size(self.lbl_pct)
        prog_box.add_widget(self.lbl_pct)
        content.add_widget(prog_box)

        content.add_widget(Widget())

        # Action Buttons
        btn_row = BoxLayout(spacing=dp(10), size_hint_y=None, height=dp(44))
        self.btn_cancel = RoundedButton(
            text="CANCEL", bg_color=COL_PANEL_ALT, fg_color=COL_TEXT, border_color=COL_BORDER,
            size_hint_x=0.3
        )
        self.btn_cancel.bind(on_press=lambda x: self.dismiss())
        btn_row.add_widget(self.btn_cancel)

        self.btn_action = RoundedButton(
            text="START COMPARISON", icon_cls=CompareIcon, icon_color=(1, 1, 1, 1),
            bg_color=COL_BLUE, fg_color=(1, 1, 1, 1), size_hint_x=0.7
        )
        self.btn_action.bind(on_press=self._handle_action_click)
        btn_row.add_widget(self.btn_action)
        content.add_widget(btn_row)

        self.content = content
        self.is_running = False

    def update_progress(self, pct: float, status_str: str):
        self.progress_bar.value = pct
        self.lbl_pct.text = f"{pct:.0f}%"
        self.lbl_status.text = status_str
        if pct >= 100.0:
            self.is_running = False
            self.btn_action.disabled = False
            self.btn_action.opacity = 1.0
            self.btn_action.label.text = "PLAY COMPARISON VIDEO"
            self.btn_action.bg_color = COL_GREEN
            self.btn_action._bgcol.rgba = COL_GREEN
            self.btn_cancel.label.text = "CLOSE"
        elif "Error" in status_str or "FAILED" in status_str:
            self.is_running = False
            self.btn_action.disabled = False
            self.btn_action.opacity = 1.0
            self.btn_action.label.text = "RETRY COMPARISON"

    def set_result_file(self, path):
        self.result_filename = path

    def _handle_action_click(self, instance):
        if self.progress_bar.value >= 100.0:
            res_file = self.result_filename
            if not res_file or not os.path.exists(res_file):
                b_name = os.path.basename(os.path.splitext(self.before_rec.get('filename', ''))[0])
                a_name = os.path.basename(os.path.splitext(self.after_rec.get('filename', ''))[0])
                v_dir = os.path.dirname(self.before_rec.get('filename', ''))
                cand1 = os.path.join(v_dir, "merged_videos", f"{b_name}_vs_{a_name}.mp4")
                cand2 = os.path.expanduser(f"~/ductbot_recordings/merged_videos/{b_name}_vs_{a_name}.mp4")
                cand3 = f"/home/roboserv-4i/Downloads/DuctbotsUI/Basic-Ductbots-main/videos/merged_videos/{b_name}_vs_{a_name}.mp4"
                if os.path.exists(cand1):
                    res_file = cand1
                elif os.path.exists(cand2):
                    res_file = cand2
                elif os.path.exists(cand3):
                    res_file = cand3

            self.dismiss()
            if self.on_play_result and res_file and os.path.exists(res_file):
                self.on_play_result(res_file)
        elif not self.is_running:
            self.is_running = True
            self.btn_action.disabled = True
            self.btn_action.opacity = 0.6
            self.on_start_comparison(self.before_rec, self.after_rec, self)


class VideoOverlay(FloatLayout):
    _INACTIVE_BG = (0.02, 0.03, 0.05, 0.72)

    def __init__(self, image_widget, on_toggle_fullscreen=None, on_flip=None, on_toggle_lane=None, on_switch_cam=None, on_toggle_map=None, on_reset_odom=None, **kwargs):
        super().__init__(**kwargs)
        # FloatLayout only repositions children that have a pos_hint; without
        # one a child keeps its default pos (0, 0) instead of tracking this
        # layout's actual position.
        image_widget.size_hint = (1, 1)
        image_widget.pos_hint = {"x": 0, "y": 0}
        self.add_widget(image_widget)

        self.active_camera = "FRONT"

        # Top-left: persistent mode badge showing mode and active camera (FRONT / REAR)
        self.mode_badge = Badge(COL_BLUE, "LIVE MODE - FRONT", icon_cls=CameraIcon, pos_hint={"x": 0.02, "top": 0.96})
        self.add_widget(self.mode_badge)

        self.rec_badge = Badge(COL_RED, "REC 00:00:00", pos_hint={"x": 0.02, "top": 0.88})
        self.rec_badge.opacity = 0
        self.add_widget(self.rec_badge)

        # Bottom-left: Sensor Telemetry HUD
        self.telemetry_hud = SensorTelemetryHUD(pos_hint={"x": 0.02, "y": 0.03})
        self.add_widget(self.telemetry_hud)

        # Top-right: Switch Cam + Lane Guides + Flip Camera + fullscreen toggle
        top_right = BoxLayout(
            size_hint=(None, None), size=(dp(430), dp(34)), spacing=dp(8),
            pos_hint={"right": 0.98, "top": 0.96},
        )

        self.switch_cam_btn = RoundedButton(
            text="CAM: FRONT", icon_cls=SwitchCamIcon, icon_color=COL_TEXT,
            bg_color=self._INACTIVE_BG, fg_color=COL_TEXT, font_size=12,
            size_hint_x=None, width=dp(125),
        )
        if on_switch_cam:
            self.switch_cam_btn.bind(on_press=lambda x: on_switch_cam())
        top_right.add_widget(self.switch_cam_btn)

        self.lane_btn = RoundedButton(
            text="LANE GUIDES", icon_cls=LaneIcon, icon_color=COL_TEXT,
            bg_color=self._INACTIVE_BG, fg_color=COL_TEXT, font_size=12,
            size_hint_x=None, width=dp(125),
        )
        if on_toggle_lane:
            self.lane_btn.bind(on_press=lambda x: on_toggle_lane())
        top_right.add_widget(self.lane_btn)

        self.flip_btn = RoundedButton(
            text="FLIP CAMERA", icon_cls=FlipIcon, icon_color=COL_TEXT,
            bg_color=self._INACTIVE_BG, fg_color=COL_TEXT, font_size=12,
            size_hint_x=None, width=dp(125),
        )
        if on_flip:
            self.flip_btn.bind(on_press=lambda x: on_flip())
        top_right.add_widget(self.flip_btn)

        self.fullscreen_btn = RoundedButton(
            text="", icon_cls=ExpandIcon, icon_color=COL_TEXT,
            bg_color=self._INACTIVE_BG, size_hint=(None, None), size=(dp(34), dp(34)),
        )
        if on_toggle_fullscreen:
            self.fullscreen_btn.bind(on_press=lambda x: on_toggle_fullscreen())
        top_right.add_widget(self.fullscreen_btn)
        self.add_widget(top_right)

    def set_recording(self, recording, elapsed_str):
        self.rec_badge.opacity = 1 if recording else 0
        self.rec_badge.label.text = f"REC {elapsed_str}"

    def set_mode_badge(self, visible, text="LIVE MODE"):
        self.mode_badge.opacity = 1 if visible else 0
        if visible and text == "LIVE MODE":
            cam = getattr(self, "active_camera", "FRONT")
            self.mode_badge.label.text = f"LIVE MODE - {cam}"
        else:
            self.mode_badge.label.text = text

    def set_active_camera(self, cam_name, source_str=""):
        cam_upper = cam_name.upper()
        self.active_camera = cam_upper
        if hasattr(self, 'mode_badge') and self.mode_badge.opacity > 0:
            self.mode_badge.label.text = f"LIVE MODE - {cam_upper}"
        self.switch_cam_btn.label.text = f"CAM: {cam_upper}"

    def update_telemetry(self, data):
        self.telemetry_hud.update_data(data)

    def set_flip_visible(self, visible):
        self.flip_btn.opacity = 1 if visible else 0
        self.flip_btn.disabled = not visible
        self.switch_cam_btn.opacity = 1 if visible else 0
        self.switch_cam_btn.disabled = not visible
        self.lane_btn.opacity = 1 if visible else 0
        self.lane_btn.disabled = not visible
        self.telemetry_hud.opacity = 1 if visible else 0

    def set_lane_active(self, active):
        color = COL_BLUE if active else self._INACTIVE_BG
        self.lane_btn.bg_color = color
        self.lane_btn._pressed_color = tuple(min(1.0, c * 1.3) if i < 3 else c for i, c in enumerate(color))
        self.lane_btn._bgcol.rgba = color
        self.lane_btn.label.color = (1, 1, 1, 1) if active else COL_TEXT
        self.lane_btn.set_icon(LaneIcon, color=(1, 1, 1, 1) if active else COL_TEXT)

    def set_map_active(self, active):
        pass

    def update_trajectory(self, *args, **kwargs):
        pass

    def reset_odometry_display(self):
        pass

    def set_fullscreen(self, is_fullscreen):
        self.fullscreen_btn.set_icon(CollapseIcon if is_fullscreen else ExpandIcon, color=COL_TEXT)


# ---------------------------------------------------------------------------
# Recording row widget & Section headers for Playback / Comparison
# ---------------------------------------------------------------------------

class PlaybackSectionHeader(BoxLayout):
    """Visual header separating Before, After, and Comparison groups."""
    def __init__(self, title, count=0, badge_color=COL_BLUE, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(36))
        kwargs.setdefault("spacing", dp(10))
        kwargs.setdefault("padding", (dp(12), dp(2)))
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(0.04, 0.07, 0.12, 0.85)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(6)])
            Color(*badge_color)
            self._left_accent = RoundedRectangle(pos=self.pos, size=(dp(4), self.height), radius=[dp(2)])
        self.bind(pos=self._update, size=self._update)

        lbl = Label(
            text=title.upper(), bold=True, font_size=sp(12), color=COL_TEXT,
            size_hint_x=None, width=dp(280), halign="left", valign="middle"
        )
        lbl.bind(size=lambda w, *_: setattr(w, 'text_size', w.size))
        self.add_widget(lbl)

        count_badge = Label(
            text=f"{count} RUN{'S' if count != 1 else ''}", font_size=sp(10), bold=True,
            color=badge_color, size_hint_x=None, width=dp(90), halign="left", valign="middle"
        )
        count_badge.bind(size=lambda w, *_: setattr(w, 'text_size', w.size))
        self.add_widget(count_badge)

        self.add_widget(Widget())

    def _update(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._left_accent.pos = self.pos
        self._left_accent.size = (dp(4), self.height)


class RecordingRowWidget(BoxLayout):
    """
    Recording row with interactive dynamic highlighting when pairing Before/After runs.
    """
    def __init__(self, rec, on_play, on_check, is_comp_mode=False, **kwargs):
        kwargs.setdefault('orientation', 'horizontal')
        kwargs.setdefault('size_hint_y', None)
        kwargs.setdefault('height', dp(52))
        kwargs.setdefault('spacing', dp(6))
        kwargs.setdefault('padding', [dp(12), dp(4)])
        super().__init__(**kwargs)
        self.rec = rec
        self.condition = rec.get('condition', 'N/A')
        self.is_comp_mode = is_comp_mode

        with self.canvas.before:
            self._bg_col = Color(*COL_PANEL_ALT)
            self._bg_rect = RoundedRectangle(size=self.size, pos=self.pos, radius=[dp(6)])
            self._border_col = Color(*COL_BORDER)
            self._border_line = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, dp(6)), width=1.0)
        self.bind(pos=self._update, size=self._update)

        # Checkbox
        self.cb = CheckBox(size_hint_x=None, width=dp(30))
        self.cb.bind(active=on_check)
        self.add_widget(self.cb)

        # Client
        self.lbl_client = Label(text=str(rec.get('client', '')), size_hint_x=0.26, color=COL_TEXT, bold=True, font_size=sp(13.5))
        self.add_widget(self.lbl_client)

        # Area
        self.lbl_area = Label(text=str(rec.get('area', '')), size_hint_x=0.26, color=COL_TEXT, font_size=sp(13))
        self.add_widget(self.lbl_area)

        # Side / Site
        self.lbl_side = Label(text=str(rec.get('side', '')), size_hint_x=0.22, color=COL_TEXT, font_size=sp(13))
        self.add_widget(self.lbl_side)

        # Condition Badge
        cond_val = self.condition
        if cond_val == 'Before':
            cond_badge_col = COL_YELLOW
        elif cond_val == 'After':
            cond_badge_col = COL_GREEN
        elif cond_val == 'Comparison':
            cond_badge_col = COL_BLUE
        else:
            cond_badge_col = COL_TEXT
        self.lbl_cond = Label(text=cond_val, size_hint_x=0.14, color=cond_badge_col, bold=True, font_size=sp(13))
        self.add_widget(self.lbl_cond)

        # Camera
        self.lbl_cam = Label(text=str(rec.get('camera', 'Front')), size_hint_x=0.12, color=COL_TEXT_DIM, font_size=sp(13))
        self.add_widget(self.lbl_cam)

        # Play Button
        btn_box = BoxLayout(size_hint_x=None, width=dp(64), padding=[dp(2), dp(4)])
        self.btn_play = RoundedButton(
            text='Play', icon_cls=PlayIcon, icon_color=(1, 1, 1, 1),
            bg_color=COL_BLUE if cond_val != 'After' else (0.12, 0.55, 0.32, 1),
            fg_color=(1, 1, 1, 1), font_size=11, radius=6
        )
        self.btn_play.bind(on_press=lambda x: on_play(self.rec))
        btn_box.add_widget(self.btn_play)
        self.add_widget(btn_box)

    def _update(self, *a):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size
        self._border_line.rounded_rectangle = (self.x, self.y, self.width, self.height, dp(6))

    def set_highlight(self, mode=None, recommended=False, match_text=None):
        """
        Highlight styling for reciprocal pairing:
        mode:
          - 'selected': This row is checked
          - 'highlight_after': Highlight as available After candidate
          - 'highlight_before': Highlight as available Before candidate
          - None: Normal state
        """
        if self.cb.active:
            if self.condition == 'Before':
                self._bg_col.rgba = (0.28, 0.22, 0.05, 0.95)
                self._border_col.rgba = COL_YELLOW
                self._border_line.width = 2.0
            elif self.condition == 'After':
                self._bg_col.rgba = (0.05, 0.28, 0.15, 0.95)
                self._border_col.rgba = COL_GREEN
                self._border_line.width = 2.0
            else:
                self._bg_col.rgba = (0.10, 0.22, 0.38, 0.95)
                self._border_col.rgba = COL_BLUE
                self._border_line.width = 2.0
        elif mode == 'highlight_after':
            if recommended:
                self._bg_col.rgba = (0.04, 0.22, 0.12, 0.9)
                self._border_col.rgba = COL_GREEN
                self._border_line.width = 2.0
            else:
                self._bg_col.rgba = (0.02, 0.14, 0.08, 0.8)
                self._border_col.rgba = (0.2, 0.7, 0.4, 0.8)
                self._border_line.width = 1.4
        elif mode == 'highlight_before':
            if recommended:
                self._bg_col.rgba = (0.22, 0.18, 0.04, 0.9)
                self._border_col.rgba = COL_YELLOW
                self._border_line.width = 2.0
            else:
                self._bg_col.rgba = (0.15, 0.12, 0.02, 0.8)
                self._border_col.rgba = (0.8, 0.7, 0.2, 0.8)
                self._border_line.width = 1.4
        else:
            self._bg_col.rgba = COL_PANEL_ALT
            self._border_col.rgba = COL_BORDER
            self._border_line.width = 1.0


# ---------------------------------------------------------------------------
# On-Screen Virtual Keyboard
# ---------------------------------------------------------------------------

class KeyButton(ButtonBehavior, BoxLayout):
    def __init__(self, label="", value=None, key_type="char", bg_color=COL_PANEL_ALT, fg_color=COL_TEXT, on_key=None, **kwargs):
        kwargs.setdefault("size_hint_y", 1.0)
        kwargs.setdefault("padding", [dp(2), dp(2)])
        super().__init__(**kwargs)
        self.value = value if value is not None else label
        self.key_type = key_type
        self.on_key = on_key
        self.base_bg = bg_color
        self._pressed_bg = tuple(min(1.0, c * 1.35) if i < 3 else c for i, c in enumerate(bg_color))

        with self.canvas.before:
            self._bgcol = Color(*self.base_bg)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
            self._border_col = Color(*COL_BORDER)
            self._border = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, dp(8)), width=1.2)
        self.bind(pos=self._update, size=self._update)

        self.lbl = Label(text=label, color=fg_color, bold=True, font_size=sp(16))
        self.add_widget(self.lbl)

    def _update(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._border.rounded_rectangle = (self.x, self.y, self.width, self.height, dp(8))

    def on_press(self):
        self._bgcol.rgba = self._pressed_bg
        if self.on_key:
            self.on_key(self.key_type, self.value)

    def on_release(self):
        self._bgcol.rgba = self.base_bg

    def update_char(self, char):
        self.value = char
        self.lbl.text = char


class OnScreenKeyboard(BoxLayout):
    """
    Touchscreen virtual keyboard for field operator input.
    """
    def __init__(self, get_target_input=None, on_submit=None, on_next=None, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(285))
        kwargs.setdefault("spacing", dp(6))
        kwargs.setdefault("padding", [dp(8), dp(8)])
        super().__init__(**kwargs)
        self.get_target_input = get_target_input
        self.on_submit = on_submit
        self.on_next = on_next
        self.is_caps = True
        self.char_keys = []

        with self.canvas.before:
            Color(0.035, 0.05, 0.08, 1.0)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10)])
            Color(*COL_BORDER)
            self._border = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, dp(10)), width=1.2)
        self.bind(pos=self._update, size=self._update)

        # Row 1: Numbers & Symbols
        r1_chars = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-', '_']
        row1 = BoxLayout(spacing=dp(5), size_hint_y=1.0)
        for c in r1_chars:
            k = KeyButton(label=c, value=c, on_key=self._handle_key, size_hint_x=1.0)
            row1.add_widget(k)
        btn_bksp = KeyButton(label="BKSP", key_type="backspace", bg_color=(0.32, 0.12, 0.14, 1),
                             fg_color=(1, 0.8, 0.8, 1), on_key=self._handle_key, size_hint_x=1.6)
        row1.add_widget(btn_bksp)
        self.add_widget(row1)

        # Row 2: Q W E R T Y U I O P
        r2_chars = ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P']
        row2 = BoxLayout(spacing=dp(5), size_hint_y=1.0)
        for c in r2_chars:
            k = KeyButton(label=c, value=c, on_key=self._handle_key, size_hint_x=1.0)
            self.char_keys.append(k)
            row2.add_widget(k)
        btn_clear = KeyButton(label="CLEAR", key_type="clear", bg_color=(0.28, 0.12, 0.12, 1),
                              fg_color=(1, 0.7, 0.7, 1), on_key=self._handle_key, size_hint_x=1.4)
        row2.add_widget(btn_clear)
        self.add_widget(row2)

        # Row 3: A S D F G H J K L
        r3_chars = ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L']
        row3 = BoxLayout(spacing=dp(5), size_hint_y=1.0)
        row3.add_widget(Widget(size_hint_x=0.3))
        for c in r3_chars:
            k = KeyButton(label=c, value=c, on_key=self._handle_key, size_hint_x=1.0)
            self.char_keys.append(k)
            row3.add_widget(k)
        btn_next = KeyButton(label="NEXT", key_type="next", bg_color=COL_BLUE,
                             fg_color=(1, 1, 1, 1), on_key=self._handle_key, size_hint_x=1.6)
        row3.add_widget(btn_next)
        self.add_widget(row3)

        # Row 4: CAPS + Z X C V B N M . /
        r4_chars = ['Z', 'X', 'C', 'V', 'B', 'N', 'M', '.', '/']
        row4 = BoxLayout(spacing=dp(5), size_hint_y=1.0)
        self.btn_caps = KeyButton(label="CAPS: ON", key_type="caps", bg_color=(0.18, 0.28, 0.45, 1),
                                  fg_color=COL_BLUE, on_key=self._handle_key, size_hint_x=1.5)
        row4.add_widget(self.btn_caps)
        for c in r4_chars:
            k = KeyButton(label=c, value=c, on_key=self._handle_key, size_hint_x=1.0)
            if c.isalpha():
                self.char_keys.append(k)
            row4.add_widget(k)
        row4.add_widget(Widget(size_hint_x=0.4))
        self.add_widget(row4)

        # Row 5: SPACE + DONE
        row5 = BoxLayout(spacing=dp(5), size_hint_y=1.0)
        row5.add_widget(Widget(size_hint_x=1.5))
        btn_space = KeyButton(label="SPACE", value=" ", key_type="char", bg_color=COL_PANEL_ALT,
                              fg_color=COL_TEXT, on_key=self._handle_key, size_hint_x=5.0)
        row5.add_widget(btn_space)
        btn_submit = KeyButton(label="DONE", key_type="submit", bg_color=COL_GREEN,
                               fg_color=(1, 1, 1, 1), on_key=self._handle_key, size_hint_x=2.2)
        row5.add_widget(btn_submit)
        row5.add_widget(Widget(size_hint_x=1.0))
        self.add_widget(row5)

    def _update(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._border.rounded_rectangle = (self.x, self.y, self.width, self.height, dp(10))

    def _handle_key(self, key_type, value):
        target = self.get_target_input() if self.get_target_input else None

        if key_type == "char":
            if target:
                col = getattr(target, 'cursor_col', len(target.text))
                t = target.text
                target.text = t[:col] + value + t[col:]
                try:
                    target.cursor = (col + len(value), 0)
                except Exception:
                    pass
        elif key_type == "backspace":
            if target and target.text:
                col = getattr(target, 'cursor_col', len(target.text))
                if col > 0:
                    t = target.text
                    target.text = t[:col - 1] + t[col:]
                    try:
                        target.cursor = (col - 1, 0)
                    except Exception:
                        pass
                else:
                    target.text = target.text[:-1]
        elif key_type == "clear":
            if target:
                target.text = ""
                try:
                    target.cursor = (0, 0)
                except Exception:
                    pass
        elif key_type == "caps":
            self.is_caps = not self.is_caps
            self.btn_caps.lbl.text = "CAPS: ON" if self.is_caps else "caps: off"
            self.btn_caps.lbl.color = COL_BLUE if self.is_caps else COL_TEXT_DIM
            for k in self.char_keys:
                new_c = k.value.upper() if self.is_caps else k.value.lower()
                k.update_char(new_c)
        elif key_type == "next":
            if self.on_next:
                self.on_next()
        elif key_type == "submit":
            if self.on_submit:
                self.on_submit()


