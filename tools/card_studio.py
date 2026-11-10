#!/usr/bin/env python3
"""Preview the complete terminal composition using the production timeline."""
import argparse
from pathlib import Path
import subprocess
import sys
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
import myt
import myt_card as card
from myt_logo import Snowflake, rgb

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, default=Path('logo-preview/card'))
parser.add_argument('--columns', type=int, default=140)
parser.add_argument('--horizontal', choices=['left','center'], default='left')
parser.add_argument('--light', action='store_true')
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=True)
palette = {'primary':'#97ccf8','tertiary':'#e7b9d6','on_surface':'#e7e1eb','surface':'#17151d'}
if args.light:
    palette.update(primary='#345e86',tertiary='#80516f',on_surface='#211e26',surface='#faf7ff')
# Source data is real fastfetch text; no drawing-only imitation of its layout.
data = subprocess.check_output(['fastfetch','--logo','nixos','--pipe','false'],text=True)
box, blank = myt.native_logo_layout(data, 50)
blank, box = card.align_card(blank, box, args.columns, horizontal=args.horizontal)
left, top, width, height = box
area = card.bounds(blank)
assert abs(top+(height-1)/2-(area[1]+area[3])/2) <= .5
font_path = subprocess.check_output(['fc-match','-f','%{file}','RobotoMono Nerd Font'],text=True)
font = ImageFont.truetype(font_path, 14)
cell_x, cell_y = 9, 20
rows = len(blank.splitlines())+2
renderer = Snowflake(palette)

def render(t):
    image = Image.new('RGB',(args.columns*cell_x,rows*cell_y),rgb(palette['surface']))
    draw = ImageDraw.Draw(image)
    text = card.frame(blank,t,palette)
    for y,line in enumerate(text.splitlines()):
        x = 0
        color = palette['on_surface']
        for token in card.TOKEN.findall(line):
            if token.startswith('\x1b['):
                if token.endswith('G'):
                    x = max(0,int(token[2:-1] or '1')-1)
                else:
                    color = card.foreground(token,color,palette)
            else:
                if not token.isspace():
                    if token in '●◉•·':
                        radius = 3 if token in '●◉' else 2 if token == '•' else 1
                        cx, cy = x*cell_x+cell_x/2, y*cell_y+12
                        draw.ellipse((cx-radius,cy-radius,cx+radius,cy+radius),fill=rgb(color))
                    else:
                        draw.text((x*cell_x,y*cell_y),token,font=font,fill=rgb(color))
                x += myt.cell_width(token)
    logo = renderer.frame('intro',t)
    # Kitty fits the square image in its cell placement while preserving aspect.
    side = min(width*cell_x,height*cell_y)
    logo = logo.resize((side,side),Image.Resampling.LANCZOS)
    image.paste(logo,(left*cell_x,top*cell_y),logo.getchannel('A'))
    return image

frames = [render(i/35) for i in range(36)]
frames[0].save(args.out/'entrance.gif',save_all=True,append_images=frames[1:],duration=40,loop=0)
for i,t in enumerate((0,.2,.4,.6,.8,1)):
    render(t).save(args.out/f'frame-{i}.png')
render(1).save(args.out/'final.png')
(args.out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Card Motion Studio</title><style>body{background:'+palette['surface']+';color:'+palette['on_surface']+';font:16px system-ui}img{max-width:100%}</style><h1>Карточка: единая заставка</h1><img src="entrance.gif" alt="Анимация карточки"><p>Ключевые кадры</p>'+''.join(f'<img src="frame-{i}.png" alt="Кадр {i}">' for i in range(6)))
print('PASS: vertical centers differ by at most half a terminal row')
print(args.out.resolve()/'index.html')
