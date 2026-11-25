"""Offscreen GUI tests for the Super Nova page and software DPI boost."""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

_TMP = tempfile.TemporaryDirectory(prefix="tarantula-studio-sn-test-")
os.environ["TARANTULA_STUDIO_CONFIG"] = _TMP.name
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from tarantula_studio.core import boost  # noqa: E402
from tarantula_studio.core import supernova as snmod  # noqa: E402
from tarantula_studio.gui.app import MainWindow  # noqa: E402
from tarantula_studio.gui.theme import apply_theme  # noqa: E402


class SuperNovaGuiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        apply_theme(cls.app)

    @classmethod
    def tearDownClass(cls):
        cls.app.processEvents()
        _TMP.cleanup()

    def setUp(self):
        self.window = MainWindow(demo=True)
        self.window.show()
        QTest.qWait(400)
        self.state = self.window.state

    def tearDown(self):
        if self.window.state.busy:
            self.fail("window still busy after test")
        self.window.close()
        self.window.deleteLater()
        QTest.qWait(20)

    def _connect_supernova(self):
        info = {
            "device_type": 3, "product": snmod.PRODUCT,
            "firmware": "1.0.6", "mac": "aa:bb:cc:dd:ee:ff",
            "battery": 55, "charging": False,
        }
        config = snmod.config_defaults()
        config["info"] = info
        self.state.set_supernova_config(config, info)
        QTest.qWait(10)
        self.window.navigate("supernova")
        QTest.qWait(10)
        return config

    def test_page_exists_and_demo_is_inactive(self):
        page = self.window.pages["supernova"]
        self.assertTrue(page.TITLE)
        self.assertTrue(page.SUBTITLE)
        page.refresh()
        self.assertFalse(page.remap_combos["A"].isEnabled() or
                         self.state.device_kind == "supernova")

    def test_navigation_hides_t3_pages_for_supernova(self):
        self._connect_supernova()
        self.assertTrue(self.window._nav_items["supernova"].isHidden() is False)
        for key in ("mouse", "sticks", "triggers", "buttons", "macros",
                    "gyro", "lighting", "vibration", "dpad", "profiles"):
            self.assertTrue(self.window._nav_items[key].isHidden(), key)
        self.assertFalse(self.window._nav_items["overview"].isHidden())
        self.assertFalse(self.window._nav_items["diagnostics"].isHidden())

    def test_dashboard_hides_dpi_and_actions_for_supernova(self):
        self._connect_supernova()
        overview = self.window.pages["overview"]
        overview.refresh()
        self.assertTrue(overview.dpi_card.isHidden())
        self.assertTrue(overview.actions_card.isHidden())

    def test_remap_edit_tracks_dirty_and_discard(self):
        self._connect_supernova()
        page = self.window.pages["supernova"]
        combo = page.remap_combos["A"]
        self.assertTrue(page._editor_cards[0].isEnabled())
        combo.setCurrentIndex(combo.findData("B"))
        QTest.qWait(10)
        self.assertEqual(self.state.dirty_supernova_sections(), ["remaps"])
        self.assertTrue(self.window.apply_button.isEnabled())
        self.assertIn("переназначения", self.window.dirty_label.text())
        old_question = QMessageBox.question
        QMessageBox.question = staticmethod(
            lambda *a, **k: QMessageBox.StandardButton.Yes)
        try:
            self.window.discard_changes()
        finally:
            QMessageBox.question = old_question
        QTest.qWait(10)
        self.assertEqual(self.state.dirty_supernova_sections(), [])
        self.assertEqual(combo.currentData(), "A")

    def test_deadzone_and_vibration_edits(self):
        self._connect_supernova()
        page = self.window.pages["supernova"]
        page.stick_left.slider.setValue(12)
        QTest.qWait(10)
        self.assertEqual(self.state.dirty_supernova_sections(), ["deadzones"])
        self.assertEqual(self.state.supernova["stick_left"]["deadzone_min"], 12)
        old_question = QMessageBox.question
        QMessageBox.question = staticmethod(
            lambda *a, **k: QMessageBox.StandardButton.Yes)
        try:
            self.window.discard_changes()
        finally:
            QMessageBox.question = old_question
        page.vib_right.slider.setValue(33)
        QTest.qWait(10)
        self.assertEqual(self.state.dirty_supernova_sections(), ["vibration"])
        self.assertEqual(self.state.supernova["vibration"]["right"], 33)

    def test_leaving_supernova_state_restores_navigation(self):
        self._connect_supernova()
        self.state.device_kind = "none"
        self.state.device_present = False
        self.state.deviceChanged.emit()
        QTest.qWait(10)
        for key, item in self.window._nav_items.items():
            self.assertFalse(item.isHidden(), key)

    def test_boost_targets_1000_and_2000(self):
        page = self.window.pages["mouse"]
        self.window.navigate("mouse")
        page.dpi_x.set_value(250)
        page.dpi_y.set_value(250)
        page._set_boost_target(1000)
        self.assertEqual(page.boost_factor.value(), 4)
        self.assertIn("1000", page.boost_effective.text())
        page._set_boost_target(2000)
        self.assertEqual(page.boost_factor.value(), 8)
        self.assertIn("2000", page.boost_effective.text())
        self.assertEqual(page.boost_enable.isEnabled(), True)

    def test_boost_start_failure_is_reported_without_staying_enabled(self):
        page = self.window.pages["mouse"]
        self.window.navigate("mouse")
        page._scan_nodes()
        page.boost_node.clear()
        with mock.patch.object(boost.MouseBooster, "start",
                               side_effect=boost.MouseBoostError("no node")):
            old_warning = QMessageBox.warning
            QMessageBox.warning = staticmethod(lambda *a, **k: None)
            try:
                page.boost_enable.setChecked(True)
            finally:
                QMessageBox.warning = old_warning
        self.assertFalse(page.boost_enable.isChecked())
        self.assertIsNone(self.window.mouse_booster)

    def test_measure_disabled_while_boosting(self):
        page = self.window.pages["mouse"]
        self.window.navigate("mouse")
        page.boost_node.addItem("fake", "/dev/input/event-fake")
        self.window.mouse_booster = object()
        try:
            page._sync_measure_availability()
            self.assertFalse(page.measure_button.isEnabled())
        finally:
            self.window.mouse_booster = None
        page._sync_measure_availability()
        self.assertTrue(page.measure_button.isEnabled())


if __name__ == "__main__":
    unittest.main(verbosity=2)
