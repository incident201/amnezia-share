import base64
import importlib.machinery
import importlib.util
import io
import json
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
    def test_client_cli_separates_peer_name_and_connection_description(self):
        default = amnezia_share.parser().parse_args(["client", "Ipad13"])
        custom = amnezia_share.parser().parse_args(
            ["client", "Ipad13", "--description", "VPS Netherlands"]
        )

        self.assertEqual(default.name, "Ipad13")
        self.assertEqual(default.description, "Amnezia VPS")
        self.assertEqual(custom.name, "Ipad13")
        self.assertEqual(custom.description, "VPS Netherlands")

    def test_create_client_keeps_description_out_of_peer_identity(self):
        info = amnezia_share.ServerInfo(
            container="amnezia-awg2",
            config_text="[Interface]\n",
            interface={},
            version="2",
            vpn_port="55424",
            subnet_address="10.8.1.0",
            subnet_cidr="24",
            server_public_key="server-public",
            psk="preshared",
        )
        table = []
        profile = {"description": "VPS Netherlands"}

        with mock.patch.object(
            amnezia_share, "detect_container", return_value="amnezia-awg2"
        ), mock.patch.object(
            amnezia_share, "parse_server_info", return_value=info
        ), mock.patch.object(
            amnezia_share, "docker_read", return_value="[]"
        ), mock.patch.object(
            amnezia_share, "load_clients_table", return_value=table
        ), mock.patch.object(
            amnezia_share, "official_next_client_ip", return_value="10.8.1.2"
        ), mock.patch.object(
            amnezia_share, "generate_client_keys", return_value=("private", "public")
        ), mock.patch.object(
            amnezia_share, "build_client_profile", return_value=profile
        ) as build_profile, mock.patch.object(
            amnezia_share, "append_peer", return_value="updated config"
        ), mock.patch.object(
            amnezia_share, "transaction_write", return_value=Path("backup")
        ), mock.patch.object(
            amnezia_share, "save_client_profile", return_value=Path("saved")
        ) as save_profile, mock.patch("builtins.print"):
            material = amnezia_share.create_client(
                "Ipad13",
                description="VPS Netherlands",
                host="vpn.example.com",
                dns1="1.1.1.1",
                dns2="1.0.0.1",
                mtu="1280",
            )

        self.assertEqual(table[0]["userData"]["clientName"], "Ipad13")
        self.assertEqual(material.name, "Ipad13")
        self.assertEqual(material.profile["description"], "VPS Netherlands")
        self.assertEqual(build_profile.call_args.kwargs["description"], "VPS Netherlands")
        save_profile.assert_called_once_with(material)

    def test_mtu_validation_matches_official_range(self):
        self.assertEqual(amnezia_share.validate_mtu("576"), "576")
        self.assertEqual(amnezia_share.validate_mtu("1280"), "1280")
        self.assertEqual(amnezia_share.validate_mtu("65535"), "65535")

        for value in ("575", "65536", "invalid", ""):
            with self.subTest(value=value), self.assertRaises(
                amnezia_share.AmneziaShareError
            ):
                amnezia_share.validate_mtu(value)

    def test_invalid_cli_mtu_is_rejected_before_client_creation(self):
        stderr = io.StringIO()
        with mock.patch.object(amnezia_share, "create_client") as create_client, mock.patch(
            "sys.stderr", stderr
        ), self.assertRaises(SystemExit) as raised:
            amnezia_share.main(["client", "phone", "--mtu", "575"])

        self.assertEqual(raised.exception.code, 2)
        create_client.assert_not_called()
        self.assertIn("MTU must be from 576 to 65535", stderr.getvalue())

    def test_qr_profile_carries_mtu_in_amnezia_last_config(self):
        info = amnezia_share.ServerInfo(
            container="amnezia-awg2",
            config_text="[Interface]\n",
            interface={},
            version="2",
            vpn_port="55424",
            subnet_address="10.8.1.0",
            subnet_cidr="24",
            server_public_key="server-public",
            psk="preshared",
        )
        profile = amnezia_share.build_client_profile(
            info,
            description="VPS Netherlands",
            host="vpn.example.com",
            client_ip="10.8.1.2",
            private_key="client-private",
            public_key="client-public",
            dns1="1.1.1.1",
            dns2="1.0.0.1",
            mtu="1280",
        )

        compressed = amnezia_share.qt_compress(amnezia_share.qt_json_bytes(profile))
        decoded_profile = json.loads(amnezia_share.zlib.decompress(compressed[4:]))
        last_config = json.loads(decoded_profile["containers"][0]["awg"]["last_config"])

        self.assertEqual(decoded_profile["description"], "VPS Netherlands")
        self.assertEqual(last_config["mtu"], "1280")

    def test_native_conf_writes_mtu_in_interface(self):
        native = (
            "[Interface]\n"
            "Address = 10.8.1.2/32\n"
            "DNS = $PRIMARY_DNS, $SECONDARY_DNS\n"
            "PrivateKey = private\n\n"
            "[Peer]\n"
            "PublicKey = public\n"
        )
        profile = {
            "dns1": "1.1.1.1",
            "dns2": "1.0.0.1",
            "containers": [
                {
                    "awg": {
                        "last_config": json.dumps({"config": native, "mtu": "1280"})
                    }
                }
            ],
        }

        exported = amnezia_share.native_client_config(profile)
        interface, peer = exported.split("[Peer]", 1)

        self.assertIn("DNS = 1.1.1.1, 1.0.0.1", interface)
        self.assertIn("MTU = 1280", interface)
        self.assertNotIn("MTU", peer)
        self.assertEqual(exported.count("MTU ="), 1)

    def test_native_conf_replaces_existing_mtu_without_duplication(self):
        native = "[Interface]\nAddress = 10.8.1.2/32\nMTU = 1376\nPrivateKey = key\n\n[Peer]\n"
        profile = {
            "containers": [
                {
                    "awg": {
                        "last_config": {
                            "config": native,
                            "mtu": "1280",
                        }
                    }
                }
            ],
        }

        exported = amnezia_share.native_client_config(profile)

        self.assertIn("MTU = 1280", exported)
        self.assertNotIn("MTU = 1376", exported)
        self.assertEqual(exported.count("MTU ="), 1)

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
