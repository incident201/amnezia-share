import base64
import importlib.machinery
import importlib.util
import io
import os
from pathlib import Path
import struct
import sys
import types
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "amnezia-share"

# ``pwd`` is Unix-only, while these pure terminal/format tests are also useful
# to contributors running them on Windows.
try:
    import pwd  # noqa: F401
except ModuleNotFoundError:
    sys.modules["pwd"] = types.ModuleType("pwd")

loader = importlib.machinery.SourceFileLoader("amnezia_share", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
amnezia_share = importlib.util.module_from_spec(spec)
sys.modules[loader.name] = amnezia_share
loader.exec_module(amnezia_share)


class TTYBuffer(io.StringIO):
    def isatty(self):
        return True


class TerminalQrTests(unittest.TestCase):
    def test_qr_payload_framing_remains_amnezia_compatible(self):
        data = b"0123456789ABC"
        payloads = amnezia_share.qr_payloads(data, 5)

        self.assertEqual(len(payloads), 3)
        restored = bytearray()
        for expected_index, encoded in enumerate(payloads):
            raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            magic, count, index, length = struct.unpack(">hBBI", raw[:8])
            self.assertEqual((magic, count, index), (1984, 3, expected_index))
            self.assertEqual(length, len(raw[8:]))
            restored.extend(raw[8:])
        self.assertEqual(bytes(restored), data)

    def test_auto_chunk_targets_78_percent_and_accepts_more_frames(self):
        data = b"x" * 1600

        def fake_render(payload, qr_type, margin):
            raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
            chunk_length = len(raw) - 8
            width = 20 + chunk_length // 10
            height = 10 + chunk_length // 20
            return "\n".join("#" * width for _ in range(height))

        with mock.patch.object(
            amnezia_share.shutil,
            "get_terminal_size",
            return_value=os.terminal_size((100, 50)),
        ), mock.patch.object(amnezia_share, "render_qr", side_effect=fake_render):
            size, dimensions = amnezia_share.choose_chunk_size(
                data, "auto", "ANSIUTF8", 1
            )

        self.assertEqual(size, 589)
        self.assertLessEqual(dimensions[0], 78)
        self.assertLessEqual(dimensions[1], 39)
        self.assertEqual(len(amnezia_share.qr_payloads(data, size)), 3)

    def test_frame_has_padding_and_stop_hint_below_qr(self):
        frame = amnezia_share.dynamic_qr_frame(
            "AA\nBB\n",
            title="Amnezia client access: phone",
            index=1,
            count=3,
            terminal_width=80,
        )

        self.assertEqual(
            frame.splitlines(),
            [
                "    Amnezia client access: phone",
                "    Frame 2/3",
                "",
                "    AA",
                "    BB",
                "",
                "    Ctrl+C to stop",
            ],
        )
        self.assertFalse(frame.endswith("\n"))

    def test_render_keeps_qrencode_margin(self):
        result = types.SimpleNamespace(returncode=0, stdout="QR", stderr="")
        with mock.patch.object(amnezia_share, "require_binary"), mock.patch.object(
            amnezia_share, "run", return_value=result
        ) as run:
            amnezia_share.render_qr("payload", margin=1)

        command = run.call_args.args[0]
        self.assertEqual(command[command.index("-m") + 1], "1")

    def test_redraw_uses_alternate_screen_and_restores_it(self):
        output = TTYBuffer()
        with mock.patch.object(amnezia_share.sys, "stdout", output), mock.patch.object(
            amnezia_share, "choose_chunk_size", return_value=(500, (2, 2))
        ), mock.patch.object(
            amnezia_share, "qr_payloads", return_value=["one", "two", "three"]
        ), mock.patch.object(
            amnezia_share, "render_qr", return_value="##\n##\n"
        ), mock.patch.object(
            amnezia_share.shutil,
            "get_terminal_size",
            return_value=os.terminal_size((80, 40)),
        ), mock.patch.object(
            amnezia_share.time, "sleep", side_effect=KeyboardInterrupt
        ):
            amnezia_share.show_dynamic_qr({}, title="Amnezia client access: phone")

        written = output.getvalue()
        self.assertIn("\033[?1049h\033[?25l", written)
        self.assertIn("\033[2J\033[H", written)
        self.assertIn("\033[?1049l", written)
        self.assertLess(written.index("    ##"), written.index("    Ctrl+C to stop"))


if __name__ == "__main__":
    unittest.main()
