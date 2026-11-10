"""Native protocol, motion geometry, lifecycle and bounded resource tests."""
import base64
import io
import json
import os
from pathlib import Path
import re
import select
import signal
import sys
import tempfile
import time
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
from PIL import ImageChops
import myt_logo as motion
from test_logo import LogoHarness, CARD

PALETTE = {'primary':'#97ccf8','tertiary':'#e7b9d6','on_surface':'#e7e1eb','surface':'#17151d'}


def packets(data):
    return re.findall(r'\x1b_G([^\x1b]*)\x1b\\', data)


class MotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.renderer = motion.Snowflake(PALETTE)

    def test_exact_idle_seam_and_intro_handoff(self):
        first = self.renderer.frame('idle', 0)
        self.assertIsNone(ImageChops.difference(first, self.renderer.frame('idle', 1)).getbbox(alpha_only=False))
        self.assertIsNone(ImageChops.difference(first, self.renderer.frame('intro', 1)).getbbox(alpha_only=False))

    def test_growth_center_and_transparent_margin(self):
        early = self.renderer.frame('intro', 0).getchannel('A').getbbox()
        late = self.renderer.frame('intro', 1).getchannel('A').getbbox()
        self.assertLess(early[2]-early[0], (late[2]-late[0]) / 4)
        self.assertAlmostEqual((late[0]+late[2])/2, motion.SIZE/2, delta=3)
        self.assertAlmostEqual((late[1]+late[3])/2, motion.SIZE/2, delta=3)
        self.assertGreater(late[0], 0)
        self.assertLess(late[2], motion.SIZE)
        self.assertNotEqual(self.renderer.frame('idle', 0).tobytes(), self.renderer.frame('idle', .25).tobytes())

    def test_chunk_size_and_animation_action_on_every_chunk(self):
        payload = os.urandom(15000)
        parts = packets(motion.command('a=f,i=123,q=2', payload))
        self.assertGreater(len(parts), 2)
        self.assertTrue(all(p.startswith('a=f,') for p in parts))
        self.assertTrue(all(len(p.split(';')[1]) <= 4096 for p in parts))
        self.assertIn('m=0;', parts[-1])
        self.assertEqual(base64.b64decode(''.join(p.split(';')[1] for p in parts)), payload)

    def test_resource_bounds_and_full_replacement(self):
        self.assertEqual(motion.frame_counts({'fps':60,'durationMs':5000,'idlePeriodMs':12000}), (90,96))
        frames = motion.encoded_frames(self.renderer, 'idle', 2)
        self.assertEqual(len(zlib.decompress(frames[0])), motion.SIZE*motion.SIZE*4)
        data = motion.upload(frames, 42, 40, 20, 50)
        self.assertIn('a=f,f=32,o=z', data)
        self.assertIn('X=1,z=50', data)
        self.assertIn('C=1', data)

    def test_resize_deletes_only_own_images_and_restores_card(self):
        out = io.StringIO()
        result = motion.play(out, PALETTE, {'fps':1,'durationMs':10,'idle':False},
                             (2,0,8,2), 2, 'blank\n\n', CARD, (100,30), lambda:(80,20))
        self.assertFalse(result)
        self.assertIn('a=d,d=I,i=', out.getvalue())
        self.assertNotIn('a=d,d=A', out.getvalue())
        self.assertTrue(out.getvalue().endswith(CARD))


class NativeLifecycleTests(LogoHarness, unittest.TestCase):
    # Use a real pipe into a terminal, then verify the renderer process exits.
    def test_native_exits_with_terminal_owned_infinite_loop(self):
        config = json.loads(self.config.read_text())
        config['logoAnimation'].update(backend='kitty', fps=2, idlePeriodMs=1000)
        self.config.write_text(json.dumps(config))
        proc, master = self.launch(duration=30)
        out = self.collect(proc, master)
        self.assertEqual(proc.returncode, 0)
        self.assertIn('s=2,c=1,q=2', out)
        self.assertIn('s=3,v=1,c=1,q=2', out)
        self.assertIn('host@example', out)
        self.assertTrue(out.endswith('\x1b[0m\x1b[?25h'))
        # There is no subprocess remaining to write into the prompt.
        self.assertIsNotNone(proc.poll())

    def test_native_sigterm_cleans_up_and_restores_card(self):
        config = json.loads(self.config.read_text())
        config['logoAnimation'].update(backend='kitty', fps=2, idle=False)
        self.config.write_text(json.dumps(config))
        proc, master = self.launch(duration=5000)
        first = b''
        deadline = time.monotonic() + 5
        while b's=2,c=1,q=2' not in first and time.monotonic() < deadline:
            if select.select([master], [], [], .1)[0]:
                first += os.read(master, 65536)
        self.assertIn(b's=2,c=1,q=2', first)
        proc.send_signal(signal.SIGTERM)
        out = first.decode().replace('\r\n', '\n') + self.collect(proc, master)
        self.assertEqual(proc.returncode, 130)
        self.assertIn('a=d,d=I,i=', out)
        self.assertIn(CARD, out)
        self.assertTrue(out.endswith('\x1b[?25h' + '\x1b[0m'))
