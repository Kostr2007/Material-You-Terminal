#!/usr/bin/env python3
"""Generate SVG and supersampled alpha mask from canonical NixOS geometry.

Geometry adapted from NixOS/branding nixoslogo/logomark.py at 09acff8d0a6cfd45112e6d2ccbfe80b86764901f.
See cli/assets/ATTRIBUTION.md for code and artwork attribution.
"""
import math
from pathlib import Path
from PIL import Image, ImageDraw


def polygons():
    # A lambda on a regular unit hexagon, thickness 1/4, separation 1/32.
    h = math.sqrt(3) / 2
    thickness = 1/4
    gap = 1/32
    v0 = (thickness, 0)
    v60 = (thickness/2, thickness*h)
    v300 = (thickness/2, -thickness*h)
    g = (gap, -2*gap*h)
    p = [(-.5-v60[0]+g[0], h-v60[1]+g[1]),
         (-.5+v60[0]+g[0], h+v60[1]+g[1]),
         (.5+v0[0], -h), (.5-v0[0], -h),
         (0, -math.sqrt(3)*thickness),
         (-.5+v0[0], -h), (-.5, -h),
         (-.5-v300[0], -h-v300[1]), (-v0[0], 0)]
    # Translate upper apex (without gap) to the join, then rotate six copies.
    p = [(x + .5-thickness/2-1, -y+h+thickness*h) for x,y in p]
    result = []
    for index in range(6):
        a = math.tau*index/6
        result.append([(x*math.cos(a)-y*math.sin(a), x*math.sin(a)+y*math.cos(a)) for x,y in p])
    return result


if __name__ == '__main__':
    root=Path(__file__).resolve().parents[1]/'cli/assets'
    points=polygons()
    radius=max(math.hypot(x,y) for polygon in points for x,y in polygon)
    # Preserve whitespace for glow and motion; the logo itself is centered.
    normalized=[[(384+x/radius*345,384+y/radius*345) for x,y in polygon] for polygon in points]
    mask=Image.new('L',(768,768))
    draw=ImageDraw.Draw(mask)
    for polygon in normalized:
        draw.polygon(polygon,fill=255)
    mask.save(root/'nix-mask.png')
    svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 768 768">\n'
    svg+='<!-- NixOS Logo, CC BY 4.0; see ATTRIBUTION.md. Geometry from NixOS/branding. -->\n'
    for polygon in normalized:
        svg+='<polygon fill="white" points="'+' '.join(f'{x:.6f},{y:.6f}' for x,y in polygon)+'"/>\n'
    svg+='</svg>\n'
    (root/'nix-snowflake.svg').write_text(svg)
