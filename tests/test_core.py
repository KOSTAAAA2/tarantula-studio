"""Unit tests for protocol helpers, defaults, config and transport metadata."""
from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

_TMP = tempfile.TemporaryDirectory(prefix="tarantula-core-test-")
os.environ["TARANTULA_STUDIO_CONFIG"] = _TMP.name

from tarantula_studio.core import config as cfg  # noqa: E402
from tarantula_studio.core import defaults, device, keys, mouse  # noqa: E402
from tarantula_studio.core.transport import udev_rule_text  # noqa: E402


class KeyEncodingTest(unittest.TestCase):
    def test_targets_roundtrip(self):
        targets = [
            "controller:a",
            "controller:b",
            "controller:a+b+x",
            "controller:ls_left",
            "key:a",
            "key:left_ctrl+a",
            "key:left_shift+left_ctrl+f1",
            "mouse:left_click",
            "mouse:right_click+scroll_down",
            "media:vol_up",
            "media:play+next",
        ]
        for target in targets:
            with self.subTest(target=target):
                report, code = keys.encode_target(target)
                decoded = keys.decode_target(report, code)
                self.assertIsNotNone(decoded)
                report2, code2 = keys.encode_target(decoded)
                self.assertEqual((report, code), (report2, code2))

    def test_b_remains_button_zero(self):
        report, code = keys.encode_target("controller:b")
        self.assertEqual(code[0], 0)
        self.assertEqual(keys.decode_target(report, code), "controller:b")

    def test_invalid_and_limits(self):
        for target in ("key:not_a_key", "mouse:not_a_button", "media:nope",
                       "controller:a+b+x+y", "key:a+b+x+y", "banana"):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    keys.encode_target(target)

    def test_none_and_reset_are_only_for_mapping_packet(self):
        self.assertEqual(keys.mapping_packet("a", "none")[14:16], keys.REPORT_UNBIND)
        reset = keys.mapping_packet("a", "reset")
        self.assertEqual(reset[10], keys.button_id("a"))
        self.assertEqual(reset[14:16], keys.REPORT_CONTROLLER)


class PacketTest(unittest.TestCase):
    def test_stick_mapping_dpi_is_one_byte_and_unclamped(self):
        for value, expected in ((0, 0), (100, 100), (150, 150), (255, 255),
                                (300, 255), (-5, 0)):
            with self.subTest(value=value):
                packet = keys.set_stick_mapping_packet(
                    1, mode="mouse", dpi_x=value, dpi_y=value)
                self.assertEqual(packet[12], expected)
                self.assertEqual(packet[13], expected)
                self.assertEqual(packet[10], keys.STICK_MODES["mouse"])
                self.assertEqual(len(packet), 32)

    def test_all_packets_have_32_bytes_and_out_header(self):
        packets = [
            keys.set_stick_mapping_packet(0),
            keys.set_stick_curve_packet(0),
            keys.set_trigger_packet(0),
            keys.set_gyro_curve_packet(),
            keys.set_gyro_mapping_packet(),
            keys.set_vibration_packet(10, 20),
            keys.set_light_packet(),
            keys.set_light_color_packet("abxy", [[0, 0, 0]] * 4),
            keys.set_dpad_packet(),
            keys.remap_packet(1, keys.REPORT_KEYBOARD, bytes(16)),
            keys.zone_packet(0x10, "key:a"),
            keys.macro_clear_packet("l4"),
            keys.macro_step_packet("l4", 0, "controller:a", 10, 20),
            keys.state_report_packet(),
        ]
        for packet in packets:
            self.assertEqual(len(packet), 32)
            self.assertEqual(packet[0], 0x07)
            self.assertGreaterEqual(packet[1], 2)

    def test_turbo_encoding(self):
        packet = keys.mapping_packet("l4", "controller:a")
        base = keys.apply_turbo(packet, None, False)
        self.assertEqual(base[11], 0)
        self.assertEqual(base[12], 0)
        low = keys.apply_turbo(packet, 5, True)
        self.assertEqual((low[11], low[12], low[13]), (1, 1, 5))
        mid = keys.apply_turbo(packet, 12)
        self.assertEqual((mid[12], mid[13]), (2, 12))
        high = keys.apply_turbo(packet, 20)
        self.assertEqual((high[12], high[13]), (3, 20))

    def test_macro_step_uses_two_byte_timings(self):
        packet = keys.macro_step_packet("l4", 3, "key:a", 1000, 65535)
        self.assertEqual(packet[4], keys.button_id("l4"))
        self.assertEqual(packet[5], 3)
        self.assertEqual(packet[16:18], (1000).to_bytes(2, "big"))
        self.assertEqual(packet[18:20], (65535).to_bytes(2, "big"))

    def test_zone_packets(self):
        packet = keys.zone_packet(0x10, "key:w")
        self.assertEqual(packet[10], 0x10)
        self.assertEqual(packet[14:16], keys.REPORT_KEYBOARD)
        empty = keys.zone_packet(0x10, "")
        self.assertEqual(empty[14:16], keys.REPORT_UNBIND)


class DefaultsTest(unittest.TestCase):
    def test_factory_defaults_are_complete(self):
        config = defaults.factory_defaults()
        for section in defaults.SECTION_KEYS:
            if section == "advanced":
                continue
            for key in defaults.SECTION_KEYS[section]:
                self.assertIn(key, config)

    def test_deep_merge_keeps_user_values(self):
        config = {"stick_left": {"mouse_dpi": 200}}
        merged = defaults.deep_merge_defaults(copy.deepcopy(config))
        self.assertEqual(merged["stick_left"]["mouse_dpi"], 200)
        self.assertEqual(merged["stick_left"]["mode"], "native")
        self.assertIn("lighting", merged)

    def test_section_changed(self):
        old = defaults.factory_defaults()
        new = copy.deepcopy(old)
        self.assertFalse(defaults.section_changed(old, new, "sticks"))
        new["stick_right"]["mouse_dpi"] = 255
        self.assertTrue(defaults.section_changed(old, new, "sticks"))
        self.assertFalse(defaults.section_changed(old, new, "lighting"))
        new["lighting"]["brightness"] = 99
        self.assertTrue(defaults.section_changed(old, new, "lighting"))


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="tarantula-cfg-"))
        self._old = (cfg.APP_DIR, cfg.CONFIG_FILE, cfg.PROFILES_DIR,
                     cfg.BACKUPS_DIR, cfg.ACTIVE_PROFILE_FILE)
        cfg.APP_DIR = self.dir
        cfg.CONFIG_FILE = self.dir / "config.json"
        cfg.PROFILES_DIR = self.dir / "profiles"
        cfg.BACKUPS_DIR = self.dir / "backups"
        cfg.ACTIVE_PROFILE_FILE = self.dir / "active_profile"

    def tearDown(self):
        (cfg.APP_DIR, cfg.CONFIG_FILE, cfg.PROFILES_DIR,
         cfg.BACKUPS_DIR, cfg.ACTIVE_PROFILE_FILE) = self._old

    def test_roundtrip_and_profile_lifecycle(self):
        config = defaults.factory_defaults()
        config["stick_right"]["mouse_dpi"] = 255
        cfg.save_config(config)
        loaded = cfg.load_config()
        self.assertEqual(loaded["stick_right"]["mouse_dpi"], 255)

        name = cfg.save_profile("Test Profile", loaded)
        self.assertEqual(cfg.get_active_profile(), name)
        self.assertEqual([p["name"] for p in cfg.list_profiles()], [name])
        cfg.save_config(defaults.factory_defaults())
        loaded = cfg.load_profile(name)
        self.assertEqual(loaded["stick_right"]["mouse_dpi"], 255)
        cfg.delete_profile(name)
        self.assertEqual(cfg.list_profiles(), [])
        self.assertIsNone(cfg.get_active_profile())

    def test_invalid_profile_names(self):
        for name in ("", "   ", "../evil", "a/b", "x" * 65):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    cfg.sanitize_profile_name(name)

    def test_backup_roundtrip(self):
        config = defaults.factory_defaults()
        config["rumble"]["left"] = 42
        path = cfg.backup_config(config, "unit test")
        self.assertTrue(path.exists())
        meta = cfg.list_backups()[0]
        self.assertEqual(meta["path"], str(path))
        self.assertEqual(meta["label"], "unit test")
        self.assertEqual(cfg.load_backup(path)["rumble"]["left"], 42)
        cfg.delete_backup(path)
        self.assertFalse(path.exists())

    def test_broken_config_is_quarantined(self):
        cfg.ensure_dirs()
        cfg.CONFIG_FILE.write_text("{broken", encoding="utf-8")
        loaded = cfg.load_config()
        self.assertIn("stick_left", loaded)
        self.assertTrue(cfg.CONFIG_FILE.exists())
        self.assertTrue(cfg.CONFIG_FILE.with_suffix(".broken.json").exists())


class DeviceVerificationTest(unittest.TestCase):
    def test_dpi_clamp_is_reported(self):
        expected = {"mouse_dpi": 255, "mouse_dpi_y": 255}
        actual = {"mouse_dpi": 100, "mouse_dpi_y": 100}
        diffs = []
        device._verify_stick(expected, actual, "right", diffs)
        self.assertEqual(len(diffs), 2)
        self.assertTrue(all("ограничивает DPI" in diff for diff in diffs))

    def test_dpi_above_100_ok(self):
        diffs = []
        device._verify_stick({"mouse_dpi": 150, "mouse_dpi_y": 150},
                             {"mouse_dpi": 150, "mouse_dpi_y": 150},
                             "right", diffs)
        self.assertEqual(diffs, [])

    def test_hsv_tolerance(self):
        diffs = []
        device._compare_hsv("hsv", [[120, 100, 6]], [[121, 100, 6]], diffs)
        self.assertEqual(diffs, [])
        device._compare_hsv("hsv", [[120, 100, 6]], [[130, 100, 6]], diffs)
        self.assertEqual(len(diffs), 1)


class TransportMetadataTest(unittest.TestCase):
    def test_udev_rule_text(self):
        text = udev_rule_text()
        self.assertIn('ATTRS{idVendor}=="3537"', text)
        self.assertIn("hidraw", text)
        self.assertIn("uaccess", text)
        self.assertIn('KERNEL=="uinput"', text)

    def test_mouse_nodes_no_hardware(self):
        self.assertIsInstance(mouse.find_mouse_nodes(), list)

    def test_parser_commands(self):
        from tarantula_studio.cli import build_parser
        parser = build_parser()
        cases = [
            ["doctor"], ["read", "--json"], ["dpi", "255", "--side", "right"],
            ["dpi", "--sweep", "50,100,150,255", "--measure", "2"],
            ["apply", "x.json"], ["restore", "x.json"], ["backup"],
            ["mouse-scan"], ["mouse-test"], ["udev-rule"], ["demo"],
            ["boost", "--factor", "4", "--seconds", "0.1"],
            ["boost", "--target", "1000", "--side", "right"],
            ["gui", "--demo"],
        ]
        for argv in cases:
            with self.subTest(argv=argv):
                args = parser.parse_args(argv)
                self.assertTrue(callable(args.func))


if __name__ == "__main__":
    unittest.main(verbosity=2)
