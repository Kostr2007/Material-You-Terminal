#!/usr/bin/env python3
"""Test native motion and usable fish input in an isolated, real kitty window.

Requires a graphical session, kitty, fish, fastfetch, xdotool and ImageMagick.
Only the window and socket created by this invocation are controlled or closed.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
from PIL import Image, ImageChops

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out',type=Path,default=Path('logo-preview/kitty-smoke'))
args=parser.parse_args()
args.out.mkdir(parents=True,exist_ok=True)
root=Path(__file__).resolve().parents[1]
env={k:v for k,v in os.environ.items() if k not in ('NO_COLOR','MYT_NO_ANIMATION','TMUX','STY')}
with tempfile.TemporaryDirectory(prefix='myt-kitty-') as tmp:
    tmp=Path(tmp)
    palette={'primary':'#97ccf8','tertiary':'#e7b9d6','on_surface':'#e7e1eb','surface':'#17151d'}
    (tmp/'palette.json').write_text(json.dumps({'colors':palette}))
    (tmp/'config.json').write_text(json.dumps({'themeDir':str(tmp),'logoAnimation':{'backend':'kitty','durationMs':1400,'fps':30}}))
    card=subprocess.check_output(['fastfetch','--logo','nixos','--pipe','false'],env=env)
    (tmp/'card.txt').write_bytes(card)
    socket='unix:'+str(tmp/'control.sock')
    window_class='myt-smoke-'+str(os.getpid())
    cli=' '.join(shlex.quote(str(x)) for x in (sys.executable,root/'cli/myt.py','--config',tmp/'config.json','logo'))
    init=f'function fish_greeting; end; function fish_prompt; printf "MOTION_READY> "; end; cat {shlex.quote(str(tmp/"card.txt"))} | {cli}'
    log=(args.out/'kitty.log').open('w')
    proc=subprocess.Popen(['kitty','--config','NONE','--class',window_class,'--title',window_class,
        '--listen-on',socket,'-o','allow_remote_control=socket-only','-o','font_size=9',
        '-o','shell_integration=disabled','-o','background=#17151d',
        'fish','--no-config','-i','-C',init],env=env,stdout=subprocess.DEVNULL,stderr=log)
    def remote(*parts):
        return subprocess.check_output(['kitty','@','--to',socket,*parts],stderr=subprocess.DEVNULL,text=True,env=env)
    try:
        deadline=time.monotonic()+25
        while True:
            try:
                text=remote('get-text')
                if 'MOTION_READY>' in text:
                    break
            except subprocess.CalledProcessError:
                pass
            if proc.poll() is not None or time.monotonic()>deadline:
                raise RuntimeError('Test terminal did not reach its prompt; inspect kitty.log')
            time.sleep(.1)
        if '▟███' in text or '▜███' in text:
            raise RuntimeError('Native image was not selected (static ASCII logo still present)')
        window=subprocess.check_output(['xdotool','search','--class',window_class],text=True).splitlines()[-1]
        def shot(name):
            p=args.out/name
            subprocess.run(['import','-window',window,str(p)],check=True)
            return Image.open(p).convert('RGB')
        a=shot('idle-a.png')
        time.sleep(.7)
        b=shot('idle-b.png')
        # Exclude the card and prompt cursor: compare only the logo region.
        region=(0,0,min(a.width//3,380),min(350,a.height//2))
        if ImageChops.difference(a.crop(region),b.crop(region)).getbbox() is None:
            raise RuntimeError('Two idle captures are identical; terminal animation may be stopped')
        remote('send-text',"printf 'MOTION_INPUT_OK\\n'\n")
        time.sleep(.3)
        text=remote('get-text')
        if '\nMOTION_INPUT_OK\n' not in text:
            raise RuntimeError('Shell input was not executed correctly')
        shot('after-input.png')
        (args.out/'terminal.txt').write_text(text)
        print('PASS: native loop changes pixels, renderer exits, fish accepts commands')
        print(args.out.resolve())
    finally:
        try:
            remote('close-window')
        except subprocess.CalledProcessError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=5)
        log.close()
