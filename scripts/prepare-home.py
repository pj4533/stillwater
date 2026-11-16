#!/usr/bin/env python3
"""Build a fresh runtime payload; never merge into an existing instrument home."""
import argparse
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',type=Path)
    parser.add_argument('--engine',required=True,type=Path)
    parser.add_argument('--tools',type=Path,help='Staged encoder directory; omitted for no-film entry smoke')
    args=parser.parse_args()
    if args.destination.exists():parser.error('Destination exists; choose a new empty path')
    if not args.engine.is_file():parser.error('Build the selected native engine first')
    if args.tools and any(not (args.tools/name).is_file() for name in ('ffmpeg','ffprobe','LICENSE.txt','provenance.json')):
        parser.error('tools must contain verified ffmpeg, ffprobe, LICENSE.txt and provenance.json')
    destination=args.destination.resolve()
    # Prevent recursive copies if the destination is under a source tree.
    if any(destination.is_relative_to(ROOT/name) for name in ('src','scripts','assets')):
        parser.error('Destination must be outside the source trees')
    destination.mkdir(parents=True)
    for name in ('src','scripts','assets'):
        shutil.copytree(ROOT/name,destination/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copyfile(args.engine,destination/'engine.so')
    if args.tools:
        (destination/'tools').mkdir()
        for name in ('ffmpeg','ffprobe','LICENSE.txt','provenance.json'):
            shutil.copy2(args.tools/name,destination/'tools'/name)
    print('Prepared fresh payload:',destination)

if __name__=='__main__':main()
