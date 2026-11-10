"""Exercise real pipe and pseudo-terminal behavior, including interruption."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import pty
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest

CLI = Path(__file__).resolve().parents[1] / "cli/myt.py"
spec = importlib.util.spec_from_file_location("myt", CLI)
myt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(myt)
CARD = "\x1b[1m\x1b[31m  ▟███▛    host@example\x1b[0m\n  ▜███▙    OS: NixOS\n"


class LogoHarness:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "palette.json").write_text(json.dumps({"colors": {
            "primary": "#97ccf8", "tertiary": "#e7b9d6",
            "surface": "#202020", "on_surface": "#f0f0f0",
        }}))
        self.config = root / "config.json"
        self.config.write_text(json.dumps({"themeDir": str(root), "logoAnimation": {"fps": 60}}))
        self.env = {**os.environ, "TERM": "xterm-kitty"}
        for key in ("NO_COLOR", "MYT_NO_ANIMATION", "KITTY_WINDOW_ID", "TMUX", "STY"):
            self.env.pop(key, None)

    def launch(self, rows=30, columns=100, duration=70, extra_env=None, data=CARD):
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))
        proc = subprocess.Popen([sys.executable, str(CLI), "--config", str(self.config),
                                 "logo", "--duration", str(duration)],
                                stdin=subprocess.PIPE, stdout=slave, stderr=subprocess.PIPE,
                                env={**self.env, **(extra_env or {})})
        os.close(slave)
        proc.stdin.write(data.encode())
        proc.stdin.close()
        self.addCleanup(os.close, master)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        return proc, master

    def collect(self, proc, master):
        chunks = []
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.1)[0]:
                try:
                    chunks.append(os.read(master, 65536))
                except OSError:
                    break
            elif proc.poll() is not None:
                break
        proc.wait(timeout=2)
        error = proc.stderr.read().decode()
        proc.stderr.close()
        self.assertEqual(error, "")
        return b"".join(chunks).decode().replace("\r\n", "\n")


class LogoTests(LogoHarness, unittest.TestCase):
    def test_pipe_is_exact_passthrough_without_palette(self):
        self.config.write_text("{}")
        result = subprocess.run([sys.executable, str(CLI), "--config", str(self.config), "logo"],
                                input=CARD, text=True, capture_output=True, env=self.env)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, CARD)

    def test_animated_terminal_keeps_card_and_finishes_with_original(self):
        proc, master = self.launch()
        out = self.collect(proc, master)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("\x1b[?25l", out)
        self.assertIn("\x1b[2A", out)
        self.assertGreater(out.count("host@example"), 1)
        self.assertTrue(out.endswith(CARD + myt.RESET + "\x1b[?25h"))

    def test_disabled_and_small_terminal_never_move_cursor(self):
        for kwargs in ({"rows": 2}, {"columns": 10}, {"duration": 0},
                       {"extra_env": {"NO_COLOR": "1"}},
                       {"extra_env": {"MYT_NO_ANIMATION": "1"}},
                       {"extra_env": {"TERM": "dumb"}},
                       {"data": "no logo here\n"}):
            with self.subTest(kwargs=kwargs):
                proc, master = self.launch(**kwargs)
                self.assertEqual(self.collect(proc, master), kwargs.get("data", CARD))
                self.assertEqual(proc.returncode, 0)

    def test_interrupt_restores_cursor_and_final_card(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signal=sig):
                proc, master = self.launch(duration=5000)
                self.assertTrue(select.select([master], [], [], 3)[0])
                first = os.read(master, 65536).decode().replace("\r\n", "\n")
                self.assertIn("\x1b[?25l", first)
                proc.send_signal(sig)
                out = first + self.collect(proc, master)
                self.assertEqual(proc.returncode, 130)
                self.assertIn(CARD, out)
                self.assertTrue(out.endswith("\x1b[?25h" + myt.RESET))

    def test_resize_stops_without_rewinding_reflowed_rows(self):
        proc, master = self.launch(duration=5000)
        self.assertTrue(select.select([master], [], [], 3)[0])
        os.read(master, 65536)
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 10, 20, 0, 0))
        out = self.collect(proc, master)
        self.assertEqual(proc.returncode, 0)
        self.assertIn(CARD, out)
        self.assertTrue(out.endswith(myt.RESET + "\x1b[?25h"))

    def test_runtime_config_disables_animation(self):
        for config in ({"animations": False}, {"logoAnimation": {"enable": False}}):
            with self.subTest(config=config):
                self.config.write_text(json.dumps(config))
                proc, master = self.launch()
                self.assertEqual(self.collect(proc, master), CARD)

    def test_fastfetch_horizontal_column_escape(self):
        card = CARD.replace("host@example", "\x1b[20Ghost@example")
        proc, master = self.launch(data=card)
        out = self.collect(proc, master)
        self.assertIn("\x1b[?25l", out)
        self.assertTrue(out.endswith(card + myt.RESET + "\x1b[?25h"))
        self.assertEqual(myt.cell_width("\x1b[10Ghi"), 11)
        self.assertEqual(myt.cell_width("123\x1b[2Gx"), 3)

    def test_width_and_styles(self):
        self.assertEqual(myt.cell_width("\x1b[31m世界e\u0301\x1b[0m"), 5)
        palette = {"primary": "#97ccf8", "tertiary": "#e7b9d6",
                   "surface_container_highest": "#202020", "on_surface": "#f0f0f0"}
        frame = myt.logo_frame(CARD, palette, 0.5, 9)
        self.assertIn("\x1b[0m\x1b[1m\x1b[31m", frame)
        self.assertIn("    host@example\x1b[0m", frame)


if __name__ == "__main__":
    unittest.main()
