"""Text-preserving choreography and alignment for the fastfetch card.

Only the bounded entrance rewrites text. At handoff, every original SGR color,
label and value is restored; the terminal-owned logo is the only idle animation.
"""
import unicodedata
import re

TOKEN = re.compile(r"\x1b\[[0-9;:]*m|\x1b\[[0-9]*G|[^\x1b]", re.DOTALL)
RESET = "\x1b[0m"


def cells(line):
    x = 0
    for token in TOKEN.findall(line):
        if token.startswith("\x1b["):
            if token.endswith("G"):
                x = max(0, int(token[2:-1] or "1") - 1)
        else:
            yield x, token
            x += (0 if unicodedata.combining(token) else
                  2 if unicodedata.east_asian_width(token) in ("W", "F") else 1)


def bounds(data):
    points = [(x, y) for y, line in enumerate(data.splitlines())
              for x, char in cells(line) if not char.isspace()]
    if not points:
        return None
    return min(x for x,y in points), min(y for x,y in points), max(x for x,y in points), max(y for x,y in points)


def align_card(blank, box, columns, vertical="center", horizontal="left"):
    """Balance text and image centers without shrinking the snowflake."""
    area = bounds(blank)
    if not area:
        return blank, box
    left, top, width, height = box
    card_left, card_top, card_right, card_bottom = area
    shift_y = 0
    if vertical == "center":
        center = (card_top + card_bottom) / 2
        top = max(0, round(center - (height - 1) / 2))
        shift_y = round(top + (height - 1) / 2 - center)
    lines = blank.splitlines()
    total = max(len(lines), top + height, card_bottom + shift_y + 1)
    moved = [""] * total
    for y, line in enumerate(lines):
        if any(not char.isspace() for x, char in cells(line)):
            moved[y + shift_y] = line
    # Center the combined logo + text footprint, including its existing gap.
    visible_left = min(left, card_left)
    visible_right = max(left + width - 1, card_right)
    shift_x = max(0, (columns - (visible_right-visible_left+1)) // 2 - visible_left) if horizontal == "center" else 0
    if shift_x:
        def relocate(match):
            return f"\x1b[{int(match.group(1) or '1')+shift_x}G"
        moved = [" "*shift_x + re.sub(r"\x1b\[([0-9]*)G", relocate, line) if line else "" for line in moved]
    return "\n".join(moved) + "\n", (left+shift_x, top, width, height)


def foreground(token, previous, palette):
    codes = [int(v or 0) for v in token[2:-1].replace(':',';').split(';')]
    i = 0
    while i < len(codes):
        code = codes[i]
        if code in (0, 39):
            previous = palette['on_surface']
        elif code in (38, 48) and codes[i+1:i+2] == [2] and len(codes) >= i+5:
            if code == 38:
                previous = '#%02x%02x%02x' % tuple(codes[i+2:i+5])
            i += 4
        elif code in (38, 48) and codes[i+1:i+2] == [5] and len(codes) >= i+3:
            if code == 38:
                index = codes[i+2]
                defaults = ('#000000','#cd0000','#00cd00','#cdcd00','#0000ee','#cd00cd','#00cdcd','#e5e5e5',
                            '#7f7f7f','#ff0000','#00ff00','#ffff00','#5c5cff','#ff00ff','#00ffff','#ffffff')
                if index < 16:
                    previous = palette.get(f'ansi{index}', defaults[index])
                elif index < 232:
                    value = index-16
                    cube = (0,95,135,175,215,255)
                    previous = '#%02x%02x%02x' % (cube[value//36],cube[value//6%6],cube[value%6])
                else:
                    previous = '#%02x%02x%02x' % ((8+10*(index-232),)*3)
            i += 2
        elif 30 <= code <= 37 or 90 <= code <= 97:
            index = code-30 if code < 90 else code-90+8
            previous = palette.get(f'ansi{index}', previous)
        i += 1
    return previous


def blend(a, b, t):
    aa, bb = bytes.fromhex(a.lstrip('#')), bytes.fromhex(b.lstrip('#'))
    values = [round((x*x*(1-t) + y*y*t)**.5) for x,y in zip(aa,bb)]
    return '\x1b[38;2;%d;%d;%dm' % tuple(values)


def frame(data, progress, palette):
    """Cascade header/rows, draw separators and bars, then pop palette swatches."""
    if progress >= 1:
        return data
    area = bounds(data)
    if not area:
        return data
    left, top, right, bottom = area
    active = [y for y,line in enumerate(data.splitlines()) if any(not c.isspace() for x,c in cells(line))]
    order = {y:i for i,y in enumerate(active)}
    result = []
    background = palette.get('surface', '#17151d')
    for y,line in enumerate(data.splitlines()):
        style = ''
        color = palette['on_surface']
        row = order.get(y, 0)
        start = .05 + .32 * row / max(1,len(active)-1)
        t = max(0, min(1, (progress-start)/.5))
        eased = 1 - (1-t)**3
        swatch = 0
        x = 0
        rendered = []
        for token in TOKEN.findall(line):
            if token.startswith('\x1b['):
                if token.endswith('G'):
                    x = max(0, int(token[2:-1] or '1')-1)
                else:
                    color = foreground(token, color, palette)
                    style = token if token in ('\x1b[m','\x1b[0m') else style+token
                rendered.append(token)
                continue
            glyph = token
            opacity = eased
            if token in '─━':
                # Draw bars and divider from left to right while keeping cells fixed.
                opacity *= max(0, min(1, (eased*1.18-(x-left)/max(1,right-left)) * 7))
            elif token in '●◉':
                local = max(0,min(1,(progress-.45-swatch*.012)/.28))
                glyph = '·' if local < .25 else '•' if local < .65 else token
                opacity = 1-(1-local)**3
                swatch += 1
            if not token.isspace():
                rendered.append(blend(background, color, opacity)+glyph+RESET+style)
            else:
                rendered.append(token)
            x += 0 if unicodedata.combining(token) else 2 if unicodedata.east_asian_width(token) in ('W','F') else 1
        result.append(''.join(rendered))
    return '\n'.join(result)+'\n'
