"""Deterministic NixOS motion renderer and kitty transport.

The terminal owns the idle loop: this module leaves no background writer.
The mask derives from the official NixOS logo; see assets/ATTRIBUTION.md.
"""
from __future__ import annotations

import base64
import json
import math
import os
from pathlib import Path
import time
import zlib

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ASSETS = Path(__file__).with_name("assets")
SIZE = 256
TAU = math.tau


def rgb(value):
    return tuple(bytes.fromhex(value.lstrip("#")))


class Snowflake:
    def __init__(self, palette, size=SIZE):
        self.size = size
        self.palette = palette
        self.mask = Image.open(ASSETS / "nix-mask.png").convert("L").resize(
            (size, size), Image.Resampling.LANCZOS)
        self.texture = Image.new("RGBA", (size, size))
        a, b = rgb(palette["primary"]), rgb(palette["tertiary"])
        pixels = self.texture.load()
        for y in range(size):
            for x in range(size):
                t = (x + y) / (2 * (size - 1))
                pixels[x, y] = tuple(round(c * (1 - t) + d * t) for c, d in zip(a, b)) + (255,)

    def frame(self, phase, t):
        """t is normalized; idle(t=0) == idle(t=1), including every particle."""
        n = self.size
        t = max(0.0, min(1.0, t))
        if phase == "intro":
            ease = 1 - (1 - t) ** 3
            scale = 0.07 + 0.83 * ease + 0.035 * math.sin(math.pi * t) ** 2
            angle = -22 * (1 - ease)
        else:
            scale = 0.9 + 0.012 * math.sin(TAU * t)
            angle = 1.2 * math.sin(TAU * t)
        # One subpixel affine transform avoids 1-pixel jumps during breathing.
        c = n / 2
        co = math.cos(math.radians(angle)) / scale
        si = math.sin(math.radians(angle)) / scale
        mask = self.mask.transform((n, n), Image.Transform.AFFINE,
                                  (co, -si, c-co*c+si*c, si, co, c-si*c-co*c),
                                  Image.Resampling.BICUBIC)
        if phase == "intro":
            # A crystal grows radially as the mark itself expands.
            reveal = Image.new("L", (n, n))
            r = n * (0.04 + 0.72 * (1 - (1 - t) ** 2))
            ImageDraw.Draw(reveal).ellipse((n/2-r, n/2-r, n/2+r, n/2+r), fill=255)
            mask = ImageChops.multiply(mask, reveal.filter(ImageFilter.GaussianBlur(n / 100)))
        sheen = Image.new("L", (n, n))
        draw = ImageDraw.Draw(sheen)
        # Periodic travelling highlight; it has fully left the image at t=0/1.
        front = (-0.4 + 2.8 * t) * n
        for offset in range(-n // 9, n // 9):
            strength = int(64 * math.exp(-(offset / (n / 23)) ** 2))
            draw.line((front + offset, 0, front + offset - n, n), fill=strength, width=2)
        sheen = ImageChops.multiply(sheen, mask)
        color = self.texture.copy()
        color.putalpha(mask)
        highlight = Image.new("RGBA", (n, n), rgb(self.palette["on_surface"]) + (0,))
        highlight.putalpha(sheen)
        color = Image.alpha_composite(color, highlight)
        glow = Image.new("RGBA", (n, n), rgb(self.palette["primary"]) + (0,))
        glow.putalpha(mask.filter(ImageFilter.GaussianBlur(n / 42)).point(lambda v: v // 9))
        result = Image.alpha_composite(glow, color)
        particles = Image.new("RGBA", (n, n))
        draw = ImageDraw.Draw(particles)
        for index in range(6):
            a = TAU * index / 6 + 0.18 * math.sin(TAU * t)
            radius = n * (0.44 + 0.015 * math.sin(TAU * t + index))
            x, y = n / 2 + math.cos(a) * radius, n / 2 + math.sin(a) * radius
            alpha = int(135 * max(0, math.sin(TAU * t + index * 1.7)) ** 8)
            if phase == "intro":
                alpha = int(alpha * math.sin(math.pi * t) ** 2)
            color = rgb(self.palette["on_surface"]) + (alpha,)
            length = n / 100
            draw.line((x-length, y, x+length, y), fill=color, width=1)
            draw.line((x, y-length, x, y+length), fill=color, width=1)
        # Particle opacity is zero at the handoff so intro meets idle exactly.
        if phase == "idle":
            particles.putalpha(particles.getchannel("A").point(
                lambda v: round(v * math.sin(math.pi * t) ** 2)))
        return Image.alpha_composite(result, particles)


def frame_counts(settings):
    fps = settings.get("fps", 30)
    intro_ms = settings.get("durationMs", 1400)
    period_ms = settings.get("idlePeriodMs", 4800)
    # Fixed upper bounds keep uploads and terminal-side image memory predictable.
    return min(90, max(2, round(intro_ms * fps / 1000))), min(96, max(12, round(period_ms * fps / 1000)))


def command(header, payload=b""):
    """Emit base64 chunks no larger than kitty's 4096-byte protocol limit."""
    encoded = base64.b64encode(payload)
    if not encoded:
        return f"\x1b_G{header}\x1b\\"
    parts = []
    for start in range(0, len(encoded), 4096):
        more = int(start + 4096 < len(encoded))
        keys = header if start == 0 else ("a=f,q=2" if header.startswith("a=f,") else "q=2")
        parts.append(f"\x1b_G{keys},m={more};" + encoded[start:start+4096].decode("ascii") + "\x1b\\")
    return "".join(parts)


def encoded_frames(renderer, phase, count):
    # First and last intro frames are endpoints. Idle excludes the duplicate end.
    denominator = count - 1 if phase == "intro" else count
    return [zlib.compress(renderer.frame(phase, i / denominator).tobytes(), 3) for i in range(count)]


def upload(frames, image_id, columns, rows, gap, size=SIZE):
    first = command(f"a=T,f=32,o=z,s={size},v={size},i={image_id},q=2,C=1,c={columns},r={rows}", frames[0])
    # Each frame replaces the entire transparent canvas: no accumulating trails.
    chunks = [first, command(f"a=a,i={image_id},r=1,z={gap},q=2")]
    for frame in frames[1:]:
        chunks.append(command(f"a=f,f=32,o=z,s={size},v={size},i={image_id},X=1,z={gap},q=2", frame))
    return "".join(chunks)


def play(out, palette, settings, box, line_count, blank_card, original, terminal_size, get_size):
    """Place once, play the entrance, then leave an autonomous native idle loop."""
    left, top, columns, rows = box
    # IDs are per invocation and per terminal; never delete another program's images.
    image_id = int.from_bytes(os.urandom(3), "big") * 2 + 1
    idle_id = image_id + 1
    anchor = f"\x1b7\r\x1b[{line_count-top}A\x1b[{left+1}G"
    restore = "\x1b8"
    placed = False
    success = False
    try:
        renderer = Snowflake(palette)
        intro_count, idle_count = frame_counts(settings)
        duration = settings.get("durationMs", 1400)
        intro = encoded_frames(renderer, "intro", intro_count)
        idle = encoded_frames(renderer, "idle", idle_count) if settings.get("idle", True) else []
        out.write(blank_card + anchor)
        placed = True
        out.write(upload(intro, image_id, columns, rows, max(1, round(duration / intro_count))))
        out.write(command(f"a=a,i={image_id},s=2,c=1,q=2") + restore)
        out.flush()
        start = time.monotonic()
        while time.monotonic() - start < duration / 1000:
            if get_size() != terminal_size:
                return False
            time.sleep(min(0.025, max(0, duration/1000 - (time.monotonic()-start))))
        if idle:
            out.write(anchor + upload(idle, idle_id, columns, rows,
                                      max(1, round(settings.get("idlePeriodMs", 4800) / idle_count))))
            out.write(command(f"a=a,i={idle_id},s=3,v=1,c=1,q=2") + restore)
            out.write(command(f"a=d,d=I,i={image_id},q=2"))
        else:
            out.write(command(f"a=a,i={image_id},s=1,c={intro_count},q=2"))
        success = True
        out.flush()
        return True
    finally:
        if not success:
            if placed:
                out.write(restore)
            out.write(command(f"a=d,d=I,i={image_id},q=2") + command(f"a=d,d=I,i={idle_id},q=2"))
            # Reflow makes rewinding unsafe; print a fresh card on resize.
            rewind = f"\r\x1b[{line_count}A" if get_size() == terminal_size and placed else "\r"
            out.write(rewind + original)
            out.flush()


def export_studio(palette, settings, target):
    """Produce standalone playback, frame scrubber, contact sheet and QA metrics."""
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    renderer = Snowflake(palette)
    counts = frame_counts(settings)
    manifest = {"intro": [], "idle": []}
    images = {}
    background = rgb(palette.get("surface", "#17151d"))
    for phase, count in zip(("intro", "idle"), counts):
        images[phase] = [renderer.frame(phase, i / (count-1 if phase == "intro" else count)) for i in range(count)]
        flattened = []
        for index, frame in enumerate(images[phase]):
            name = f"{phase}-{index:03}.png"
            frame.save(target / name)
            manifest[phase].append(name)
            canvas = Image.new("RGB", frame.size, background)
            canvas.paste(frame, mask=frame.getchannel("A"))
            flattened.append(canvas)
        duration = settings.get("durationMs", 1400) if phase == "intro" else settings.get("idlePeriodMs", 4800)
        flattened[0].save(target / f"{phase}.gif", save_all=True, append_images=flattened[1:],
                          duration=round(duration/count), loop=1 if phase == "intro" else 0)
    chosen = [images["intro"][round(i*(counts[0]-1)/5)] for i in range(6)] + [images["idle"][round(i*counts[1]/6)] for i in range(6)]
    sheet = Image.new("RGB", (SIZE*6, SIZE*2), background)
    for i, image in enumerate(chosen):
        sheet.paste(image, ((i%6)*SIZE, (i//6)*SIZE), image.getchannel("A"))
    sheet.save(target / "contact-sheet.png")
    # Endpoint equality plus the actual last->first frame difference catch seams.
    first, last = renderer.frame("idle", 0), renderer.frame("idle", 1)
    endpoint = ImageChops.difference(first, last).getbbox(alpha_only=False)
    handoff = ImageChops.difference(renderer.frame("intro", 1), first).getbbox(alpha_only=False)
    def difference(a, b):
        return sum(ImageChops.difference(a, b).convert("RGB").resize((32,32)).tobytes()) / (32*32*3)
    sequence = images["idle"]
    steps = [difference(sequence[i], sequence[(i+1)%len(sequence)]) for i in range(len(sequence))]
    metrics = {"endpointEqual": endpoint is None, "handoffEqual": handoff is None,
               "introFrames": counts[0], "idleFrames": counts[1],
               "loopSeamDifference": steps[-1], "maxAdjacentDifference": max(steps),
               "seamWithinMotion": steps[-1] <= max(steps[:-1]) * 1.25 + 0.05,
               "rawIdleMemoryMiB": round(counts[1]*SIZE*SIZE*4/1024**2, 2)}
    (target / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    html = '''<!doctype html><html lang="ru"><meta charset="utf-8"><title>NixOS Motion Studio</title>
<style>body{background:BG;color:FG;font:16px system-ui;max-width:960px;margin:40px auto}img{width:320px;height:320px;object-fit:contain}button,select,input{font:inherit;margin:12px;padding:8px}pre{white-space:pre-wrap}canvas{display:none}</style>
<h1>NixOS Motion Studio</h1><p>Рост кристалла → дыхание и свет. Те же кадры, что получает kitty.</p>
<img id="frame" alt="Кадр анимации"><div><select id="phase"><option value="intro">Заставка</option><option value="idle">Постоянный цикл</option></select><button id="play">Пауза</button><input id="scrub" type="range" min="0" value="0"><output id="number"></output></div>
<p><a href="intro.gif">Заставка GIF</a> · <a href="idle.gif">Цикл GIF</a> · <a href="contact-sheet.png">Ключевые кадры</a></p><pre id="metrics"></pre>
<script>const frames=MANIFEST,metrics=METRICS,durations=DURATIONS;let phase='intro',index=0,playing=true,last=0;const image=document.querySelector('#frame'),slider=document.querySelector('#scrub');function draw(){slider.max=frames[phase].length-1;slider.value=index;image.src=frames[phase][index];document.querySelector('#number').textContent=`${index+1} / ${frames[phase].length}`;}document.querySelector('#phase').onchange=e=>{phase=e.target.value;index=0;draw()};document.querySelector('#play').onclick=e=>{playing=!playing;e.target.textContent=playing?'Пауза':'Играть'};slider.oninput=e=>{playing=false;document.querySelector('#play').textContent='Играть';index=+e.target.value;draw()};document.querySelector('#metrics').textContent=JSON.stringify(metrics,null,2);function tick(t){if(playing&&t-last>durations[phase]/frames[phase].length){last=t;index++;if(index>=frames[phase].length){index=0;if(phase==='intro'){phase='idle';document.querySelector('#phase').value=phase}}draw()}requestAnimationFrame(tick)}draw();requestAnimationFrame(tick);</script></html>'''
    html = html.replace("BG", palette.get("surface", "#17151d")).replace("FG", palette["on_surface"])
    html = html.replace("MANIFEST", json.dumps(manifest)).replace("METRICS", json.dumps(metrics)).replace("DURATIONS", json.dumps({"intro": settings.get("durationMs", 1400), "idle": settings.get("idlePeriodMs", 4800)}))
    (target / "index.html").write_text(html)
    return metrics
