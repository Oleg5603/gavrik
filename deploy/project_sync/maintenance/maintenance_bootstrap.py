"""Start the singleton maintainer without sharing secrets or blocking bot startup."""
import os
from pathlib import Path
import subprocess
import sys


def ensure_runtime_identity():
    if os.name != 'nt':return
    import ctypes
    buffer=ctypes.create_unicode_buffer(256);size=ctypes.c_ulong(len(buffer))
    if not ctypes.windll.advapi32.GetUserNameW(buffer,ctypes.byref(size)):
        raise RuntimeError('Cannot verify bot runtime identity')
    if buffer.value.casefold() != 'hp':
        raise RuntimeError('Gavrik must be started by the HP user-session watchdog')


def start_maintenance():
    ensure_runtime_identity()
    if os.name=='nt':home=Path(r'C:\Users\HP\gavrik\support\project-sync')
    else:home=Path(__file__).resolve().parent/'support'/'project-sync'
    script=home/'maintainer.py'
    if not script.is_file() or not (home/'policy.json').is_file():return
    subprocess.Popen([sys.executable,str(script),'--home',str(home)],stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),cwd=str(home))


def start_pc_bridge():
    if os.name!='nt':return
    ensure_runtime_identity()
    launcher=Path(r'C:\Users\HP\gavrik\pc_bridge\Start-Bridge-Hidden.vbs')
    if launcher.is_file():
        subprocess.Popen(['wscript.exe',str(launcher)],stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
