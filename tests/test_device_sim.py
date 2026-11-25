"""End-to-end protocol tests against the in-process Tarantula simulator.

The fake device (``tests/fake_device.py``) speaks the real framing over a
socketpair, so these tests exercise read, write, apply and verify exactly as
they would run against a physical controller.  Only the USB link is simulated.

Run with::

    python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import copy
import unittest

from tarantula_studio.core import defaults, device, keys

try:  # works with both `unittest discover -s tests` and `tests.test_device_sim`
    from tests.fake_device import FakeTarantula
except ImportError:  # pragma: no cover - discovery imports tests as top level
    from fake_device import FakeTarantula


class SimulatorTest(unittest.TestCase):
    def setUp(self):
        self.sim = FakeTarantula()
        self.dev = self.sim.device

    def tearDown(self):
        self.sim.stop()

    def read_all(self):
        config, info, warnings = device.read_all(self.dev)
        self.assertEqual(warnings, [], "read_all reported warnings")
        return config, info

    def apply(self, config, previous=None, sections=None):
        return device.apply_config(
            self.dev, config, previous=previous, sections=sections, verify=True)

    # -- reads ------------------------------------------------------------
    def test_read_all_defaults(self):
        config, info = self.read_all()
        self.assertEqual(info["firmware"], "1.2.3")
        self.assertEqual(info["battery"], 87)
        self.assertFalse(info["charging"])
        self.assertEqual(info["mac"], "aa:bb:cc:dd:ee:ff")
        self.assertEqual(info["type"], 1)
        self.assertEqual(info["controller_version"]["firmware"], "01000203")
        self.assertEqual(info["dongle_version"]["firmware"], "01000203")

        for section in ("stick_left", "stick_right"):
            actual = dict(config[section])
            expected = defaults.stick_defaults()
            actual.pop("keyboard")
            expected.pop("keyboard")
            self.assertEqual(actual, expected, section)
            # Native wheel zones read back as unbound.
            self.assertEqual(set(config[section]["keyboard"].values()),
                             {"none", ""})

        for section in ("trigger_left", "trigger_right"):
            self.assertEqual(config[section], defaults.trigger_defaults(), section)

        actual_gyro = dict(config["gyro"])
        expected_gyro = defaults.gyro_defaults()
        for direction in keys.GYRO_ZONES:
            actual_gyro.pop(f"kb_{direction}")
            expected_gyro.pop(f"kb_{direction}")
        self.assertEqual(actual_gyro, expected_gyro)
        for direction in keys.GYRO_ZONES:
            self.assertEqual(config["gyro"][f"kb_{direction}"], "none")

        self.assertEqual(config["rumble"], defaults.rumble_defaults())
        self.assertEqual(config["dpad"], defaults.dpad_defaults())
        self.assertEqual(config["key_mappings"], {})
        self.assertEqual(config["turbo_settings"], {})
        self.assertEqual(config["macro_settings"], {})

        lighting = config["lighting"]
        self.assertEqual(lighting["lighting_mode"], "colorful")
        self.assertEqual(lighting["brightness"], 50)
        self.assertEqual(lighting["lighting_speed"], 50)
        self.assertEqual(lighting["panel_hsv"], [240, 100, 50])
        self.assertEqual(lighting["home_hsv"], [0, 0, 100])
        self.assertEqual([c[0] for c in lighting["abxy_hsv"]], [120, 0, 240, 58])
        self.assertEqual(lighting["bayx_hsv"], [[0, 0, 6]] * 4)

    # -- DPI --------------------------------------------------------------
    def test_quick_set_dpi_above_official_cap(self):
        config, _ = self.read_all()
        stick = device.quick_set_dpi(self.dev, 1, 255)
        self.assertEqual(stick["mode"], "mouse")
        self.assertEqual(stick["mouse_dpi"], 255)
        self.assertEqual(stick["mouse_dpi_y"], 255)
        # The raw firmware bytes keep the full range.
        self.assertEqual(self.sim.stick_mapping[1][8], 255)
        self.assertEqual(self.sim.stick_mapping[1][9], 255)

        config["stick_right"] = stick
        self.assertEqual(device.verify_section(self.dev, config, "sticks"), [])

        clamped = device.quick_set_dpi(self.dev, 0, 999)
        self.assertEqual(clamped["mouse_dpi"], 255)
        self.assertEqual(clamped["mouse_dpi_y"], 255)

    def test_dpi_255_apply_and_verify(self):
        config, _ = self.read_all()
        base = copy.deepcopy(config)
        config["stick_right"].update(mode="mouse", mouse_dpi=255, mouse_dpi_y=255)

        result = self.apply(config, previous=base)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.changed, ["sticks"])

        got = device.read_stick(self.dev, 1)
        self.assertEqual(got["mode"], "mouse")
        self.assertEqual(got["mouse_dpi"], 255)
        self.assertEqual(got["mouse_dpi_y"], 255)
        self.assertEqual(self.sim.stick_mapping[1][8], 255)

    def test_firmware_dpi_clamp_is_reported(self):
        sim = FakeTarantula(clamp_dpi=True)
        try:
            dev = sim.device
            config, _info, warnings = device.read_all(dev)
            self.assertEqual(warnings, [])
            config["stick_right"].update(mode="mouse", mouse_dpi=200,
                                         mouse_dpi_y=200)
            result = device.apply_config(dev, config, sections=["sticks"],
                                         verify=True)
            self.assertTrue(result.ok)
            self.assertEqual(result.errors, [])
            self.assertEqual(len(result.warnings), 2)
            for warning in result.warnings:
                self.assertIn("ограничивает DPI", warning)
                self.assertIn("200", warning)
                self.assertIn("100", warning)
            self.assertEqual(device.read_stick(dev, 1)["mouse_dpi"], 100)
        finally:
            sim.stop()

    def test_write_stick_now_roundtrip(self):
        stick = defaults.stick_defaults()
        stick.update(mode="mouse", mouse_dpi=180, mouse_dpi_y=255)
        got = device.write_stick_now(self.dev, 1, stick)
        self.assertEqual(got["mode"], "mouse")
        self.assertEqual(got["mouse_dpi"], 180)
        self.assertEqual(got["mouse_dpi_y"], 255)
        self.assertEqual(got["curve_preset"], "linear")
        self.assertEqual(self.sim.stick_mapping[1][8], 180)
        self.assertEqual(self.sim.stick_mapping[1][9], 255)
        self.assertEqual(self.sim.saved, 1)

    # -- mappings, turbo, macros -----------------------------------------
    def test_mappings_turbo_and_removal(self):
        config, _ = self.read_all()
        base = copy.deepcopy(config)
        config["key_mappings"] = {
            "l4": "controller:a",
            "r4": "mouse:right_click+scroll_down",
        }
        config["turbo_settings"] = {"l4": {"rate": 12, "continuous": True}}

        result = self.apply(config, previous=base)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.changed, ["mappings"])

        target, turbo = device.read_mapping(self.dev, keys.button_id("l4"))
        self.assertEqual(target, "controller:a")
        self.assertEqual(turbo, {"rate": 12, "continuous": True, "turbo": True})
        target, turbo = device.read_mapping(self.dev, keys.button_id("r4"))
        self.assertEqual(target, "mouse:right_click+mouse:scroll_down")
        self.assertIsNone(turbo)

        # Removing a mapping writes the factory target back.
        result = self.apply(base, previous=config)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.warnings, [])
        for name in ("l4", "r4"):
            target, turbo = device.read_mapping(self.dev, keys.button_id(name))
            self.assertIsNone(target, name)
            self.assertIsNone(turbo, name)

    def test_macro_roundtrip_and_clear(self):
        config, _ = self.read_all()
        base = copy.deepcopy(config)
        steps = [
            ["controller:b", 100, 50],
            ["key:left_ctrl+a", 20, 10],
            ["media:vol_up", 5, 5],
        ]
        config["macro_settings"] = {
            "t2": {"steps": copy.deepcopy(steps), "hold": False, "loop": False},
        }

        result = self.apply(config, previous=base)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.warnings, [])

        got = device.read_macro_steps(self.dev, keys.button_id("t2"))
        self.assertEqual([[s["target"], s["press_ms"], s["release_ms"]]
                          for s in got], [
            ["controller:b", 100, 50],
            ["key:left_ctrl+key:a", 20, 10],
            ["media:vol_up", 5, 5],
        ])
        maps, _turbo, macros, warnings = device.read_mappings(self.dev)
        self.assertEqual(warnings, [])
        self.assertIn("t2", macros)
        self.assertEqual(maps["t2"],
                         "macro:controller:b+key:left_ctrl+key:a+media:vol_up")
        self.assertEqual(macros["t2"]["steps"], [
            ["controller:b", 100, 50],
            ["key:left_ctrl+key:a", 20, 10],
            ["media:vol_up", 5, 5],
        ])

        result = self.apply(base, previous=config)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.warnings, [])
        self.assertEqual(device.read_macro_steps(self.dev, keys.button_id("t2")), [])

    # -- sticks / wheel ---------------------------------------------------
    def test_wheel_mode_zones_and_clear(self):
        config, _ = self.read_all()
        base = copy.deepcopy(config)
        keyboard = {
            "left": "key:a", "right": "key:d", "up": "key:w", "down": "none",
            "outline": "key:left_shift",
            "left_outer": "", "right_outer": "", "up_outer": "", "down_outer": "",
        }
        config["stick_left"].update(mode="wheel", keyboard=dict(keyboard))

        result = self.apply(config, previous=base)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.warnings, [])
        got = device.read_stick(self.dev, 0)["keyboard"]
        self.assertEqual(got["left"], "key:a")
        self.assertEqual(got["right"], "key:d")
        self.assertEqual(got["up"], "key:w")
        self.assertEqual(got["down"], "none")
        self.assertEqual(got["outline"], "key:left_shift")
        for name in ("left_outer", "right_outer", "up_outer", "down_outer"):
            self.assertEqual(got[name], "")

        # Distinct outer-ring keys must not be collapsed into one outline.
        config2 = copy.deepcopy(config)
        config2["stick_left"]["keyboard"].update(
            outline="", left_outer="key:q", right_outer="key:e",
            up_outer="none", down_outer="none")
        result = self.apply(config2, previous=config)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.warnings, [])
        got = device.read_stick(self.dev, 0)["keyboard"]
        self.assertEqual(got["outline"], "")
        self.assertEqual(got["left_outer"], "key:q")
        self.assertEqual(got["right_outer"], "key:e")
        self.assertEqual(got["up_outer"], "none")
        self.assertEqual(got["down_outer"], "none")

        # Clearing every zone writes unbind packets.
        config3 = copy.deepcopy(config2)
        config3["stick_left"]["keyboard"] = {
            name: "none" for name in (
                "left", "right", "up", "down", "outline",
                "left_outer", "right_outer", "up_outer", "down_outer")
        }
        result = self.apply(config3, previous=config2)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.warnings, [])
        got = device.read_stick(self.dev, 0)["keyboard"]
        for name in ("left", "right", "up", "down"):
            self.assertEqual(got[name], "none")
        self.assertEqual(got["outline"], "none")
        for name in ("left_outer", "right_outer", "up_outer", "down_outer"):
            self.assertEqual(got[name], "")

    # -- gyro -------------------------------------------------------------
    def test_gyro_keyboard_zones_and_clear(self):
        config, _ = self.read_all()
        base = copy.deepcopy(config)
        config["gyro"].update(
            output_mode="keyboard", activate_button="l4", activate_method="hold",
            x_sensitivity=200, y_sensitivity=30,
            kb_left="key:a", kb_right="key:d", kb_up="key:w", kb_down="none",
        )
        result = self.apply(config, previous=base)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.warnings, [])
        got = device.read_gyro(self.dev)
        self.assertEqual(got["output_mode"], "keyboard")
        self.assertEqual(got["activate_button"], "l4")
        self.assertEqual(got["activate_method"], "hold")
        self.assertEqual(got["x_sensitivity"], 200)
        self.assertEqual(got["y_sensitivity"], 30)
        self.assertEqual(got["kb_left"], "key:a")
        self.assertEqual(got["kb_right"], "key:d")
        self.assertEqual(got["kb_up"], "key:w")
        self.assertEqual(got["kb_down"], "none")

        # Empty zones must be explicitly unbound, not silently skipped.
        config2 = copy.deepcopy(config)
        config2["gyro"].update(kb_left="none", kb_right="none",
                               kb_up="none", kb_down="none")
        result = self.apply(config2, previous=config)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.warnings, [])
        got = device.read_gyro(self.dev)
        for direction in keys.GYRO_ZONES:
            self.assertEqual(got[f"kb_{direction}"], "none")

    # -- other sections ---------------------------------------------------
    def test_trigger_roundtrip(self):
        config, _ = self.read_all()
        base = copy.deepcopy(config)
        for side in ("trigger_left", "trigger_right"):
            config[side].update(
                hair_mode="fixed", hair_trigger_begin=15, hair_trigger_end=25,
                deadzone_min=7, deadzone_max=93, antideadzone_min=3,
                antideadzone_max=97, curve_preset="s-curve",
                curve_intensity=64,
                curve_points=[[10, 20], [40, 50], [80, 90]],
            )
        result = self.apply(config, previous=base)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.warnings, [])
        for side, index in (("trigger_left", 0), ("trigger_right", 1)):
            got = device.read_trigger(self.dev, index)
            for field in ("hair_mode", "hair_trigger_begin", "hair_trigger_end",
                          "deadzone_min", "deadzone_max", "antideadzone_min",
                          "antideadzone_max", "curve_preset", "curve_intensity",
                          "curve_points"):
                self.assertEqual(got[field], config[side][field], f"{side}.{field}")

    def test_lighting_roundtrip(self):
        config, _ = self.read_all()
        base = copy.deepcopy(config)
        config["lighting"].update(
            lighting_mode="static", brightness=80, lighting_speed=25,
            home_hsv=[200, 50, 70],
            abxy_hsv=[[10, 80, 40], [20, 90, 50], [30, 70, 60], [40, 60, 70]],
            bayx_hsv=[[0, 0, 0], [7, 100, 100], [120, 50, 50], [240, 100, 100]],
        )
        result = self.apply(config, previous=base)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.warnings, [])
        got = device.read_lighting(self.dev)
        self.assertEqual(got["lighting_mode"], "static")
        self.assertEqual(got["brightness"], 80)
        self.assertEqual(got["lighting_speed"], 25)
        self.assertEqual(got["home_hsv"], [199, 50, 70])
        self.assertEqual([c[0] for c in got["abxy_hsv"]], [10, 20, 30, 40])
        self.assertEqual([c[0] for c in got["bayx_hsv"]], [0, 6, 120, 240])
        self.assertEqual(got["abxy_hsv"][0][1:], [80, 40])
        self.assertEqual(got["bayx_hsv"][1][1:], [100, 100])

    def test_rumble_roundtrip(self):
        config, _ = self.read_all()
        base = copy.deepcopy(config)
        config["rumble"].update(left=20, right=90, lt_mode=1, rt_mode=1,
                                lt_level=60, rt_level=30)
        result = self.apply(config, previous=base)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.warnings, [])
        self.assertEqual(device.read_rumble(self.dev), {
            "left": 20, "right": 90, "lt_mode": 1, "rt_mode": 1,
            "lt_level": 60, "rt_level": 30,
        })

    def test_dpad_roundtrip(self):
        config, _ = self.read_all()
        base = copy.deepcopy(config)
        config["dpad"].update(dpad_type="4way", swap="dpad_to_rs",
                              layout="switch", auto_onoff=False,
                              fast_trigger=False, macro_switch="l4")
        result = self.apply(config, previous=base)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.warnings, [])
        self.assertEqual(device.read_dpad(self.dev), {
            "dpad_type": "4way", "swap": "dpad_to_rs", "layout": "switch",
            "auto_onoff": False, "fast_trigger": False, "macro_switch": "l4",
        })

    # -- full apply -------------------------------------------------------
    def test_full_apply_and_incremental_update(self):
        config, _ = self.read_all()
        config["stick_left"].update(mode="mouse", mouse_dpi=255, mouse_dpi_y=255)
        config["stick_right"].update(mode="wheel")
        config["stick_right"]["keyboard"].update(
            left="key:a", right="key:d", up="key:w", down="key:s",
            outline="key:left_shift")
        config["trigger_left"].update(hair_mode="fixed", hair_trigger_begin=15,
                                      hair_trigger_end=25)
        config["gyro"].update(output_mode="keyboard", activate_button="l4",
                              activate_method="hold", x_sensitivity=200,
                              kb_left="key:a", kb_right="key:d",
                              kb_up="key:w", kb_down="none")
        config["lighting"].update(lighting_mode="static", brightness=80,
                                  lighting_speed=25, home_hsv=[200, 50, 70])
        config["rumble"].update(left=20, right=90, lt_mode=1, rt_mode=1,
                                lt_level=60, rt_level=30)
        config["dpad"].update(dpad_type="4way", swap="dpad_to_ls",
                              layout="switch", auto_onoff=False, fast_trigger=False)
        config["key_mappings"] = {"l4": "controller:a", "r4": "key:left_ctrl+c"}
        config["turbo_settings"] = {"l4": {"rate": 12, "continuous": True}}
        config["macro_settings"] = {
            "t1": {"steps": [["controller:a", 100, 50], ["key:w", 20, 10]],
                   "hold": True, "loop": True},
        }

        result = self.apply(config, previous=None)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.changed,
                         ["sticks", "triggers", "gyro", "lighting",
                          "rumble", "dpad", "mappings"])
        self.assertEqual(self.sim.saved, 7)
        self.assertEqual(self.sim.stick_mapping[0][8], 255)
        self.assertIsNotNone(result.readback)
        self.assertEqual(result.readback["battery"], 87)

        readback, _ = self.read_all()
        self.assertEqual(readback["stick_left"]["mouse_dpi"], 255)
        self.assertEqual(readback["stick_right"]["mode"], "wheel")
        self.assertEqual(readback["stick_right"]["keyboard"]["outline"],
                         "key:left_shift")
        self.assertEqual(readback["dpad"]["dpad_type"], "4way")
        self.assertEqual(readback["key_mappings"]["l4"], "controller:a")
        self.assertEqual(readback["key_mappings"]["r4"], "key:left_ctrl+key:c")
        self.assertIn("t1", readback["macro_settings"])
        self.assertEqual(readback["macro_settings"]["t1"]["steps"],
                         [["controller:a", 100, 50], ["key:w", 20, 10]])
        self.assertTrue(readback["macro_settings"]["t1"]["hold"])
        self.assertTrue(readback["macro_settings"]["t1"]["loop"])
        self.assertEqual(readback["turbo_settings"]["l4"],
                         {"rate": 12, "continuous": True})

        # Only the changed section is written on an incremental apply.
        count = self.sim.saved
        changed = copy.deepcopy(readback)
        changed["dpad"]["dpad_type"] = "8way"
        result = self.apply(changed, previous=readback)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.changed, ["dpad"])
        self.assertEqual(self.sim.saved, count + 1)

    def test_apply_without_changes_is_a_noop(self):
        config, _ = self.read_all()
        saved = self.sim.saved
        result = self.apply(config, previous=config)
        self.assertTrue(result.ok)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.changed, [])
        self.assertEqual(result.warnings, ["Нет изменений для записи."])
        self.assertIsNone(result.readback)
        self.assertEqual(self.sim.saved, saved)

    def test_unknown_section_is_skipped(self):
        config, _ = self.read_all()
        result = self.apply(config, previous=config, sections=["nonsense"])
        self.assertTrue(result.ok)
        self.assertEqual(result.changed, [])
        self.assertEqual(result.warnings, ["Нет изменений для записи."])


if __name__ == "__main__":
    unittest.main(verbosity=2)
