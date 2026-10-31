#!/usr/bin/env python3
"""Render the native house/book app mark reproducibly; no remote imagery or fonts."""
from pathlib import Path
from PIL import Image,ImageDraw

root=Path(__file__).resolve().parents[1]/'static/icons';root.mkdir(parents=True,exist_ok=True)
for size in (192,512):
    scale=size/192
    image=Image.new('RGB',(size,size),'#245e49');draw=ImageDraw.Draw(image)
    def coords(points):return [(round(x*scale),round(y*scale)) for x,y in points]
    draw.line(coords([(43,87),(96,44),(149,87)]),fill='#ffffff',width=round(10*scale),joint='curve')
    draw.line(coords([(53,86),(53,138),(96,148),(139,138),(139,86)]),fill='#ffffff',width=round(8*scale),joint='curve')
    draw.line(coords([(96,92),(96,147)]),fill='#ffffff',width=round(7*scale))
    draw.line(coords([(64,107),(85,112)]),fill='#dce9d8',width=round(5*scale))
    draw.line(coords([(107,112),(128,107)]),fill='#dce9d8',width=round(5*scale))
    image.save(root/('easy-'+str(size)+'.png'))
