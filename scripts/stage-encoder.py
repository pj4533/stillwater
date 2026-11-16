#!/usr/bin/env python3
"""Stage, never install/run, the pinned x86_64 GPL encoder for rollout review."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import urllib.request
ROOT=Path(__file__).resolve().parents[1]
URL='https://github.com/FFmpeg-Builds/FFmpeg-Builds/releases/download/autobuild-2026-11-15-12-40/ffmpeg-n8.1.3-35-gf1acb0a266-linux64-gpl-8.1.tar.xz'
DIGEST='94879ca4e4d17aae5e6a30d0de16ba765df708572e4ce3f6c2623a48405be917'
PREFIX='ffmpeg-n8.1.3-35-gf1acb0a266-linux64-gpl-8.1'

def main():
    cache=ROOT/'.build/tools';cache.mkdir(parents=True,exist_ok=True);archive=cache/'ffmpeg.tar.xz'
    if not archive.exists():
        with urllib.request.urlopen(URL,timeout=60) as response,archive.with_suffix('.download').open('wb') as stream:shutil.copyfileobj(response,stream,1024*1024)
        archive.with_suffix('.download').replace(archive)
    digest=hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()
    if digest!=DIGEST or archive.stat().st_size!=151596896:raise ValueError('Pinned archive hash/size mismatch')
    selected={PREFIX+'/bin/ffmpeg':'ffmpeg',PREFIX+'/bin/ffprobe':'ffprobe',PREFIX+'/LICENSE.txt':'LICENSE.txt'}
    with tarfile.open(archive) as source:
        members=source.getmembers()
        for entry in members:
            path=PurePosixPath(entry.name)
            if path.is_absolute() or '..' in path.parts or path.parts[0]!=PREFIX or not (entry.isdir() or entry.isfile()):raise ValueError('Unsafe archive path/type: '+entry.name)
        for entry in members:
            if entry.name in selected:
                target=cache/selected[entry.name]
                with source.extractfile(entry) as src,target.open('wb') as dst:shutil.copyfileobj(src,dst,1024*1024)
                target.chmod(0o755 if selected[entry.name] in ('ffmpeg','ffprobe') else 0o644)
    report=dict(url=URL,sha256=digest,size=archive.stat().st_size,all_archive_paths_validated=True,executed=False,device_tested=False,binaries={})
    for binary in ('ffmpeg','ffprobe'):
        path=cache/binary
        report['binaries'][binary]=dict(sha256=hashlib.file_digest(path.open('rb'),'sha256').hexdigest(),elf=subprocess.check_output(['readelf','-l','-d','-V',str(path)],text=True))
    (cache/'provenance.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Staged verified archive, ffmpeg, ffprobe, GPL license and ELF provenance:',cache)
if __name__=='__main__':main()
