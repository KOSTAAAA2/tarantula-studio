"""Software mouse boost: fractional scaling, node selection and uinput."""
from __future__ import annotations

import struct
import unittest

from tarantula_studio.core import boost
from tarantula_studio.core import mouse


class AxisScalerTest(unittest.TestCase):
    def test_integer_factor(self):
        scaler = boost.AxisScaler(10)
        self.assertEqual([scaler.apply(v) for v in (1, 2, -1, 0, 3)],
                         [10, 20, -10, 0, 30])

    def test_fractional_factor_carries_remainder(self):
        scaler = boost.AxisScaler(2.5)
        self.assertEqual([scaler.apply(1), scaler.apply(1), scaler.apply(1),
                          scaler.apply(1)], [2, 3, 2, 3])
        self.assertEqual(scaler.apply(4), 10)

    def test_negative_fractional_accumulates_exactly(self):
        scaler = boost.AxisScaler(1.5)
        self.assertEqual([scaler.apply(-1), scaler.apply(-1),
                          scaler.apply(-1), scaler.apply(-1)],
                         [-1, -2, -1, -2])

    def test_reset_clears_carry(self):
        scaler = boost.AxisScaler(2.5)
        scaler.apply(1)
        scaler.reset()
        self.assertEqual(scaler.apply(1), 2)

    def test_scale_relative_leaves_wheel_and_other_axes(self):
        x, y = boost.AxisScaler(3), boost.AxisScaler(3)
        self.assertEqual(boost.scale_relative(mouse.REL_X, 2, x, y), 6)
        self.assertEqual(boost.scale_relative(mouse.REL_Y, -2, x, y), -6)
        self.assertEqual(boost.scale_relative(mouse.REL_WHEEL, 2, x, y), 2)
        self.assertEqual(boost.scale_relative(boost.REL_HWHEEL, -1, x, y), -1)
        self.assertEqual(boost.scale_relative(0x18, 7, x, y), 7)


class NodeSelectionTest(unittest.TestCase):
    def test_pick_first_node(self):
        nodes = [
            mouse.MouseNode("/dev/input/event1", "a", 0x3537, 0x103E, "", 3),
            mouse.MouseNode("/dev/input/event2", "b", 0x3537, 0x103E, "", 3),
        ]
        self.assertEqual(boost.pick_mouse_node(nodes).path, "/dev/input/event1")
        self.assertIsNone(boost.pick_mouse_node([]))

    def test_resolve_explicit_path_keeps_path(self):
        booster = boost.MouseBooster(node="/dev/input/event-does-not-exist",
                                     factor=2)
        self.assertIsNotNone(booster.node)
        self.assertEqual(booster.node.path, "/dev/input/event-does-not-exist")
        self.assertEqual(booster.factor, 2.0)

    def test_booster_status_without_start(self):
        booster = boost.MouseBooster(
            node=mouse.MouseNode("/dev/input/event-x", "x", 0x3537, 0, "", 3),
            factor=3)
        status = booster.status()
        self.assertFalse(status["running"])
        self.assertEqual(status["node"], "/dev/input/event-x")
        self.assertEqual(status["factor"], 3.0)
        self.assertEqual(status["events"], 0)

    def test_set_factor_updates_scalers(self):
        booster = boost.MouseBooster(
            node=mouse.MouseNode("/dev/input/event-x", "x", 0x3537, 0, "", 3),
            factor=2)
        booster.set_factor(4.5)
        self.assertEqual(booster.factor, 4.5)
        self.assertEqual(booster._x.factor, 4.5)
        self.assertEqual(booster._y.factor, 4.5)
        booster.set_factor(0)
        self.assertEqual(booster.factor, 0.1)


class VirtualMouseTest(unittest.TestCase):
    def test_setup_struct_size(self):
        self.assertEqual(struct.calcsize("HHHH80sI"), 92)

    @unittest.skipUnless(boost.uinput_available(),
                         "no writable /dev/uinput on this machine")
    def test_create_emit_and_destroy(self):
        device = boost.VirtualMouse("Tarantula Studio Test Mouse")
        try:
            device.open()
            self.assertIsNotNone(device.fd)
            device.emit([(0x00, 0x00, 0),
                         (0x02, 0x00, 5),
                         (0x02, 0x01, -3),
                         (0x00, 0x00, 0)])
        finally:
            device.close()
        self.assertIsNone(device.fd)


if __name__ == "__main__":
    unittest.main(verbosity=2)
