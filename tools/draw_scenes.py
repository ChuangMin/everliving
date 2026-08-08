"""Draw the scene pictures, because nothing here can generate them.

人類 2026-08-08: 「看不懂你的美術以及視覺畫面 太不行了」, then 「我沒有生圖工具 你幫我生圖」.
There is no image-generation tool in this session, so these are composed in code instead
— which is a different thing from the procedural svg he rejected, in one way that matters:

    the svg scatters random rectangles across a skyline fifty metres away;
    this places a named object at a chosen spot, an arm's length from the camera.

That distance is the whole point. Everything the writing talks about — a yellowing
filter cartridge, rust eating deeper into a bracket, a wrist that will not take load —
happens within reach of the bench, and a wide establishing shot cannot show any of it.

Lighting is computed rather than painted: every surface gets a flat albedo, then one
sodium lamp's falloff multiplies the whole frame. That is what buys the value
separation the drawn scenes never had — inside the pool reads bright, outside falls to
near-black, and objects cannot accidentally end up the same value as the wall behind
them.

    python tools/draw_scenes.py                # every scene
    python tools/draw_scenes.py 工作間          # just one
    python tools/draw_scenes.py --stage 4      # that scene at a stage of the world
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "src" / "everliving" / "static" / "scenes"

#: Authored large and downsampled at the end: the only antialiasing that costs nothing
#: to reason about. The ratio is the svg viewBox's, 1000x420, because the page slices
#: the picture to fill and a different ratio would crop from the middle outwards.
W, H = 2000, 840
SS = 2  # supersample factor for shape drawing

#: Straight off `index.html`'s custom properties, so a picture cannot drift away from
#: the interface it sits above.
BRINE = (11, 26, 33)
SALT = (223, 231, 234)
RUST = (140, 74, 47)
SODIUM = (240, 180, 92)
DEEP = (5, 12, 16)

#: Albedo, not final pixels. The first version built every surface by lerping a few
#: percent away from `DEEP`, which meant the darkest thing in frame and the brightest
#: were both nearly black before the lamp had even been applied — the picture came out
#: unreadable for the same reason the drawn scenes did. These are real mid values, and
#: the lamp is what decides which of them the player actually sees.
WALL = (26, 36, 42)
BENCH = (60, 68, 72)
BENCH_FRONT = (28, 36, 41)
METAL = (104, 114, 120)
METAL_DARK = (54, 64, 70)
GLASS = (38, 56, 64)


def _lerp(a, b, t):
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


class Frame:
    """An albedo layer plus one lamp, resolved into pixels at the end."""

    def __init__(self):
        self.albedo = Image.new("RGB", (W * SS, H * SS), WALL)
        self.pen = ImageDraw.Draw(self.albedo)
        self.lamps: list[tuple[float, float, float, float]] = []
        self.beams: list[tuple[list[tuple[float, float]], float]] = []
        self.ambient = 0.20

    # -- drawing helpers take 0..1 coordinates, so a composition reads as a layout --

    def box(self, x0, y0, x1, y1, fill):
        self.pen.rectangle(
            [x0 * W * SS, y0 * H * SS, x1 * W * SS, y1 * H * SS], fill=fill
        )

    def poly(self, points, fill):
        self.pen.polygon([(x * W * SS, y * H * SS) for x, y in points], fill=fill)

    def disc(self, cx, cy, r, fill):
        rx, ry = r * W * SS, r * W * SS
        self.pen.ellipse(
            [cx * W * SS - rx, cy * H * SS - ry, cx * W * SS + rx, cy * H * SS + ry],
            fill=fill,
        )

    def line(self, x0, y0, x1, y1, width, fill):
        self.pen.line(
            [x0 * W * SS, y0 * H * SS, x1 * W * SS, y1 * H * SS],
            fill=fill,
            width=int(width * W * SS),
        )

    def rim(self, x0, y0, x1, colour=SODIUM, weight=0.0022, alpha=0.85):
        """A lit top edge. One line is what separates an object from its background."""
        self.line(x0, y0, x1, y0, weight, colour if alpha >= 1 else _lerp(METAL, colour, alpha))

    def shadow(self, cx, cy, rx, ry=None, strength=0.55):
        """Contact shadow. Without one, everything looks pasted on rather than resting."""
        ry = ry if ry is not None else rx * 0.28
        self.pen.ellipse(
            [(cx - rx) * W * SS, (cy - ry) * H * SS,
             (cx + rx) * W * SS, (cy + ry) * H * SS],
            fill=_lerp(BENCH, DEEP, strength),
        )

    def lamp(self, cx, cy, reach, power=1.0):
        self.lamps.append((cx, cy, reach, power))

    def beam(self, points, power=0.5):
        """A shaft of light, added to the light field and blurred rather than drawn.

        Painting the wedge into the albedo gave it two dead-straight edges, and the eye
        read a triangle rather than a lamp. Light has no edges; blurring a mask into the
        lighting is the difference between 「一盞燈」 and 「這裡比較亮」.
        """
        self.beams.append((points, power))

    # -- resolve ----------------------------------------------------------------

    def render(self) -> Image.Image:
        flat = self.albedo.resize((W, H), Image.LANCZOS)
        arr = np.asarray(flat).astype(np.float32) / 255.0

        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        xx /= W
        yy /= H
        aspect = W / H

        light = np.zeros((H, W), dtype=np.float32)
        for cx, cy, reach, power in self.lamps:
            d = np.sqrt(((xx - cx) * aspect) ** 2 + (yy - cy) ** 2) / reach
            # Inverse-square-ish rather than a gaussian: the tail is what keeps the far
            # corners readable instead of collapsing them into the frame's black.
            light += power / (1.0 + d * d * 2.2)

        for points, power in self.beams:
            mask = Image.new("L", (W, H), 0)
            ImageDraw.Draw(mask).polygon([(x * W, y * H) for x, y in points], fill=255)
            mask = mask.filter(ImageFilter.GaussianBlur(W * 0.035))
            light += (np.asarray(mask).astype(np.float32) / 255.0) * power

        light = light[:, :, None]

        # The lamp is sodium, so what it adds is warm and what it leaves behind is not.
        warm = np.array([1.0, 0.74, 0.40], dtype=np.float32)
        cool = np.array([0.52, 0.74, 1.0], dtype=np.float32)
        lit = arr * (light * warm + self.ambient * cool)

        lit = 1.0 - np.exp(-lit * 2.7)  # roll the highlights off instead of clipping
        out = Image.fromarray(np.clip(lit * 255, 0, 255).astype(np.uint8))

        glow = out.filter(ImageFilter.GaussianBlur(22))
        out = Image.blend(out, Image.blend(out, glow, 0.42), 0.34)

        return _grain(_vignette(out))


def _vignette(img: Image.Image) -> Image.Image:
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx / W - 0.5) * 1.15) ** 2 + (yy / H - 0.5) ** 2)
    mask = np.clip(1.0 - (d - 0.42) * 1.05, 0.72, 1.0)[:, :, None]
    return Image.fromarray(
        np.clip(np.asarray(img).astype(np.float32) * mask, 0, 255).astype(np.uint8)
    )


def _grain(img: Image.Image) -> Image.Image:
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 4.2, (H, W, 1)).astype(np.float32)
    return Image.fromarray(
        np.clip(np.asarray(img).astype(np.float32) + noise, 0, 255).astype(np.uint8)
    )


# ---------------------------------------------------------------------------
# 工作間 — his own bench. The default opening, so it is the one that matters most.
# ---------------------------------------------------------------------------

#: The bench surface runs from its far edge to its near one. Objects stand at different
#: depths inside that band, which is what gives the frame somewhere to be — the first
#: version put everything on one line and left two empty stripes underneath it.
BENCH_FAR = 0.60
BENCH_NEAR = 0.87


def workshop(f: Frame, stage: int) -> None:
    wear = stage / 4.0  # 0 = a month before rust shows, 1 = the filter takes all night

    # --- the room behind the bench ------------------------------------------------
    f.box(0, 0, 1, BENCH_FAR, WALL)
    # A window, and the city through it: dark, because it is not what this is about.
    f.box(0.58, 0.05, 1.02, 0.50, _lerp(WALL, DEEP, 0.55))
    for i, h in enumerate((0.19, 0.31, 0.13, 0.25, 0.16)):
        x = 0.605 + i * 0.082
        f.box(x, 0.50 - h, x + 0.062, 0.50, _lerp(WALL, DEEP, 0.75))
    for x in (0.578, 0.725, 0.872):  # mullions, and they are what say 「窗」
        f.box(x, 0.05, x + 0.008, 0.505, _lerp(WALL, METAL, 0.35))
    f.box(0.578, 0.05, 1.02, 0.062, _lerp(WALL, METAL, 0.35))
    f.box(0.578, 0.494, 1.02, 0.506, _lerp(WALL, METAL, 0.35))
    for i in range(70):  # rain on the glass, heavier as the world gets worse
        x = 0.585 + (i * 0.0137) % 0.42
        y0 = 0.07 + (i * 0.0271) % 0.38
        f.line(x, y0, x - 0.005, min(0.49, y0 + 0.05 + wear * 0.04), 0.0013,
               _lerp(_lerp(WALL, DEEP, 0.55), SALT, 0.12 + wear * 0.10))

    # A shelf and a coiled hose on the left, so the wall is a room and not a backdrop.
    f.box(0.03, 0.30, 0.30, 0.322, _lerp(WALL, METAL, 0.30))
    for i, w in enumerate((0.030, 0.022, 0.036)):
        x = 0.055 + i * 0.062
        f.box(x, 0.30 - 0.055 - i * 0.008, x + w, 0.30, _lerp(WALL, METAL_DARK, 0.55))
    f.disc(0.115, 0.155, 0.036, _lerp(WALL, METAL_DARK, 0.45))
    f.disc(0.115, 0.155, 0.020, WALL)

    # --- the bench ----------------------------------------------------------------
    f.box(0, BENCH_FAR, 1, BENCH_NEAR, BENCH)
    f.box(0, BENCH_NEAR, 1, 1.0, BENCH_FRONT)
    f.line(0, BENCH_NEAR, 1, BENCH_NEAR, 0.0018, _lerp(BENCH, SALT, 0.35))
    for i in range(30):  # scars: this bench is worked on, not bought
        x = 0.02 + (i * 0.0391) % 0.94
        y = BENCH_FAR + 0.03 + (i * 0.0231) % 0.22
        f.line(x, y, x + 0.025 + (i % 4) * 0.014, y, 0.0012,
               _lerp(BENCH, RUST if i % 3 else DEEP, 0.28))

    # --- the lamp -----------------------------------------------------------------
    # Bolted to the bench at the left, reaching over: a thing someone installed.
    f.line(0.055, BENCH_FAR, 0.062, 0.30, 0.010, _lerp(WALL, METAL, 0.55))
    f.line(0.062, 0.30, 0.285, 0.16, 0.0085, _lerp(WALL, METAL, 0.55))
    f.line(0.285, 0.16, 0.455, 0.315, 0.0080, _lerp(WALL, METAL, 0.55))
    f.disc(0.285, 0.16, 0.008, _lerp(WALL, METAL, 0.8))
    # A shade over the bulb, not across it: the first version put the shape through the
    # middle of the lamp, so it read as a card floating in front of the light.
    f.poly([(0.424, 0.330), (0.482, 0.330), (0.508, 0.386), (0.398, 0.386)],
           _lerp(WALL, METAL, 0.75))
    f.disc(0.453, 0.390, 0.021, _lerp(SODIUM, SALT, 0.35))  # the bulb

    # --- what is on the bench, back to front --------------------------------------
    # A vice, bolted down at the left. Blocky and unmistakable.
    f.shadow(0.168, 0.706, 0.075)
    f.box(0.115, 0.560, 0.222, 0.700, _lerp(WALL, METAL_DARK, 0.85))
    f.box(0.128, 0.520, 0.209, 0.566, _lerp(WALL, METAL, 0.55))
    f.box(0.156, 0.470, 0.178, 0.528, _lerp(WALL, METAL, 0.65))
    f.disc(0.167, 0.464, 0.014, _lerp(WALL, METAL, 0.75))
    f.rim(0.128, 0.520, 0.209)

    # The filter housing, opened up. The object the writing keeps naming.
    f.shadow(0.368, 0.690, 0.086)
    f.box(0.292, 0.578, 0.444, 0.684, _lerp(WALL, METAL_DARK, 0.95))
    f.disc(0.292, 0.631, 0.0265, _lerp(WALL, METAL, 0.5))
    f.disc(0.444, 0.631, 0.0265, _lerp(WALL, METAL, 0.62))
    f.disc(0.444, 0.631, 0.0170, _lerp(WALL, DEEP, 0.7))
    f.rim(0.292, 0.578, 0.444)

    # The cartridge out of it. Yellowing is the world clock turned into an object:
    # nearly white at stage 0, brown by stage 4.
    cart = _lerp(_lerp(SALT, SODIUM, 0.20 + wear * 0.50), RUST, wear * 0.55)
    f.shadow(0.492, 0.727, 0.036)
    f.box(0.470, 0.596, 0.514, 0.722, cart)
    for i in range(8):  # pleats
        x = 0.4735 + i * 0.0053
        f.line(x, 0.600, x, 0.718, 0.0013, _lerp(cart, DEEP, 0.30))
    f.box(0.466, 0.590, 0.518, 0.602, _lerp(cart, METAL, 0.45))
    f.rim(0.466, 0.590, 0.518, colour=SALT)

    # Tools laid out in a row, nearest the camera. Order is the character: he puts
    # them back. Each is a handle plus a head, which is the least that reads as a tool.
    for i, (length, head) in enumerate(((0.052, 0.015), (0.044, 0.010),
                                        (0.060, 0.019), (0.038, 0.012))):
        x = 0.556 + i * 0.048
        y = 0.762 + (i % 2) * 0.014
        # Tight and soft. The first version gave each tool a shadow wider than the tool,
        # so the row read as four beans with a yellow dash on top.
        f.shadow(x + 0.004, y + length * 0.6, head * 0.75, length * 0.42, strength=0.30)
        f.line(x, y, x, y + length, 0.0060, _lerp(WALL, METAL, 0.45))  # handle
        f.box(x - head / 2, y - 0.014, x + head / 2, y + 0.008,
              _lerp(WALL, METAL, 0.72))  # head
        f.rim(x - head / 2, y - 0.014, x + head / 2, alpha=0.7)

    # A jar of screws. Glass gets the one real highlight in the frame.
    f.shadow(0.812, 0.712, 0.044)
    f.box(0.780, 0.582, 0.845, 0.706, _lerp(WALL, GLASS, 0.9))
    f.box(0.780, 0.648, 0.845, 0.706, _lerp(WALL, METAL_DARK, 0.7))
    f.box(0.776, 0.572, 0.849, 0.590, _lerp(WALL, METAL, 0.6))
    f.line(0.791, 0.600, 0.791, 0.690, 0.0040, _lerp(GLASS, SALT, 0.55))
    f.rim(0.776, 0.572, 0.849)

    # Parts nobody wants, at the right, arriving as the world gets worse: stage 4's
    # 「他的房間現在堆著沒人要的零件」, shown instead of stated.
    for i in range(int(round(wear * 6))):
        x = 0.876 + (i % 2) * 0.052
        y = 0.672 - (i // 2) * 0.034
        f.shadow(x + 0.023, y + 0.034, 0.030, strength=0.35)
        f.box(x, y, x + 0.046, y + 0.032, _lerp(WALL, RUST, 0.45 + 0.12 * (i % 3)))
        f.rim(x, y, x + 0.046, colour=RUST)

    # Rationing dims the lamp as the world worsens — stage 3 is 「限電從一週一次變三次」.
    f.beam([(0.430, 0.386), (0.478, 0.386), (0.70, 1.0), (0.21, 1.0)],
           power=0.50 - wear * 0.12)
    f.lamp(0.470, 0.665, 0.44, power=1.85 - wear * 0.34)
    f.lamp(0.453, 0.390, 0.075, power=0.85)
    f.ambient = 0.205 - wear * 0.030


SCENES = {"工作間": workshop}


def draw(name: str, stage: int | None) -> Path:
    frame = Frame()
    SCENES[name](frame, 0 if stage is None else stage)
    picture = frame.render()
    OUT.mkdir(parents=True, exist_ok=True)
    suffix = "" if stage is None else f"-s{stage}"
    path = OUT / f"{name}{suffix}.webp"
    picture.save(path, "WEBP", quality=88, method=6)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(prog="draw-scenes")
    parser.add_argument("scene", nargs="?", choices=sorted(SCENES), default=None)
    parser.add_argument("--stage", type=int, default=None, choices=range(5))
    args = parser.parse_args(argv)

    names = [args.scene] if args.scene else sorted(SCENES)
    for name in names:
        path = draw(name, args.stage)
        print(f"{path.name}  {path.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
