#!/usr/bin/env python3
"""Curate only the synthetic V4 Prism preview; never reads user/device media."""
from pathlib import Path
from PIL import Image, ImageSequence

ROOT = Path(__file__).resolve().parents[1]

def main():
    source = ROOT / '.build/v4-preview/prism-fixed-audio.gif'
    with Image.open(source) as image:
        frames = [frame.convert('RGB') for frame in ImageSequence.Iterator(image)]
    target = ROOT / 'docs/media/v4-prism.gif'
    target.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(target, save_all=True, append_images=frames[1:],
                   duration=100, loop=0, optimize=True)

if __name__ == '__main__':
    main()
