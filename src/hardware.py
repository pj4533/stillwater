"""Direct hardware ownership. Protocol adapted from MIT Push Hack (see NOTICE)."""
import ctypes as C
import fcntl
from pathlib import Path
import re
import struct
import subprocess
from midi import MidiParser

class Display:
    def __init__(self):
        self.fd=None;self.frames=0
        self.libc=C.CDLL(None,use_errno=True);self.libc.ioctl.argtypes=[C.c_int,C.c_ulong,C.c_void_p];self.libc.ioctl.restype=C.c_int
        for d in Path('/sys/bus/usb/devices').iterdir():
            try:
                if (d/'idVendor').read_text().strip()!='2982' or (d/'idProduct').read_text().strip()!='1969':continue
                bus=int((d/'busnum').read_text());dev=int((d/'devnum').read_text())
                self.fd=open('/dev/bus/usb/%03d/%03d'%(bus,dev),'r+b',buffering=0)
                fcntl.ioctl(self.fd,0x8004550F,struct.pack('I',0));break
            except FileNotFoundError:continue
        if not self.fd:raise RuntimeError('Push display not found')
        self.xor=[bytes(v^x for v in range(256)) for x in (0xe7,0xf3,0xe7,0xff)]
    def bulk(self,b):
        data=C.create_string_buffer(b)
        transfer=struct.pack('III4xQ',1,len(b),1000,C.addressof(data))
        request=C.create_string_buffer(transfer)
        n=self.libc.ioctl(self.fd.fileno(),0xc0185502,request)
        if n<0:raise OSError(C.get_errno(),"USB display transfer")
        if n!=len(b):raise IOError('short display transfer')
    def send(self,frame):
        wire=bytearray(frame)
        for i in range(4):wire[i::4]=frame[i::4].translate(self.xor[i])
        self.bulk(bytes([255,204,170,136])+bytes(12));self.bulk(bytes(wire));self.bulk(bytes(wire));self.frames+=1
    def close(self):
        if self.fd:
            fcntl.ioctl(self.fd,0x80045510,struct.pack('I',0));self.fd.close();self.fd=None

class Midi:
    def __init__(self,tap=None):
        text=subprocess.check_output(['amidi','-l'],text=True)
        port=next((re.search(r'hw:\S+',line).group() for line in text.splitlines() if 'Live Port' in line),None)
        if not port:raise RuntimeError('named Ableton Push 3 Live Port not found')
        self.port=port;self.lib=C.CDLL('libasound.so.2');self.input=C.c_void_p();self.output=C.c_void_p()
        self.lib.snd_rawmidi_open.argtypes=[C.POINTER(C.c_void_p),C.POINTER(C.c_void_p),C.c_char_p,C.c_int]
        self.lib.snd_rawmidi_read.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t];self.lib.snd_rawmidi_read.restype=C.c_long
        self.lib.snd_rawmidi_write.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t];self.lib.snd_rawmidi_write.restype=C.c_long
        e=self.lib.snd_rawmidi_open(C.byref(self.input),C.byref(self.output),port.encode(),2)
        if e<0:raise RuntimeError('MIDI open failed: %d'%e)
        self.buf=C.create_string_buffer(4096);self.parser=MidiParser(tap);self.events=0;self.outgoing=bytearray()
    def flush(self):
        if not self.outgoing:return
        b=bytes(self.outgoing);n=self.lib.snd_rawmidi_write(self.output,b,len(b))
        if n<0 and n!=-11:raise IOError('MIDI write %d'%n)
        if n>0:del self.outgoing[:n]
    def write(self,data):
        b=bytes(data);self.flush()
        if len(self.outgoing)+len(b)>1024:return False
        self.outgoing.extend(b);self.flush();return True
    def cc(self,num,value):return self.write([0xb0,num,value])
    def note(self,num,value):return self.write([0x90,num,value])
    def read(self):
        self.flush()
        n=self.lib.snd_rawmidi_read(self.input,self.buf,4096);events=[]
        if n<0 and n!=-11:raise IOError('MIDI read %d'%n)
        events=self.parser.feed(self.buf.raw[:max(0,n)])
        self.events+=len(events);return events
    def close(self):
        for h in (self.input,self.output):self.lib.snd_rawmidi_close(h)
