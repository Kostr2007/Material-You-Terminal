#!/usr/bin/env python3
"""myt — Material You Terminal.

Generates a Material You (Material Design 3) palette with matugen and renders
it into kitty, fish, starship and fastfetch configs. At runtime it can re-theme
everything from a wallpaper and smoothly morph the colors of running kitty
windows.

Only the Python standard library is used.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

VERSION = "1.0.0"
APP = "material-you-terminal"

# Base hues for the 16 terminal colors. matugen harmonizes ("blends") them
# towards the source color so they sit naturally next to the scheme.
DEFAULT_CUSTOM_COLORS = {
    "red": "#e5484d",
    "green": "#46a758",
    "yellow": "#f5d90a",
    "blue": "#3e8ef7",
    "magenta": "#c94fd6",
    "cyan": "#12a5b8",
}

ANSI_HUES = ["red", "green", "yellow", "blue", "magenta", "cyan"]

# Material 3 easing curves (cubic-bezier control points).
EASINGS = {
    "standard": (0.2, 0.0, 0.0, 1.0),
    "emphasized-decelerate": (0.05, 0.7, 0.1, 1.0),
    "emphasized-accelerate": (0.3, 0.0, 0.8, 0.15),
    "linear": (0.0, 0.0, 1.0, 1.0),
}

HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")
PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)(?:\.(hex|strip|rgb|r|g|b))?\s*\}\}")


class MytError(Exception):
    pass


# --------------------------------------------------------------------------
# paths & config
# --------------------------------------------------------------------------

def xdg(var: str, fallback: str) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else Path.home() / fallback


def default_config_path() -> Path:
    env = os.environ.get("MYT_CONFIG")
    if env:
        return Path(env)
    return xdg("XDG_CONFIG_HOME", ".config") / APP / "config.json"


def state_dir() -> Path:
    return xdg("XDG_STATE_HOME", ".local/state") / APP


def load_config(path: Path | None) -> dict:
    path = path or default_config_path()
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        raise MytError(
            f"config not found: {path}\n"
            "Enable `programs.material-you-terminal` in home-manager, or pass --config."
        )


def theme_dir(cfg: dict) -> Path:
    return Path(os.path.expanduser(cfg.get("themeDir") or state_dir() / "theme"))


# --------------------------------------------------------------------------
# colors
# --------------------------------------------------------------------------

def norm_hex(value: str) -> str:
    m = HEX_RE.match(value.strip())
    if not m:
        raise MytError(f"not a #rrggbb color: {value!r}")
    return "#" + m.group(1).lower()


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    h = norm_hex(value)[1:]
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def _srgb_to_linear(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c: float) -> float:
    c = max(0.0, min(1.0, c))
    v = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return v * 255.0


def rgb_to_oklab(rgb):
    r, g, b = (_srgb_to_linear(c) for c in rgb)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = (math.copysign(abs(x) ** (1 / 3), x) for x in (l, m, s))
    return (
        0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
    )


def oklab_to_rgb(lab):
    L, a, b = lab
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (
        _linear_to_srgb(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
        _linear_to_srgb(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
        _linear_to_srgb(-0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s),
    )


def mix(a: str, b: str, t: float) -> str:
    """Perceptual (OKLab) interpolation between two hex colors."""
    la, lb = rgb_to_oklab(hex_to_rgb(a)), rgb_to_oklab(hex_to_rgb(b))
    return rgb_to_hex(oklab_to_rgb(tuple(x + (y - x) * t for x, y in zip(la, lb))))


def cubic_bezier(p1x: float, p1y: float, p2x: float, p2y: float):
    def sample(a1: float, a2: float, t: float) -> float:
        return 3 * a1 * (1 - t) ** 2 * t + 3 * a2 * (1 - t) * t ** 2 + t ** 3

    def ease(x: float) -> float:
        if x <= 0:
            return 0.0
        if x >= 1:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(32):
            mid = (lo + hi) / 2
            if sample(p1x, p2x, mid) < x:
                lo = mid
            else:
                hi = mid
        return sample(p1y, p2y, (lo + hi) / 2)

    return ease


def easing(name: str):
    return cubic_bezier(*EASINGS.get(name, EASINGS["standard"]))


# --------------------------------------------------------------------------
# palette generation
# --------------------------------------------------------------------------

def matugen_bin(cfg: dict) -> str:
    exe = cfg.get("matugen") or shutil.which("matugen")
    if not exe:
        raise MytError("matugen not found in PATH")
    return exe


def _matugen_supports(exe: str, flag: str) -> bool:
    try:
        out = subprocess.run([exe, "--help"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return flag in out


def _toml_str(value: str) -> str:
    return json.dumps(value)  # JSON strings are valid TOML basic strings


def run_matugen(cfg: dict, source: dict, mode: str, scheme: str, contrast: float) -> dict:
    exe = matugen_bin(cfg)
    custom = dict(DEFAULT_CUSTOM_COLORS)
    custom.update(cfg.get("customColors") or {})
    with tempfile.TemporaryDirectory(prefix="myt-") as tmp:
        conf = Path(tmp) / "matugen.toml"
        lines = ["[config]", "", "[config.custom_colors]"]
        for name, value in custom.items():
            lines.append(f"{name} = {{ color = {_toml_str(norm_hex(value))}, blend = true }}")
        lines += ["", "[templates]"]  # required by matugen, we render ourselves
        conf.write_text("\n".join(lines) + "\n")

        args = [exe, "-c", str(conf)]
        if "image" in source:
            image = os.path.expanduser(source["image"])
            if not os.path.isfile(image):
                raise MytError(f"image not found: {image}")
            args += ["image", image]
            if _matugen_supports(exe, "--source-color-index"):
                args += ["--source-color-index", "0"]
        elif "color" in source:
            args += ["color", "hex", norm_hex(source["color"])]
        else:
            raise MytError(f"unsupported source: {source}")
        args += ["-m", mode, "-t", scheme, "--contrast", str(contrast), "-j", "hex", "--dry-run"]

        env = dict(os.environ)
        home = env.get("HOME", "")
        if not home or not os.access(home, os.W_OK):
            env["HOME"] = tmp  # e.g. inside the nix build sandbox
        env.setdefault("XDG_CACHE_HOME", os.path.join(tmp, "cache"))
        proc = subprocess.run(args, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
        if proc.returncode != 0:
            raise MytError(f"matugen failed ({proc.returncode}):\n{proc.stderr or proc.stdout}")
        out = proc.stdout
        start = out.find("{")
        if start < 0:
            raise MytError(f"matugen produced no JSON:\n{out}\n{proc.stderr}")
        return json.JSONDecoder().raw_decode(out[start:])[0]


def roles_from_matugen_json(data: dict, mode: str) -> dict[str, str]:
    """Accepts both the matugen >= 4 and the older JSON layout."""
    colors = data.get("colors", data)
    roles: dict[str, str] = {}
    if isinstance(colors.get(mode), dict) and "primary" in colors[mode]:
        # old layout: {"colors": {"dark": {"primary": "#..."}, "light": {...}}}
        for name, value in colors[mode].items():
            if isinstance(value, str) and HEX_RE.match(value):
                roles[name] = norm_hex(value)
        return roles
    for name, entry in colors.items():
        if isinstance(entry, str) and HEX_RE.match(entry):
            roles[name] = norm_hex(entry)
            continue
        if not isinstance(entry, dict):
            continue
        variant = entry.get(mode) or entry.get("default")
        if isinstance(variant, dict):
            variant = variant.get("color")
        if isinstance(variant, str) and HEX_RE.match(variant):
            roles[name] = norm_hex(variant)
    return roles


def add_terminal_roles(p: dict[str, str], mode: str, fixed: set[str]) -> None:
    """Derives the 16 ANSI colors (ansi0..ansi15) from the scheme."""

    def put(key: str, value: str) -> None:
        if key not in fixed:
            p[key] = value

    def get(*names: str) -> str:
        for n in names:
            if n in p:
                return p[n]
        raise MytError(f"palette is missing all of: {', '.join(names)}")

    dark = mode == "dark"
    put("ansi0", get("surface_container_high", "surface_variant") if dark else get("on_surface"))
    put("ansi8", get("outline"))
    put("ansi7", get("on_surface_variant") if dark else get("outline_variant"))
    put("ansi15", get("on_surface") if dark else get("surface_container_highest", "surface_variant"))
    for i, hue in enumerate(ANSI_HUES, start=1):
        fallback = {"red": "error", "green": "tertiary", "yellow": "secondary",
                    "blue": "primary", "magenta": "tertiary", "cyan": "secondary"}[hue]
        normal = get(hue, fallback)
        deep = get(f"on_{hue}_container", f"on_{fallback}_container", hue, fallback)
        put(f"ansi{i}", normal)
        # dark: a lighter tone; light: a deeper tone that keeps its hue
        put(f"ansi{i + 8}", deep if dark else mix(normal, deep, 0.45))


def build_palette(cfg: dict, source: dict, mode: str, scheme: str, contrast: float) -> dict[str, str]:
    overrides = {k: norm_hex(v) for k, v in (cfg.get("overrides") or {}).items()}
    if "json" in source:
        path = os.path.expanduser(source["json"])
        with open(path) as f:
            data = json.load(f)
        roles = roles_from_matugen_json(data, mode)
        # Regenerate from the same seed so the harmonized ANSI hues exist too,
        # then lay the user's (possibly hand-tuned) roles on top.
        seed = roles.get("source_color") or roles.get("primary")
        if seed:
            base = roles_from_matugen_json(
                run_matugen(cfg, {"color": seed}, mode, scheme, contrast), mode)
            base.update(roles)
            roles = base
    else:
        roles = roles_from_matugen_json(run_matugen(cfg, source, mode, scheme, contrast), mode)
    if "primary" not in roles or "surface" not in roles:
        raise MytError("matugen output did not contain a Material You scheme")
    roles.update(overrides)
    add_terminal_roles(roles, mode, set(overrides))
    return dict(sorted(roles.items()))


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def render(text: str, palette: dict[str, str], mode: str, origin: str) -> str:
    def sub(m: re.Match) -> str:
        name, fmt = m.group(1), m.group(2) or "hex"
        if name == "mode":
            return mode
        if name not in palette:
            raise MytError(f"{origin}: unknown color role {{{{{name}}}}}")
        value = palette[name]
        r, g, b = hex_to_rgb(value)
        return {
            "hex": value,
            "strip": value[1:],
            "rgb": f"{r};{g};{b}",
            "r": str(r), "g": str(g), "b": str(b),
        }[fmt]

    return PLACEHOLDER_RE.sub(sub, text)


def atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    with os.fdopen(fd, "w") as f:
        f.write(data)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def generate(cfg: dict, out: Path, source: dict, mode: str, scheme: str, contrast: float) -> dict:
    palette = build_palette(cfg, source, mode, scheme, contrast)
    templates = cfg.get("templates") or {}
    if not templates:
        raise MytError("no templates configured")
    rendered = {}
    for name, tpl in templates.items():
        with open(tpl) as f:
            rendered[name] = render(f.read(), palette, mode, tpl)
    out.mkdir(parents=True, exist_ok=True)
    for name, text in rendered.items():
        atomic_write(out / name, text)
    meta = {"mode": mode, "scheme": scheme, "contrast": contrast, "source": source, "colors": palette}
    atomic_write(out / "palette.json", json.dumps(meta, indent=2) + "\n")
    return meta


# --------------------------------------------------------------------------
# kitty: live color morphing over the remote control socket
# --------------------------------------------------------------------------

def kitty_sockets(cfg: dict) -> list[str]:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    pattern = (cfg.get("kitty") or {}).get("socketGlob") or "${XDG_RUNTIME_DIR}/kitty-myt-*"
    pattern = pattern.replace("${XDG_RUNTIME_DIR}", runtime)
    socks = []
    for path in glob.glob(os.path.expandvars(pattern)):
        pid = path.rsplit("-", 1)[-1]
        if pid.isdigit():
            try:
                os.kill(int(pid), 0)
            except ProcessLookupError:
                continue
            except PermissionError:
                pass
        socks.append(path)
    return sorted(socks)


def kitty_rc(sock: str, cmd: str, payload: dict, want_response: bool = False, timeout: float = 2.0):
    msg = {"cmd": cmd, "version": [0, 26, 0], "no_response": not want_response, "payload": payload}
    data = b"\x1bP@kitty-cmd" + json.dumps(msg).encode() + b"\x1b\\"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(sock)
        s.sendall(data)
        if not want_response:
            return None
        buf = b""
        while not buf.endswith(b"\x1b\\"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    m = re.search(rb"\x1bP@kitty-cmd(.*)\x1b\\", buf, re.S)
    if not m:
        raise MytError(f"kitty sent an unexpected reply on {sock}")
    reply = json.loads(m.group(1))
    if not reply.get("ok"):
        raise MytError(f"kitty: {reply.get('error')}")
    return reply.get("data")


def parse_kitty_colors(text: str) -> dict[str, str]:
    colors = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and HEX_RE.match(parts[1]) and not parts[0].startswith("#"):
            colors[parts[0]] = norm_hex(parts[1])
    return colors


def morph_kitty(sock: str, target: dict[str, str], duration: float, ease) -> None:
    def push(colors: dict[str, str], configured: bool) -> None:
        kitty_rc(sock, "set-colors", {
            "colors": {k: int(v[1:], 16) for k, v in colors.items()},
            "all": True, "configured": configured, "reset": False,
        })

    current = {}
    if duration > 0:
        try:
            current = parse_kitty_colors(kitty_rc(sock, "get-colors", {"configured": False}, True) or "")
        except (OSError, MytError, ValueError):
            current = {}
    keys = [k for k in target if k in current and current[k] != target[k]]
    if keys and duration > 0:
        labs = {k: (rgb_to_oklab(hex_to_rgb(current[k])), rgb_to_oklab(hex_to_rgb(target[k]))) for k in keys}
        start = time.monotonic()
        frame = 1 / 60
        while True:
            t = (time.monotonic() - start) / duration
            if t >= 1:
                break
            e = ease(t)
            push({k: rgb_to_hex(oklab_to_rgb(tuple(x + (y - x) * e for x, y in zip(a, b))))
                  for k, (a, b) in labs.items()}, False)
            time.sleep(frame)
    push(target, True)


def sync_kitty(cfg: dict, colors_file: Path, animate: bool = True, quiet: bool = False) -> int:
    kcfg = cfg.get("kitty") or {}
    if not colors_file.exists():
        return 0
    target = parse_kitty_colors(colors_file.read_text())
    duration = kcfg.get("transitionMs", 450) / 1000 if animate and cfg.get("animations", True) else 0
    ease = easing(kcfg.get("easing", "standard"))
    socks = kitty_sockets(cfg)
    errors: list[str] = []

    def worker(sock: str) -> None:
        try:
            morph_kitty(sock, target, duration, ease)
        except (OSError, MytError) as exc:
            errors.append(f"{sock}: {exc}")

    threads = [threading.Thread(target=worker, args=(s,)) for s in socks]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=duration + 5)
    if not quiet:
        for e in errors:
            print(f"myt: kitty {e}", file=sys.stderr)
    return len(socks) - len(errors)


def notify_shells() -> None:
    # fish re-reads colors.fish on the next prompt (see __myt_watch); nudging
    # fish with SIGWINCH makes idle prompts repaint right away.
    try:
        subprocess.run(["pkill", "-WINCH", "-u", str(os.getuid()), "-x", "fish"],
                       capture_output=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        pass


# --------------------------------------------------------------------------
# terminal eye-candy
# --------------------------------------------------------------------------

def _palette_for_display(cfg: dict) -> dict[str, str]:
    try:
        with open(theme_dir(cfg) / "palette.json") as f:
            return json.load(f)["colors"]
    except (OSError, KeyError, ValueError):
        raise MytError("no generated palette yet — run `myt refresh` or `myt apply`")


def _fg(h: str) -> str:
    return "\x1b[38;2;{};{};{}m".format(*hex_to_rgb(h))


def _bg(h: str) -> str:
    return "\x1b[48;2;{};{};{}m".format(*hex_to_rgb(h))


RESET = "\x1b[0m"


def anim_enabled(cfg: dict) -> bool:
    if os.environ.get("MYT_NO_ANIMATION") or os.environ.get("NO_COLOR"):
        return False
    return bool(cfg.get("animations", True)) and sys.stdout.isatty()


def cmd_ripple(cfg: dict, args) -> None:
    """A Material 'ripple' that sweeps across a line and settles into a gradient."""
    p = _palette_for_display(cfg)
    width = min(shutil.get_terminal_size((80, 24)).columns - 2 * args.margin, args.width)
    if width <= 4:
        return
    stops = [p["primary"], p["tertiary"], p["secondary"]]
    base = p.get("surface_container_highest", p["surface"])

    def gradient(i: int) -> str:
        x = i / max(1, width - 1) * (len(stops) - 1)
        j = min(int(x), len(stops) - 2)
        return mix(stops[j], stops[j + 1], x - j)

    final = [gradient(i) for i in range(width)]
    glyph = args.glyph
    pad = " " * args.margin
    out = sys.stdout
    if not anim_enabled(cfg):
        out.write(pad + "".join(_fg(c) + glyph for c in final) + RESET + "\n")
        return
    ease = easing("emphasized-decelerate")
    duration = args.duration / 1000
    spread = max(6.0, width / 5)
    glow_color = p.get("on_primary_container", p["primary"])
    out.write("\x1b[?25l")
    try:
        start = time.monotonic()
        while True:
            t = min(1.0, (time.monotonic() - start) / duration)
            front = ease(t) * (width + spread) - spread / 2
            line = []
            for i in range(width):
                d = (i - front) / spread
                settled = max(0.0, min(1.0, 0.5 - d))
                c = mix(base, final[i], settled)
                glow = math.exp(-d * d * 4)
                if glow > 0.02:
                    c = mix(c, glow_color, glow * 0.85)
                line.append(_fg(c) + glyph)
            out.write("\r" + pad + "".join(line) + RESET)
            out.flush()
            if t >= 1:
                break
            time.sleep(1 / 60)
    finally:
        out.write("\r" + pad + "".join(_fg(c) + glyph for c in final) + RESET + "\x1b[?25h\n")
        out.flush()


def cmd_reveal(cfg: dict, args) -> int:
    """Reveals text line by line (a staggered entrance), e.g.

        fastfetch --pipe false | myt reveal
        myt reveal -- some-command args
    """
    cmd = args.command
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if cmd:
        if not anim_enabled(cfg):
            return subprocess.call(cmd)
        proc = subprocess.run(cmd, stdout=subprocess.PIPE)
        data, rc = proc.stdout.decode(errors="replace"), proc.returncode
    else:
        if sys.stdin.isatty():
            raise MytError("usage: <command> | myt reveal   or   myt reveal -- <command>")
        data, rc = sys.stdin.read(), 0
    out = sys.stdout
    if not anim_enabled(cfg):
        out.write(data)
        return rc
    delay = args.stagger / 1000
    lines = data.split("\n")
    out.write("\x1b[?25l")
    try:
        for idx, line in enumerate(lines):
            out.write(line + ("\n" if idx < len(lines) - 1 else ""))
            out.flush()
            if line.strip():
                time.sleep(delay)
    finally:
        out.write("\x1b[?25h")
        out.flush()
    return rc


def cmd_palette(cfg: dict, args) -> None:
    p = _palette_for_display(cfg)
    groups = [
        ("Accent", ["primary", "secondary", "tertiary", "error"]),
        ("Container", ["primary_container", "secondary_container", "tertiary_container", "error_container"]),
        ("Surface", ["surface_container_lowest", "surface_container_low", "surface_container",
                     "surface_container_high", "surface_container_highest"]),
        ("Outline", ["outline", "outline_variant", "on_surface_variant", "on_surface"]),
    ]
    def on(n: str) -> str:
        if "on_" + n in p:
            return p["on_" + n]
        return p["on_surface"] if n.startswith("surface") else p["surface"]

    for title, names in groups:
        print(f"  {_fg(p['on_surface_variant'])}{title}{RESET}")
        line = "  "
        for n in (n for n in names if n in p):
            label = n.replace("surface_container", "sc").replace("_", " ")
            line += f"{_fg(p[n])}\ue0b6{_bg(p[n])}{_fg(on(n))} {label} {RESET}{_fg(p[n])}\ue0b4{RESET} "
        print(line)
    print(f"  {_fg(p['on_surface_variant'])}Terminal{RESET}")
    for row in (range(0, 8), range(8, 16)):
        print("  " + "".join(f"{_bg(p[f'ansi{i}'])}    {RESET}" for i in row))


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def parse_source(value: str) -> dict:
    if value.startswith("#") or HEX_RE.match(value) and not os.path.exists(value):
        return {"color": norm_hex(value)}
    if value.endswith(".json"):
        return {"json": os.path.abspath(os.path.expanduser(value))}
    return {"image": os.path.abspath(os.path.expanduser(value))}


def read_last() -> dict:
    try:
        with open(state_dir() / "last.json") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def ensure_dynamic(cfg: dict) -> Path:
    if not cfg.get("dynamic"):
        raise MytError(
            "runtime theming is off. Set `programs.material-you-terminal.dynamic.enable = true;`\n"
            "or change `source` in your Nix config and rebuild."
        )
    return theme_dir(cfg)


def apply_theme(cfg: dict, source: dict, mode: str, scheme: str, contrast: float,
                animate: bool, quiet: bool) -> dict:
    out = ensure_dynamic(cfg)
    meta = generate(cfg, out, source, mode, scheme, contrast)
    atomic_write(state_dir() / "last.json", json.dumps(
        {"source": source, "mode": mode, "scheme": scheme, "contrast": contrast}, indent=2) + "\n")
    sync_kitty(cfg, out / "kitty.conf", animate=animate, quiet=quiet)
    notify_shells()
    run_hooks(cfg, out, quiet)
    return meta


def run_hooks(cfg: dict, out: Path, quiet: bool) -> None:
    for hook in cfg.get("hooks") or []:
        env = dict(os.environ, MYT_THEME_DIR=str(out), MYT_PALETTE=str(out / "palette.json"))
        r = subprocess.run(hook, shell=True, env=env)
        if r.returncode != 0 and not quiet:
            print(f"myt: hook failed ({r.returncode}): {hook}", file=sys.stderr)


def cmd_apply(cfg: dict, args) -> None:
    last = read_last()
    source = parse_source(args.source) if args.source else last.get("source") or cfg["source"]
    mode = args.mode or last.get("mode") or cfg.get("mode", "dark")
    scheme = args.scheme or last.get("scheme") or cfg.get("scheme", "scheme-tonal-spot")
    contrast = args.contrast if args.contrast is not None else last.get("contrast", cfg.get("contrast", 0.0))
    if args.source and args.scheme is None:
        scheme = cfg.get("scheme", scheme)
    meta = apply_theme(cfg, source, mode, scheme, contrast, not args.no_animate, args.quiet)
    if not args.quiet:
        c = meta["colors"]
        print(f"{_fg(c['primary'])}{_bg(c['primary'])}{_fg(c['on_primary'])} {mode} · "
              f"{scheme.removeprefix('scheme-')} {RESET}{_fg(c['primary'])}{RESET} "
              f"primary {c['primary']}")


def cmd_mode(cfg: dict, args) -> None:
    last = read_last()
    current = last.get("mode") or cfg.get("mode", "dark")
    mode = {"dark": "light", "light": "dark"}[current] if args.mode == "toggle" else args.mode
    args2 = argparse.Namespace(source=None, mode=mode, scheme=None, contrast=None,
                               no_animate=args.no_animate, quiet=args.quiet)
    cmd_apply(cfg, args2)


def cmd_refresh(cfg: dict, args) -> None:
    """Called on home-manager activation: re-render with the current config."""
    out = theme_dir(cfg)
    if cfg.get("dynamic"):
        last = read_last()
        if args.reset or not last:
            seed = Path(cfg["seedDir"])
            out.mkdir(parents=True, exist_ok=True)
            for item in seed.iterdir():
                atomic_write(out / item.name, item.read_text())
            if args.reset:
                try:
                    (state_dir() / "last.json").unlink()
                except FileNotFoundError:
                    pass
        else:
            try:
                generate(cfg, out, last["source"], last.get("mode", cfg.get("mode", "dark")),
                         last.get("scheme", cfg.get("scheme")), last.get("contrast", cfg.get("contrast", 0.0)))
            except MytError as exc:
                if not args.quiet:
                    print(f"myt: {exc}; falling back to the Nix-defined theme", file=sys.stderr)
                for item in Path(cfg["seedDir"]).iterdir():
                    atomic_write(out / item.name, item.read_text())
    if not args.no_kitty:
        sync_kitty(cfg, out / "kitty.conf", animate=not args.no_animate, quiet=args.quiet)
    notify_shells()


def cmd_generate(cfg: dict, args) -> None:
    if args.source:
        source = parse_source(args.source)
    else:
        source = cfg.get("source") or {"color": "#6750a4"}
    generate(cfg, Path(args.out), source, args.mode or cfg.get("mode", "dark"),
             args.scheme or cfg.get("scheme", "scheme-tonal-spot"),
             args.contrast if args.contrast is not None else cfg.get("contrast", 0.0))


def cmd_kitty(cfg: dict, args) -> None:
    n = sync_kitty(cfg, theme_dir(cfg) / "kitty.conf", animate=not args.no_animate, quiet=args.quiet)
    if not args.quiet:
        print(f"myt: updated {n} kitty instance(s)")


def cmd_status(cfg: dict, args) -> None:
    out = theme_dir(cfg)
    last = read_last()
    try:
        meta = json.loads((out / "palette.json").read_text())
    except (OSError, ValueError):
        meta = {}
    info = {
        "version": VERSION,
        "dynamic": bool(cfg.get("dynamic")),
        "themeDir": str(out),
        "mode": meta.get("mode"),
        "scheme": meta.get("scheme"),
        "source": meta.get("source"),
        "lastApplied": last or None,
        "kittySockets": kitty_sockets(cfg),
    }
    if args.json:
        print(json.dumps(info, indent=2))
        return
    for k, v in info.items():
        print(f"{k:>13}: {v}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="myt", description="Material You for kitty, fish, starship & fastfetch")
    ap.add_argument("--config", type=Path, help="config.json (default: $XDG_CONFIG_HOME/material-you-terminal/config.json)")
    ap.add_argument("--version", action="version", version=f"myt {VERSION}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def scheme_opts(p):
        p.add_argument("--mode", choices=["dark", "light"])
        p.add_argument("--scheme", help="matugen scheme, e.g. scheme-tonal-spot, scheme-expressive")
        p.add_argument("--contrast", type=float, help="-1 .. 1")

    p = sub.add_parser("apply", help="re-theme from a wallpaper, a #hex color or a matugen JSON file")
    p.add_argument("source", nargs="?", help="image path, #rrggbb or colors.json (default: last used)")
    scheme_opts(p)
    p.add_argument("--no-animate", action="store_true")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("mode", help="switch between dark and light")
    p.add_argument("mode", choices=["dark", "light", "toggle"])
    p.add_argument("--no-animate", action="store_true")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_mode)

    p = sub.add_parser("refresh", help="re-render after a config change (runs on home-manager switch)")
    p.add_argument("--reset", action="store_true", help="drop the runtime theme, go back to the Nix one")
    p.add_argument("--no-animate", action="store_true")
    p.add_argument("--no-kitty", action="store_true")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_refresh)

    p = sub.add_parser("generate", help="render all templates into a directory")
    p.add_argument("--out", required=True)
    p.add_argument("--source")
    scheme_opts(p)
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("kitty", help="push the current colors into running kitty windows")
    p.add_argument("--no-animate", action="store_true")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_kitty)

    p = sub.add_parser("palette", help="show the current palette")
    p.set_defaults(func=cmd_palette)

    p = sub.add_parser("ripple", help="animated gradient divider")
    p.add_argument("--width", type=int, default=64)
    p.add_argument("--margin", type=int, default=2)
    p.add_argument("--duration", type=int, default=520, help="milliseconds")
    p.add_argument("--glyph", default="━")
    p.set_defaults(func=cmd_ripple)

    p = sub.add_parser("reveal", help="run a command and reveal its output with a staggered animation")
    p.add_argument("--stagger", type=int, default=14, help="milliseconds per line")
    p.add_argument("command", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_reveal)

    p = sub.add_parser("status", help="show what is active")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    args = ap.parse_args(argv)
    try:
        cfg = load_config(args.config)
        rc = args.func(cfg, args)
        return rc if isinstance(rc, int) else 0
    except MytError as exc:
        print(f"myt: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        sys.stdout.write("\x1b[?25h" + RESET)
        return 130


if __name__ == "__main__":
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    sys.exit(main())
