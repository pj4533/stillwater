#!/usr/bin/env python3
"""Local JSON control client. Send one request on stdin or as an argument."""
import argparse
import json
import socket
import sys
p=argparse.ArgumentParser();p.add_argument('request',nargs='?');p.add_argument('--socket',default='/data/push-ambient/control.sock');a=p.parse_args()
req=json.loads(a.request if a.request else sys.stdin.read())
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(5);s.connect(a.socket);s.sendall((json.dumps(req,allow_nan=False)+'\n').encode());out=b''
while b'\n' not in out:
 data=s.recv(65536)
 if not data:break
 out+=data
s.close();result=json.loads(out);print(json.dumps(result,indent=2));sys.exit(0 if result.get('ok') else 1)
