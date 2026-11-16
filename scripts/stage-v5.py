#!/usr/bin/env python3
"""Stage a fresh portable V5 home and complete manifest; never access a device."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',type=Path)
    parser.add_argument('--engine',required=True,type=Path)
    parser.add_argument('--tools',type=Path)
    args=parser.parse_args()
    spec=importlib.util.spec_from_file_location('prepare_home',ROOT/'scripts/prepare-home.py')
    prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)
    argv=['prepare-home',str(args.destination),'--engine',str(args.engine)]
    if args.tools:argv+=['--tools',str(args.tools)]
    sys.argv=argv;prepare.main()
    entries={}
    for path in sorted(args.destination.rglob('*')):
        if path.is_file():
            data=path.read_bytes();entries[str(path.relative_to(args.destination))]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    result={'abi':6,'song_schema':3,'art_version':5,'files':entries}
    (args.destination/'payload-manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(len(entries),'payload files; manifest written')
if __name__=='__main__':main()
