"""Super Nova / T4 Nova Pro protocol, read, write and rollback tests."""
from __future__ import annotations

import copy
import unittest

from tarantula_studio.core import supernova as sn
from tests.fake_device import FakeTarantula
from tests.fake_supernova import FakeSuperNova, VIBRATION


class SuperNovaReadTest(unittest.TestCase):
    def setUp(self):
        self.sim = FakeSuperNova()
        self.addCleanup(self.sim.stop)
        self.dev = self.sim.device

    def test_probe_requires_device_type_3(self):
        self.assertTrue(sn.probe(self.dev))
        other = FakeSuperNova(device_type=1)
        self.addCleanup(other.stop)
        self.assertFalse(sn.probe(other.device))

    def test_t3_pro_probe_is_rejected(self):
        t3 = FakeTarantula()
        self.addCleanup(t3.stop)
        self.assertFalse(sn.probe(t3.device))

    def test_read_info_and_battery(self):
        info = sn.read_info(self.dev)
        self.assertEqual(info["device_type"], 3)
        self.assertEqual(info["firmware"], "1.0.6")
        self.assertEqual(info["mac"], "aa:bb:cc:dd:ee:ff")
        self.assertEqual(info["battery"], 87)
        self.assertFalse(info["charging"])

    def test_charging_battery(self):
        charged = FakeSuperNova(charging=True)
        self.addCleanup(charged.stop)
        info = sn.read_info(charged.device)
        self.assertIsNone(info["battery"])
        self.assertTrue(info["charging"])
        self.assertEqual(info["battery_raw"], 0xFF)

    def test_read_config_factory(self):
        config = sn.read_config(self.dev)
        self.assertEqual(config["remaps"], {})
        self.assertEqual(config["vibration"], {"left": 75, "right": 75})
        self.assertEqual(config["stick_left"],
                         {"deadzone_min": 5, "deadzone_max": 100})
        self.assertEqual(config["trigger_right"],
                         {"deadzone_min": 5, "deadzone_max": 95})

    def test_read_detects_existing_remap(self):
        self.sim.keys[0x01] = bytearray(
            sn.with_key_target(bytes(self.sim.keys[0x01]), 0x00))
        config = sn.read_config(self.dev)
        self.assertEqual(config["remaps"], {"A": "B"})

    def test_refuses_non_supernova_read(self):
        other = FakeSuperNova(device_type=1)
        self.addCleanup(other.stop)
        with self.assertRaises(sn.SuperNovaError):
            sn.read_config(other.device)

    def test_apply_refuses_non_supernova(self):
        other = FakeSuperNova(device_type=1)
        self.addCleanup(other.stop)
        result = sn.apply_config(other.device, sn.config_defaults())
        self.assertFalse(result.ok)
        self.assertEqual(other.saved, 0)
        self.assertEqual(other.writes, [])


class SuperNovaWriteTest(unittest.TestCase):
    def setUp(self):
        self.sim = FakeSuperNova()
        self.addCleanup(self.sim.stop)
        self.dev = self.sim.device
        self.previous = sn.read_config(self.dev)

    def test_apply_remap_and_save(self):
        config = copy.deepcopy(self.previous)
        config["remaps"] = {"A": "B"}
        result = sn.apply_config(self.dev, config, previous=self.previous)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.changed, ["remaps"])
        self.assertEqual(self.sim.saved, 1)
        block = self.sim.keys[0x01]
        self.assertEqual(block[sn.KEY_CODES], 0x00)
        self.assertEqual(block[sn.KEY_TYPE], sn.KEY_TYPE_GAMEPAD)
        self.assertEqual(block[sn.KEY_COUNT], 1)
        self.assertEqual(sn.read_config(self.dev)["remaps"], {"A": "B"})

    def test_reset_remap_to_factory(self):
        remapped = copy.deepcopy(self.previous)
        remapped["remaps"] = {"A": "B"}
        sn.apply_config(self.dev, remapped, previous=self.previous)
        self.sim.saved = 0
        current = sn.read_config(self.dev)
        reset = copy.deepcopy(current)
        reset["remaps"] = {}
        result = sn.apply_config(self.dev, reset, previous=current)
        self.assertTrue(result.ok, result.errors)
        block = self.sim.keys[0x01]
        self.assertEqual(block[sn.KEY_CODES], 0x01)
        self.assertEqual(block[sn.KEY_TURBO_TIMES], 0)
        self.assertEqual(sn.read_config(self.dev)["remaps"], {})

    def test_apply_vibration(self):
        config = copy.deepcopy(self.previous)
        config["vibration"] = {"left": 10, "right": 90}
        result = sn.apply_config(self.dev, config, previous=self.previous)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(list(self.sim.vibration[:2]), [10, 90])
        self.assertEqual(self.sim.saved, 1)

    def test_apply_deadzones_rescales_curve(self):
        config = copy.deepcopy(self.previous)
        config["stick_left"]["deadzone_min"] = 10
        config["trigger_right"]["deadzone_min"] = 8
        result = sn.apply_config(self.dev, config, previous=self.previous)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(list(self.sim.sticks[0][9:19]),
                         [10, 0, 24, 16, 55, 50, 86, 84, 100, 100])
        self.assertEqual(list(self.sim.triggers[1][4:14]),
                         [8, 0, 22, 16, 52, 50, 81, 84, 95, 100])
        self.assertEqual(self.sim.saved, 1)

    def test_sections_filter_writes_only_selected(self):
        config = copy.deepcopy(self.previous)
        config["remaps"] = {"A": "B"}
        config["vibration"] = {"left": 10, "right": 90}
        result = sn.apply_config(self.dev, config, previous=self.previous,
                                 sections=["vibration"])
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.changed, ["vibration"])
        self.assertEqual(self.sim.keys[0x01][sn.KEY_CODES], 0x01)
        self.assertEqual(list(self.sim.vibration[:2]), [10, 90])

    def test_noop_does_not_save(self):
        result = sn.apply_config(self.dev, copy.deepcopy(self.previous),
                                 previous=self.previous)
        self.assertTrue(result.ok)
        self.assertEqual(result.changed, [])
        self.assertEqual(self.sim.saved, 0)
        self.assertEqual(self.sim.writes, [])
        self.assertTrue(result.warnings)

    def test_verification_mismatch_restores_and_does_not_save(self):
        config = copy.deepcopy(self.previous)
        config["vibration"] = {"left": 10, "right": 20}
        self.sim.mangle_verification_once = True
        result = sn.apply_config(self.dev, config, previous=self.previous)
        self.assertFalse(result.ok)
        self.assertTrue(result.errors)
        self.assertEqual(self.sim.saved, 0)
        self.assertEqual(list(self.sim.vibration[:2]), [75, 75])
        self.assertEqual(len(self.sim.writes), 2)  # desired + restored original

    def test_rejected_later_block_rolls_back_earlier_write(self):
        config = copy.deepcopy(self.previous)
        config["remaps"] = {"A": "B"}
        config["vibration"] = {"left": 10, "right": 20}
        self.sim.fail_sets.add(sn.SET_VIBRATION)
        result = sn.apply_config(self.dev, config, previous=self.previous)
        self.assertFalse(result.ok)
        self.assertEqual(self.sim.saved, 0)
        self.assertEqual(self.sim.keys[0x01][sn.KEY_CODES], 0x01)
        self.assertEqual(list(self.sim.vibration[:2]), [75, 75])

    def test_vibration_test_is_not_saved_or_stored(self):
        sn.vibrate_test(self.dev, 10, 20)
        self.assertEqual(self.sim.vibration_tests, [bytes([10, 20, 0, 0])])
        self.assertEqual(self.sim.saved, 0)
        self.assertEqual(list(self.sim.vibration[:2]), [75, 75])

    def test_vibration_test_clamps(self):
        sn.vibrate_test(self.dev, -5, 150)
        self.assertEqual(self.sim.vibration_tests, [bytes([0, 100, 0, 0])])


class SuperNovaHelperTest(unittest.TestCase):
    def test_deadzone_rescale_from_factory(self):
        original = bytes([0, 0, 0, 0, 0, 0, 0, 1, 50]) + bytes(
            sn.FACTORY_POINTS[sn.STICK_POINTS]) + bytes([0, 50])
        changed = sn.with_begin_deadzone(original, sn.STICK_POINTS, 10)
        self.assertEqual(list(changed[9:19]),
                         [10, 0, 24, 16, 55, 50, 86, 84, 100, 100])
        self.assertTrue(sn.has_factory_shape(changed, sn.STICK_POINTS))
        self.assertEqual(original, bytes([0, 0, 0, 0, 0, 0, 0, 1, 50]) + bytes(
            sn.FACTORY_POINTS[sn.STICK_POINTS]) + bytes([0, 50]))

    def test_deadzone_must_be_inside_range(self):
        original = bytes(9) + bytes(sn.FACTORY_POINTS[sn.STICK_POINTS]) + bytes(2)
        with self.assertRaises(sn.SuperNovaError):
            sn.with_begin_deadzone(original, sn.STICK_POINTS, 100)
        with self.assertRaises(sn.SuperNovaError):
            sn.with_begin_deadzone(original, sn.STICK_POINTS, -1)

    def test_key_target_keeps_turbo_reset_clean(self):
        block = bytearray(sn.KEY_LEN)
        block[sn.KEY_SOURCE] = 0x01
        block[sn.KEY_TURBO_TIMES] = 1
        block[sn.KEY_TYPE] = sn.KEY_TYPE_GAMEPAD
        block[sn.KEY_COUNT] = 1
        block[sn.KEY_CODES] = 0x00
        reset = sn.with_key_target(bytes(block), 0x01)
        self.assertEqual(reset[sn.KEY_CODES], 0x01)
        self.assertEqual(reset[sn.KEY_TURBO_TIMES], 0)
        remap = sn.with_key_target(bytes(block), 0x02)
        self.assertEqual(remap[sn.KEY_CODES], 0x02)
        self.assertEqual(remap[sn.KEY_TURBO_TIMES], 1)

    def test_remap_diff_uses_defaults(self):
        config = sn.config_defaults()
        self.assertEqual(sn.diff_sections(config, config), [])
        config["remaps"]["A"] = "B"
        self.assertEqual(sn.diff_sections(sn.config_defaults(), config),
                         ["remaps"])
        config["stick_left"]["deadzone_min"] = 9
        self.assertEqual(sn.diff_sections(sn.config_defaults(), config),
                         ["remaps", "deadzones"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
