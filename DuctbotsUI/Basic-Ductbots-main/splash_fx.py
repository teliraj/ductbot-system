"""
Cinematic splash screen for 4i Roboserv: an animated build-up of the "4i"
logo told as Imagine -> Innovate -> Invent -> Implement -> 4i, rendered
entirely with Kivy canvas instructions (no external video/asset needed).
"""

import math
import random

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Line, Rectangle
from kivy.graphics.texture import Texture
from kivy.metrics import dp, sp
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.scatter import Scatter
from kivy.uix.widget import Widget

try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

COL_ELECTRIC_BLUE = (0.29, 0.66, 1.0, 1)
COL_NEON_CYAN = (0.32, 0.93, 0.93, 1)
COL_SOFT_WHITE = (0.94, 0.97, 1.0, 1)
COL_PURPLE_GLOW = (0.52, 0.38, 0.98, 1)


# ---------------------------------------------------------------------------
# Tweening: a small self-driven replacement for kivy.animation.Animation.
#
# kivy.animation.Animation was observed to intermittently stop progressing
# (silently, with no exception) once this splash's several concurrent
# Clock.schedule_interval loops (particles, ring, glyph, words) were all
# running together - the animated properties would just freeze at their
# starting value. The manual per-frame Clock.schedule_interval loops that
# already drive particles/ring/etc never showed that failure, so every
# animated transition here is tweened through the same proven mechanism
# instead of kivy.animation.Animation.
# ---------------------------------------------------------------------------

def ease_linear(t):
    return t


def ease_out_quad(t):
    return 1 - (1 - t) * (1 - t)


def ease_in_quad(t):
    return t * t


def ease_out_sine(t):
    return math.sin(t * math.pi / 2)


def ease_in_out_sine(t):
    return -(math.cos(math.pi * t) - 1) / 2


def ease_in_out_quad(t):
    return 2 * t * t if t < 0.5 else 1 - ((-2 * t + 2) ** 2) / 2


def ease_out_back(t, overshoot=1.70158):
    t -= 1
    return 1 + t * t * ((overshoot + 1) * t + overshoot)


def _lerp(a, b, t):
    if isinstance(a, (tuple, list)):
        # Always build a plain tuple: Kivy's own list-backed properties (e.g.
        # Label.color is an ObservableList) can't be constructed from an
        # iterable via type(a)(...), but they happily accept a plain tuple.
        return tuple(_lerp(x, y, t) for x, y in zip(a, b))
    return a + (b - a) * t


class Animator:
    """Runs many concurrent property tweens off one Clock.schedule_interval."""

    def __init__(self):
        self._tweens = []

    def animate(self, obj, duration, ease=ease_linear, on_complete=None, **targets):
        start = {}
        for k in targets:
            v = getattr(obj, k)
            start[k] = tuple(v) if isinstance(v, (tuple, list)) else v
        self._tweens.append({
            "obj": obj, "targets": targets, "start": start,
            "t": 0.0, "duration": max(duration, 1e-6), "ease": ease,
            "on_complete": on_complete,
        })

    def update(self, dt):
        if not self._tweens:
            return
        alive = []
        for tw in self._tweens:
            tw["t"] += dt
            frac = min(1.0, tw["t"] / tw["duration"])
            eased = tw["ease"](frac)
            obj = tw["obj"]
            for key, target_v in tw["targets"].items():
                setattr(obj, key, _lerp(tw["start"][key], target_v, eased))
            if frac >= 1.0:
                if tw["on_complete"]:
                    tw["on_complete"]()
            else:
                alive.append(tw)
        self._tweens = alive


def tracked(text, spacing=1):
    """Fake letter-tracking using thin spaces, for an engineering-caps look."""
    sep = " " * spacing
    return sep.join(text)


# ---------------------------------------------------------------------------
# Procedural textures (generated once, reused everywhere)
# ---------------------------------------------------------------------------

_GLOW_TEXTURE = None


def get_glow_texture():
    global _GLOW_TEXTURE
    if _GLOW_TEXTURE is not None:
        return _GLOW_TEXTURE
    size = 128
    if PILImage is None:
        tex = Texture.create(size=(2, 2), colorfmt="rgba")
        tex.blit_buffer(bytes([255, 255, 255, 255] * 4), colorfmt="rgba", bufferfmt="ubyte")
        _GLOW_TEXTURE = tex
        return tex
    img = PILImage.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    cx = cy = size / 2
    r_max = size / 2
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - cx, y - cy) / r_max
            a = max(0.0, 1.0 - d) ** 2.2
            px[x, y] = (255, 255, 255, int(255 * a))
    tex = Texture.create(size=(size, size), colorfmt="rgba")
    tex.blit_buffer(img.tobytes(), colorfmt="rgba", bufferfmt="ubyte")
    _GLOW_TEXTURE = tex
    return tex


def make_background_texture(w=48, h=256):
    if PILImage is None:
        tex = Texture.create(size=(1, 1), colorfmt="rgb")
        tex.blit_buffer(bytes([5, 8, 14]), colorfmt="rgb", bufferfmt="ubyte")
        return tex
    top = (4, 6, 11)
    bottom = (8, 17, 32)
    img = PILImage.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        t = y / (h - 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    tex = Texture.create(size=(w, h), colorfmt="rgb")
    tex.blit_buffer(img.tobytes(), colorfmt="rgb", bufferfmt="ubyte")
    return tex


def make_vignette_texture(size=256):
    if PILImage is None:
        return None
    img = PILImage.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    cx = cy = size / 2
    r_max = size * 0.75
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - cx, y - cy) / r_max
            a = max(0.0, min(1.0, (d - 0.35) / 0.65)) ** 1.6
            px[x, y] = (0, 0, 0, int(190 * a))
    tex = Texture.create(size=(size, size), colorfmt="rgba")
    tex.blit_buffer(img.tobytes(), colorfmt="rgba", bufferfmt="ubyte")
    return tex


# ---------------------------------------------------------------------------
# Scene 1 - atmosphere: gradient background + faint hex grid
# ---------------------------------------------------------------------------

class GradientBackground(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._grad_tex = make_background_texture()
        self._grad_tex.wrap = "clamp_to_edge"
        self._vin_tex = make_vignette_texture()
        with self.canvas:
            Color(1, 1, 1, 1)
            self._bg_rect = Rectangle(texture=self._grad_tex, pos=self.pos, size=self.size)
            if self._vin_tex:
                Color(1, 1, 1, 1)
                self._vin_rect = Rectangle(texture=self._vin_tex, pos=self.pos, size=self.size)
        self.bind(pos=self._update, size=self._update)

    def _update(self, *a):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size
        if self._vin_tex:
            self._vin_rect.pos = self.pos
            self._vin_rect.size = self.size


class HexGrid(Widget):
    def __init__(self, hex_size=48, **kwargs):
        super().__init__(**kwargs)
        self.hex_size = hex_size
        self.bind(pos=self._redraw, size=self._redraw)
        Clock.schedule_once(self._redraw, 0)

    def _redraw(self, *a):
        self.canvas.clear()
        w, h = self.size
        if w <= 1 or h <= 1:
            return
        s = self.hex_size
        dx = s * 1.5
        dy = s * math.sqrt(3)
        cols = int(w / dx) + 3
        rows = int(h / dy) + 3
        with self.canvas:
            Color(*COL_ELECTRIC_BLUE[:3], 0.045)
            for cx in range(cols):
                x0 = self.x + cx * dx
                y_off = dy / 2 if cx % 2 else 0
                for cy in range(rows):
                    y0 = self.y + cy * dy + y_off
                    pts = []
                    for i in range(7):
                        ang = math.radians(60 * i)
                        pts.append(x0 + s * 0.55 * math.cos(ang))
                        pts.append(y0 + s * 0.55 * math.sin(ang))
                    Line(points=pts, width=1)


# ---------------------------------------------------------------------------
# Particle field: ambient drift + radial bursts (ripples) + spiral collapse
# ---------------------------------------------------------------------------

class ParticleField(Widget):
    def __init__(self, ambient_count=80, color=COL_ELECTRIC_BLUE, **kwargs):
        super().__init__(**kwargs)
        self.glow_tex = get_glow_texture()
        self.color = color
        self.particles = []
        if ambient_count:
            Clock.schedule_once(lambda dt: self._seed_ambient(ambient_count), 0)
        self._ev = Clock.schedule_interval(self._update, 1 / 60)

    def _seed_ambient(self, count):
        for _ in range(count):
            self.particles.append(self._make_ambient(random.uniform(0, Window.height)))

    def _make_ambient(self, y=None):
        return {
            "kind": "ambient",
            "x": random.uniform(0, Window.width),
            "y": y if y is not None else -10,
            "vy": random.uniform(2, 9),
            "vx": random.uniform(-3, 3),
            "size": random.uniform(1.6, 4.2),
            "alpha": random.uniform(0.06, 0.28),
        }

    def spawn_burst(self, pos, count=16, color=None, speed=(30, 120), life=0.8, size=(3, 7)):
        color = color or self.color
        for _ in range(count):
            ang = random.uniform(0, 2 * math.pi)
            spd = random.uniform(*speed)
            self.particles.append({
                "kind": "burst",
                "x": pos[0], "y": pos[1],
                "vx": math.cos(ang) * spd, "vy": math.sin(ang) * spd,
                "size": random.uniform(*size),
                "life": life, "age": 0.0,
                "color": color,
            })

    def spawn_spiral(self, start_pos, target_pos, count=24, duration=0.85, color=None, spins=1.5):
        color = color or self.color
        for i in range(count):
            self.particles.append({
                "kind": "spiral",
                "x": start_pos[0], "y": start_pos[1],
                "start": start_pos, "target": target_pos,
                "age": -random.uniform(0, 0.18),
                "duration": duration,
                "spins": spins * random.uniform(0.85, 1.15),
                "radius0": random.uniform(16, 46),
                "angle0": random.uniform(0, 2 * math.pi),
                "size": random.uniform(3, 6),
                "alpha": 0.0,
                "color": color,
            })

    def spawn_trail(self, start_pos, end_pos, duration=0.6, color=None, tail=5):
        """A short comet of light traveling start -> end, never a static line."""
        color = color or self.color
        for i in range(tail):
            self.particles.append({
                "kind": "trail",
                "x": start_pos[0], "y": start_pos[1],
                "start": start_pos, "end": end_pos,
                "age": -i * 0.035,
                "duration": duration,
                "size": max(1.5, 5 - i * 0.8),
                "alpha": 0.0,
                "color": color,
            })

    def _update(self, dt):
        alive = []
        for p in self.particles:
            kind = p["kind"]
            if kind == "ambient":
                p["x"] += p["vx"] * dt
                p["y"] += p["vy"] * dt
                if p["y"] > Window.height + 10:
                    p.update(self._make_ambient(-10))
                alive.append(p)
            elif kind == "burst":
                p["age"] += dt
                if p["age"] >= p["life"]:
                    continue
                t = p["age"] / p["life"]
                p["x"] += p["vx"] * dt
                p["y"] += p["vy"] * dt
                p["vx"] *= 0.94
                p["vy"] *= 0.94
                p["alpha"] = 1 - t
                alive.append(p)
            elif kind == "spiral":
                p["age"] += dt
                if p["age"] < 0:
                    p["alpha"] = 0
                    alive.append(p)
                    continue
                t = min(1.0, p["age"] / p["duration"])
                ease = 1 - (1 - t) ** 3
                sx, sy = p["start"]
                tx, ty = p["target"]
                bx = sx + (tx - sx) * ease
                by = sy + (ty - sy) * ease
                r = p["radius0"] * (1 - ease)
                ang = p["angle0"] + p["spins"] * 2 * math.pi * ease
                p["x"] = bx + math.cos(ang) * r
                p["y"] = by + math.sin(ang) * r
                p["alpha"] = 1.0 if t < 0.85 else max(0.0, (1 - t) / 0.15)
                if t >= 1.0:
                    continue
                alive.append(p)
            elif kind == "trail":
                p["age"] += dt
                if p["age"] < 0:
                    p["alpha"] = 0
                    alive.append(p)
                    continue
                t = p["age"] / p["duration"]
                if t >= 1.0:
                    continue
                ease = ease_out_quad(t)
                sx, sy = p["start"]
                ex, ey = p["end"]
                p["x"] = sx + (ex - sx) * ease
                p["y"] = sy + (ey - sy) * ease
                p["alpha"] = math.sin(min(1.0, t) * math.pi)
                alive.append(p)
        self.particles = alive
        self._redraw()

    def _redraw(self):
        self.canvas.clear()
        with self.canvas:
            for p in self.particles:
                color = p.get("color", self.color)
                r, g, b, a = color
                Color(r, g, b, a * p.get("alpha", 1.0))
                s = p["size"]
                Rectangle(texture=self.glow_tex, pos=(p["x"] - s, p["y"] - s), size=(s * 2, s * 2))

    def stop(self):
        self._ev.cancel()


# ---------------------------------------------------------------------------
# Scene 2 - self-drawing energy ring
# ---------------------------------------------------------------------------

class EnergyRing(Widget):
    def __init__(self, animator, radius=200, dot_count=64, color=COL_ELECTRIC_BLUE, center_target=None, **kwargs):
        super().__init__(**kwargs)
        self.animator = animator
        self.glow_tex = get_glow_texture()
        self.radius = radius
        self.dot_count = dot_count
        self.color = color
        self.center_target = center_target or (lambda: (Window.width / 2, Window.height / 2))
        self.progress = 0.0
        self.rotation = 0.0
        self.brightness = 1.0
        self.pulses = [{"t": 0.0, "speed": 0.5}, {"t": 0.5, "speed": 0.5}]
        self._ev = Clock.schedule_interval(self._update, 1 / 60)

    def _update(self, dt):
        self.rotation -= dt * 0.12
        for p in self.pulses:
            p["t"] = (p["t"] + dt * p["speed"]) % 1.0
        self._redraw()

    def flash(self):
        def cool_down():
            self.animator.animate(self, 0.6, ease=ease_out_quad, brightness=1.0)

        self.animator.animate(self, 0.12, ease=ease_linear, on_complete=cool_down, brightness=2.4)

    def _redraw(self):
        self.canvas.clear()
        if self.progress <= 0:
            return
        cx, cy = self.center_target()
        n_visible = max(1, int(self.dot_count * self.progress))
        edge = self.progress * self.dot_count
        b = min(1.8, self.brightness)
        with self.canvas:
            r, g, bl, a = self.color
            for i in range(n_visible):
                ang = self.rotation + (i / self.dot_count) * 2 * math.pi
                x = cx + math.cos(ang) * self.radius
                y = cy + math.sin(ang) * self.radius
                fade = 1.0 if self.progress >= 1.0 else max(0.15, 1.0 - abs(i - edge) / 6.0)
                Color(r, g, bl, a * 0.55 * fade * b)
                s = 2.6
                Rectangle(texture=self.glow_tex, pos=(x - s, y - s), size=(s * 2, s * 2))
            for p in self.pulses:
                ang = self.rotation + p["t"] * 2 * math.pi
                x = cx + math.cos(ang) * self.radius
                y = cy + math.sin(ang) * self.radius
                Color(*COL_SOFT_WHITE[:3], 0.85 * b)
                s = 6
                Rectangle(texture=self.glow_tex, pos=(x - s, y - s), size=(s * 2, s * 2))

    def stop(self):
        self._ev.cancel()


# ---------------------------------------------------------------------------
# Scene 3 - the "4" constructs itself: a glowing pen traces a vector path,
# then solidifies into a crisp bold glyph with a soft halo behind it.
# ---------------------------------------------------------------------------

FOUR_PATH_A = [(0.62, 1.0), (0.05, 0.35), (0.95, 0.35)]   # diagonal + crossbar
FOUR_PATH_B = [(0.62, 1.0), (0.62, 0.0)]                  # vertical stroke


def _path_length(path):
    return sum(
        math.hypot(path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1])
        for i in range(len(path) - 1)
    )


def _partial_path(path, frac):
    if frac <= 0:
        return [], path[0]
    total = _path_length(path)
    target = total * frac
    acc = 0.0
    pts = [path[0]]
    for i in range(len(path) - 1):
        x0, y0 = path[i]
        x1, y1 = path[i + 1]
        seg = math.hypot(x1 - x0, y1 - y0)
        if acc + seg >= target:
            t = (target - acc) / seg if seg > 0 else 0
            tip = (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
            pts.append(tip)
            return pts, tip
        acc += seg
        pts.append((x1, y1))
    return pts, path[-1]


class ConstructedFour(Widget):
    def __init__(self, animator, particle_field, center_target, glyph_size=(150, 210), color=COL_ELECTRIC_BLUE, **kwargs):
        super().__init__(**kwargs)
        self.animator = animator
        self.particle_field = particle_field
        self.center_target = center_target
        self.glyph_size = glyph_size
        self.color = color
        self.glow_tex = get_glow_texture()

        self.reveal_a = 0.0
        self.reveal_b = 0.0
        self.solidify = 0.0

        self._label = Label(
            text="4", font_size=sp(glyph_size[1] * 0.95), bold=True,
            color=(*color[:3], 0), size_hint=(None, None),
        )
        self._label.texture_update()
        self._label.size = self._label.texture_size
        self.add_widget(self._label)

        self._ev = Clock.schedule_interval(self._update, 1 / 60)

    def _box(self):
        cx, cy = self.center_target()
        w, h = self.glyph_size
        return cx - w / 2, cy - h / 2, w, h

    def _to_screen(self, nx, ny):
        x, y, w, h = self._box()
        return x + nx * w, y + ny * h

    def _update(self, dt):
        self._label.color = (*self.color[:3], self.solidify)
        x, y, w, h = self._box()
        self._label.pos = (x + w / 2 - self._label.width / 2, y + h / 2 - self._label.height / 2)
        self._redraw()

    def _redraw(self):
        self.canvas.before.clear()
        vector_alpha = max(0.0, 1.0 - self.solidify)
        x, y, w, h = self._box()
        if vector_alpha <= 0.01 and self.reveal_a >= 1 and self.reveal_b >= 1:
            return
        pts_a, tip_a = _partial_path(FOUR_PATH_A, self.reveal_a)
        pts_b, tip_b = (_partial_path(FOUR_PATH_B, self.reveal_b) if self.reveal_a >= 1 else ([], None))
        with self.canvas.before:
            if self.solidify > 0.05:
                cx, cy = self.center_target()
                r, g, b, a = self.color
                Color(r, g, b, 0.32 * self.solidify)
                s = max(w, h) * 0.85
                Rectangle(texture=self.glow_tex, pos=(cx - s, cy - s), size=(s * 2, s * 2))
            if vector_alpha > 0.01:
                r, g, b, a = self.color
                if len(pts_a) >= 2:
                    Color(r, g, b, 0.9 * vector_alpha)
                    screen = []
                    for px, py in pts_a:
                        sx, sy = self._to_screen(px, py)
                        screen += [sx, sy]
                    Line(points=screen, width=dp(5), cap="round", joint="round")
                if len(pts_b) >= 2:
                    Color(r, g, b, 0.9 * vector_alpha)
                    screen = []
                    for px, py in pts_b:
                        sx, sy = self._to_screen(px, py)
                        screen += [sx, sy]
                    Line(points=screen, width=dp(5), cap="round", joint="round")
                tip = tip_b if tip_b else tip_a
                if tip and (self.reveal_a < 1 or self.reveal_b < 1):
                    sx, sy = self._to_screen(*tip)
                    Color(*COL_SOFT_WHITE[:3], vector_alpha)
                    s = dp(9)
                    Rectangle(texture=self.glow_tex, pos=(sx - s, sy - s), size=(s * 2, s * 2))

    def start(self, on_stroke_complete=None):
        def after_a():
            cx, cy = self._to_screen(*FOUR_PATH_A[1])
            self.particle_field.spawn_burst((cx, cy), count=8, color=self.color, speed=(20, 60), life=0.4)
            self.animator.animate(self, 0.35, ease=ease_out_sine, reveal_b=1.0)
            Clock.schedule_once(lambda dt: self._finish_stroke(on_stroke_complete), 0.4)

        self.animator.animate(self, 0.55, ease=ease_out_sine, on_complete=after_a, reveal_a=1.0)

    def _finish_stroke(self, cb):
        cx, cy = self.center_target()
        self.particle_field.spawn_burst((cx, cy), count=26, color=self.color, speed=(60, 180))
        self.animator.animate(self, 0.5, ease=ease_out_quad, solidify=1.0)
        if cb:
            cb()

    def stop(self):
        self._ev.cancel()


# ---------------------------------------------------------------------------
# Scenes 4-6 - the four ideas: slide in, orbit, then collapse into the "i"
# ---------------------------------------------------------------------------

WORD_DEFS = [
    ("Imagine", "left", 180),
    ("Innovate", "right", 0),
    ("Invent", "bottom", 270),
    ("Implement", "top", 90),
]


class IdeaWords(Widget):
    def __init__(self, animator, particle_field, center_target, orbit_radius=260, **kwargs):
        super().__init__(**kwargs)
        self.animator = animator
        self.particle_field = particle_field
        self.center_target = center_target
        self.orbit_radius = orbit_radius
        self.orbit_angle_offset = 0.0
        self._orbiting = False
        self._collapsed = False
        self._collapse_duration = 0.85
        self._guide_alpha = 0.0
        self._guide_target = None
        self.words = []
        for text, direction, ang_deg in WORD_DEFS:
            lbl = Label(
                text=text, font_size=sp(23), bold=True,
                color=(*COL_SOFT_WHITE[:3], 1), size_hint=(None, None),
            )
            lbl.texture_update()
            lbl.size = lbl.texture_size
            scat = Scatter(
                do_rotation=False, do_scale=False, do_translation=False,
                size_hint=(None, None), size=lbl.size,
            )
            scat.opacity = 0
            lbl.pos = (0, 0)
            scat.add_widget(lbl)
            self.add_widget(scat)
            self.words.append({
                "scatter": scat, "label": lbl, "dir": direction, "angle": math.radians(ang_deg),
            })
        self._place_initial()
        self._ev = Clock.schedule_interval(self._update, 1 / 60)

    def _rest_pos(self, w):
        cx, cy = self.center_target()
        ang = w["angle"] + self.orbit_angle_offset
        return cx + math.cos(ang) * self.orbit_radius, cy + math.sin(ang) * self.orbit_radius

    def _place_initial(self):
        ww, wh = Window.size
        offsets = {
            "left": (-ww * 0.55, 0), "right": (ww * 0.55, 0),
            "bottom": (0, -wh * 0.55), "top": (0, wh * 0.55),
        }
        for w in self.words:
            tx, ty = self._rest_pos(w)
            ox, oy = offsets[w["dir"]]
            w["scatter"].scale = 0.94
            w["scatter"].center = (tx + ox, ty + oy)

    def slide_in(self):
        """Phase 1 - arrival: position, scale and opacity move together so
        each word feels like it has mass, not just a fade-in."""
        for i, w in enumerate(self.words):
            tx, ty = self._rest_pos(w)
            scat = w["scatter"]

            def start(dt, scat=scat, tx=tx, ty=ty):
                def landed():
                    cx, cy = scat.center
                    self.particle_field.spawn_burst(
                        (cx, cy), count=14, color=COL_ELECTRIC_BLUE, speed=(25, 80), life=0.6
                    )

                self.animator.animate(scat, 0.7, ease=ease_out_back, on_complete=landed, center_x=tx, center_y=ty)
                self.animator.animate(scat, 0.6, ease=ease_out_back, scale=1.0)
                self.animator.animate(scat, 0.45, ease=ease_out_quad, opacity=1)

            Clock.schedule_once(start, i * 0.32)
        # Phase 2 - hold: intentionally nothing scheduled here. The ring keeps
        # spinning and particles keep drifting on their own loops, giving the
        # viewer a still beat to actually read the four words before Phase 3.

    def pulse_connections(self):
        """Phase 3 - a brief traveling light between neighboring words (never
        a static line) to say "these four ideas are connected"."""
        ring_order = sorted(self.words, key=lambda w: w["angle"])
        n = len(ring_order)
        for i in range(n):
            a = ring_order[i]["scatter"].center
            b = ring_order[(i + 1) % n]["scatter"].center
            self.particle_field.spawn_trail(a, b, duration=0.6, color=COL_NEON_CYAN, tail=5)

    def micro_orbit(self):
        """Phase 4 (part 1) - a small bounded rotation, not a full orbit:
        precision over spectacle. It settles rather than spins forever."""
        self._orbiting = True
        self.animator.animate(self, 0.6, ease=ease_in_out_sine, orbit_angle_offset=-0.28)

    def _update(self, dt):
        if self._orbiting and not self._collapsed:
            for w in self.words:
                w["scatter"].center = self._rest_pos(w)
        elif self._collapsed:
            self._advance_collapse(dt)
        self._redraw_guide()

    def _redraw_guide(self):
        self.canvas.before.clear()
        if self._guide_alpha <= 0.01 or not self._guide_target:
            return
        gx, gy = self._guide_target
        with self.canvas.before:
            Color(*COL_ELECTRIC_BLUE[:3], 0.55 * self._guide_alpha)
            h = dp(70) * min(1.0, 0.4 + self._guide_alpha)
            Line(points=[gx, gy - h / 2, gx, gy + h / 2], width=dp(2))

    def _advance_collapse(self, dt):
        cx, cy = self.center_target()
        for w in self.words:
            if "collapse_to_angle" not in w:
                continue
            w["collapse_t"] = min(1.0, w["collapse_t"] + dt / self._collapse_duration)
            t = w["collapse_t"]
            # Angle eases smoothly toward the "i"; radius shrinks with an
            # ease-in curve so the word keeps circling before it gets pulled
            # inward - it reads as "rotate around, then dive into the i".
            ang = w["collapse_from_angle"] + (w["collapse_to_angle"] - w["collapse_from_angle"]) * ease_in_out_sine(t)
            radius = self.orbit_radius * (1 - t * t)
            x = cx + math.cos(ang) * radius
            y = cy + math.sin(ang) * radius
            merge_start = w["merge_start"]
            scat = w["scatter"]
            if t > merge_start:
                # Final approach: blend onto the exact "i" position, fade out,
                # and shrink slightly - all driven by the same factor, so the
                # word visibly melts into the "i" instead of fading on its
                # own separate schedule.
                blend = ease_in_quad((t - merge_start) / (1 - merge_start))
                ix, iy = w["i_target"]
                x += (ix - x) * blend
                y += (iy - y) * blend
                scat.opacity = 1.0 - blend
                scat.scale = 1.0 - 0.25 * blend
            scat.center = (x, y)

    def collapse(self, i_label, i_target, on_i_formed=None):
        """Phases 4-5 - convergence + dissolve, staggered per word so the
        four ideas visibly cascade into the "i" rather than snapping at once."""
        self._collapsed = True
        self._orbiting = False
        self._guide_target = i_target
        self.animator.animate(self, 0.3, ease=ease_out_quad, _guide_alpha=1.0)

        merge_start = 0.5
        stagger = 0.13
        cx, cy = self.center_target()
        angle_i = math.atan2(i_target[1] - cy, i_target[0] - cx)

        for idx, w in enumerate(self.words):
            def start_word(dt, w=w):
                from_angle = w["angle"] + self.orbit_angle_offset
                delta = (angle_i - from_angle + math.pi) % (2 * math.pi) - math.pi
                w["collapse_from_angle"] = from_angle
                w["collapse_to_angle"] = from_angle + delta
                w["collapse_t"] = 0.0
                w["i_target"] = i_target
                w["merge_start"] = merge_start
                start_pos = w["scatter"].center
                self.particle_field.spawn_spiral(
                    start_pos, i_target, count=22,
                    duration=self._collapse_duration * (1 - merge_start) + 0.3,
                    color=COL_ELECTRIC_BLUE,
                )

            Clock.schedule_once(start_word, idx * stagger)

        last_start = (len(self.words) - 1) * stagger
        reveal_delay = last_start + self._collapse_duration * merge_start
        i_fade_duration = self._collapse_duration * (1 - merge_start) + 0.4

        def reveal_i(dt):
            self.animator.animate(i_label, i_fade_duration, ease=ease_out_quad, color=(*COL_ELECTRIC_BLUE[:3], 1))
            self.animator.animate(self, 0.5, ease=ease_in_quad, _guide_alpha=0.0)
            if on_i_formed:
                Clock.schedule_once(lambda dt2: on_i_formed(), i_fade_duration)

        Clock.schedule_once(reveal_i, reveal_delay)

    def stop(self):
        self._ev.cancel()


# ---------------------------------------------------------------------------
# Scene 7 - typography reveal
# ---------------------------------------------------------------------------

class TitleReveal(Widget):
    def __init__(self, animator, anchor, **kwargs):
        super().__init__(**kwargs)
        self.animator = animator
        self.anchor = anchor if callable(anchor) else (lambda: anchor)
        self.title = Label(
            text="4i ROBOSERV", font_size=sp(34), bold=True,
            color=(*COL_SOFT_WHITE[:3], 0), size_hint=(None, None),
        )
        self.subtitle = Label(
            text=tracked("PRIVATE LIMITED", 2), font_size=sp(15), bold=True,
            color=(*COL_ELECTRIC_BLUE[:3], 0), size_hint=(None, None),
        )
        self.tagline = Label(
            text=tracked("IMAGINE · INNOVATE · INVENT · IMPLEMENT", 1),
            font_size=sp(13), color=(*COL_NEON_CYAN[:3], 0), size_hint=(None, None),
        )
        for lbl in (self.title, self.subtitle, self.tagline):
            self.add_widget(lbl)
        self._reposition()

    def _reposition(self, *a):
        cx, base_y = self.anchor()
        self._targets = {}
        y = base_y
        for lbl, gap in ((self.title, 46), (self.subtitle, 30), (self.tagline, 34)):
            lbl.texture_update()
            lbl.size = lbl.texture_size
            self._targets[lbl] = (cx, y)
            lbl.center = (cx, y - dp(18))
            y -= gap

    def reveal(self):
        self._reposition()
        for i, lbl in enumerate((self.title, self.subtitle, self.tagline)):
            tx, ty = self._targets[lbl]

            def do(dt, lbl=lbl, tx=tx, ty=ty):
                r, g, b, _a = lbl.color
                self.animator.animate(lbl, 0.6, ease=ease_out_quad, center_x=tx, center_y=ty)
                self.animator.animate(lbl, 0.6, ease=ease_out_quad, color=(r, g, b, 1))

            Clock.schedule_once(do, i * 0.15)


# ---------------------------------------------------------------------------
# Scene 8 - status ticker + filling progress ring
# ---------------------------------------------------------------------------

STATUS_PHRASES = [
    "Initializing System...",
    "Ready.",
]


class StatusTicker(Widget):
    def __init__(self, animator, anchor, **kwargs):
        super().__init__(**kwargs)
        self.animator = animator
        self.anchor = anchor if callable(anchor) else (lambda: anchor)
        self.label = Label(
            text="", font_size=sp(13), color=(*COL_SOFT_WHITE[:3], 0), size_hint=(None, None),
        )
        self.add_widget(self.label)
        self.ring_radius = dp(4)
        self.progress_angle = 0.0
        with self.canvas:
            self._arc_color = Color(*COL_ELECTRIC_BLUE[:3], 0.0)
            self._arc = Line(width=dp(2))
        self._arc_ev = Clock.schedule_interval(self._redraw_arc, 1 / 60)

    def _redraw_arc(self, dt):
        if self.progress_angle <= 0:
            return
        cx, cy = self.anchor()
        ring_cy = cy - dp(26)
        self._arc.circle = (cx, ring_cy, self.ring_radius, -90, -90 + self.progress_angle)

    def start(self):
        self._arc_color.a = 0.7
        self.animator.animate(self, 1.8, ease=ease_linear, progress_angle=360)
        step = 1.8 / len(STATUS_PHRASES)
        for i, text in enumerate(STATUS_PHRASES):
            Clock.schedule_once(lambda dt, t=text, first=(i == 0): self._show(t, first), i * step)

    def _update_label_pos(self):
        cx, cy = self.anchor()
        self.label.texture_update()
        self.label.size = self.label.texture_size
        self.label.center = (cx, cy)

    def _show(self, text, first):
        if first:
            self.label.text = text
            self._update_label_pos()
            self.animator.animate(self.label, 0.2, ease=ease_linear, color=(*COL_SOFT_WHITE[:3], 0.85))
            return

        def swap():
            self.label.text = text
            self._update_label_pos()
            self.animator.animate(self.label, 0.18, ease=ease_linear, color=(*COL_SOFT_WHITE[:3], 0.85))

        self.animator.animate(self.label, 0.12, ease=ease_linear, on_complete=swap, color=(*COL_SOFT_WHITE[:3], 0))

    def stop(self):
        self._arc_ev.cancel()


# ---------------------------------------------------------------------------
# Master timeline
# ---------------------------------------------------------------------------

class SplashLoader(FloatLayout):
    """
    Cinematic 4i Roboserv splash. Tells the "Imagine, Innovate, Invent,
    Implement -> 4i" story - arrival, a held beat, a connecting pulse, a
    bounded micro-orbit, then a staggered convergence into "i" - then
    crossfades into the widget produced by `build_main_widget`.
    """

    DEFAULT_DURATION = 9.9
    _SCENE_OFFSETS = {
        "ring": 0.8, "four": 1.5, "words": 2.6, "connect": 4.7,
        "microorbit": 5.2, "collapse": 5.9, "title": 7.3, "status": 8.1,
        "crossfade": 9.9,
    }

    def __init__(self, build_main_widget, on_finish_callback=None, duration=DEFAULT_DURATION, **kwargs):
        super().__init__(**kwargs)
        self.build_main_widget = build_main_widget
        self.on_finish_callback = on_finish_callback
        self.duration = duration
        self.opacity = 0
        self._done = False
        self._crossfade_started = False

        self.animator = Animator()
        self._animator_ev = Clock.schedule_interval(self.animator.update, 1 / 60)

        logo_center = self._logo_center

        self.bg = GradientBackground(size_hint=(1, 1))
        self.add_widget(self.bg)
        self.hexgrid = HexGrid(size_hint=(1, 1))
        self.add_widget(self.hexgrid)
        self.ambient_particles = ParticleField(ambient_count=80, color=COL_ELECTRIC_BLUE, size_hint=(1, 1))
        self.add_widget(self.ambient_particles)

        self.logo_scatter = Scatter(
            do_rotation=False, do_scale=False, do_translation=False,
            size_hint=(None, None), size=Window.size, pos=(0, 0),
        )
        self.add_widget(self.logo_scatter)

        self.fx_particles = ParticleField(
            ambient_count=0, color=COL_ELECTRIC_BLUE, size_hint=(None, None), size=Window.size, pos=(0, 0)
        )
        self.logo_scatter.add_widget(self.fx_particles)

        self.ring = EnergyRing(
            self.animator, radius=self._ring_radius(), color=COL_ELECTRIC_BLUE, center_target=logo_center,
            size_hint=(None, None), size=(1, 1),
        )
        self.logo_scatter.add_widget(self.ring)

        self.four_glyph = ConstructedFour(
            self.animator, self.fx_particles, center_target=self._four_center, glyph_size=self._four_size(),
            color=COL_ELECTRIC_BLUE, size_hint=(None, None), size=(1, 1),
        )
        self.logo_scatter.add_widget(self.four_glyph)

        self.i_label = Label(
            text="i", font_size=sp(180 * self._scale_factor()), bold=True,
            color=(*COL_ELECTRIC_BLUE[:3], 0), size_hint=(None, None),
        )
        self.i_label.texture_update()
        self.i_label.size = self.i_label.texture_size
        ix, iy = self._i_center()
        self.i_label.pos = (ix - self.i_label.width / 2, iy - self.i_label.height / 2)
        self.logo_scatter.add_widget(self.i_label)

        self.idea_words = IdeaWords(
            self.animator, self.fx_particles, center_target=logo_center, orbit_radius=self._orbit_radius(),
            size_hint=(None, None), size=(1, 1),
        )
        self.logo_scatter.add_widget(self.idea_words)

        self.title_group = TitleReveal(self.animator, self._title_anchor, size_hint=(1, 1))
        self.add_widget(self.title_group)

        self.status_ticker = StatusTicker(self.animator, self._status_anchor, size_hint=(1, 1))
        self.add_widget(self.status_ticker)

        self.bind(size=self._on_resize)
        Window.bind(size=self._on_resize)

        self._schedule_all()

    def _on_resize(self, *a):
        ix, iy = self._i_center()
        self.i_label.center = (ix, iy)
        if hasattr(self, "title_group"):
            self.title_group._reposition()

    # -- geometry helpers ---------------------------------------------------

    def _scale_factor(self):
        return max(0.7, min(1.6, min(Window.width, Window.height) / 900.0))

    def _logo_center(self):
        return (Window.width * 0.50, Window.height * 0.56)

    def _title_anchor(self):
        return (Window.width * 0.50, Window.height * 0.30)

    def _status_anchor(self):
        cx, cy = self._title_anchor()
        return (cx, cy - dp(112))

    def _four_center(self):
        cx, cy = self._logo_center()
        return (cx - dp(37.5) * self._scale_factor(), cy)

    def _i_center(self):
        cx, cy = self._logo_center()
        return (cx + dp(78.75) * self._scale_factor(), cy)

    def _four_size(self):
        s = self._scale_factor()
        return (150 * s, 210 * s)

    def _ring_radius(self):
        return max(150, min(Window.width, Window.height) * 0.22)

    def _orbit_radius(self):
        return max(230, min(Window.width, Window.height) * 0.32)

    # -- timeline -------------------------------------------------------

    def _schedule_all(self):
        k = self.duration / self.DEFAULT_DURATION
        off = self._SCENE_OFFSETS
        Clock.schedule_once(lambda dt: self._scene1(), 0)
        Clock.schedule_once(lambda dt: self._scene_ring(), off["ring"] * k)
        Clock.schedule_once(lambda dt: self._scene_four(), off["four"] * k)
        Clock.schedule_once(lambda dt: self._scene_words(), off["words"] * k)
        Clock.schedule_once(lambda dt: self._scene_connect(), off["connect"] * k)
        Clock.schedule_once(lambda dt: self._scene_microorbit(), off["microorbit"] * k)
        Clock.schedule_once(lambda dt: self._scene_collapse(), off["collapse"] * k)
        Clock.schedule_once(lambda dt: self._scene_title(), off["title"] * k)
        Clock.schedule_once(lambda dt: self._scene_status(), off["status"] * k)
        Clock.schedule_once(lambda dt: self._crossfade(), off["crossfade"] * k)
        Clock.schedule_once(lambda dt: self._force_finish(), off["crossfade"] * k + 4.0)

    def _scene1(self):
        self.animator.animate(self, 1.0, ease=ease_out_sine, opacity=1)

    def _scene_ring(self):
        self.animator.animate(self.ring, 0.9, ease=ease_out_quad, progress=1.0)

    def _scene_four(self):
        self.four_glyph.start()

    def _scene_words(self):
        self.idea_words.slide_in()

    def _scene_connect(self):
        self.idea_words.pulse_connections()

    def _scene_microorbit(self):
        self.idea_words.micro_orbit()
        self.animator.animate(self.logo_scatter, 1.5, ease=ease_in_out_sine, scale=1.05)

    def _scene_collapse(self):
        self.idea_words.collapse(self.i_label, self._i_center(), on_i_formed=self.ring.flash)

    def _scene_title(self):
        self.title_group.reveal()

    def _scene_status(self):
        self.status_ticker.start()

    def on_touch_down(self, touch):
        if not self._crossfade_started:
            self._crossfade()
            return True
        return super().on_touch_down(touch)

    def _crossfade(self):
        if self._crossfade_started:
            return
        self._crossfade_started = True
        main_widget = self.build_main_widget()
        parent = self.parent
        if parent is not None:
            parent.add_widget(main_widget, index=len(parent.children))
            main_widget.opacity = 0
            self.animator.animate(main_widget, 1.0, ease=ease_out_quad, opacity=1)
        self.animator.animate(self, 1.0, ease=ease_in_quad, opacity=0)
        self.animator.animate(
            self.logo_scatter, 1.0, ease=ease_in_out_quad,
            scale=0.32, center_x=Window.width * 0.09, center_y=Window.height * 0.90,
        )
        Clock.schedule_once(lambda dt: self._finish(), 1.05)

    def _finish(self):
        if self._done:
            return
        self._done = True
        self._animator_ev.cancel()
        self.ambient_particles.stop()
        self.fx_particles.stop()
        self.ring.stop()
        self.four_glyph.stop()
        self.idea_words.stop()
        self.status_ticker.stop()
        try:
            Window.unbind(size=self._on_resize)
        except Exception:
            pass
        if self.parent:
            self.parent.remove_widget(self)
        if self.on_finish_callback:
            self.on_finish_callback()


    def _force_finish(self):
        if not self._done:
            self._crossfade()
            Clock.schedule_once(lambda dt: self._finish(), 1.2)


SplashScreen = SplashLoader
