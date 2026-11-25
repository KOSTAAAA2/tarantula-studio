"""Offscreen GUI smoke tests.

Run with::

    QT_QPA_PLATFORM=offscreen python3 -m unittest tests.test_gui_smoke -v

The test never touches real device nodes: the window is started in demo mode and
all dialogs that would block or ask questions are driven directly or patched.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

# Must be set before importing tarantula_studio.core.config.
_TMP = tempfile.TemporaryDirectory(prefix="tarantula-studio-test-")
os.environ["TARANTULA_STUDIO_CONFIG"] = _TMP.name
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox  # noqa: E402

from tarantula_studio.core import config as cfg  # noqa: E402
from tarantula_studio.core import keys  # noqa: E402
from tarantula_studio.core import mouse  # noqa: E402
from tarantula_studio.gui.app import MainWindow  # noqa: E402
from tarantula_studio.gui.theme import apply_theme  # noqa: E402
from tarantula_studio.gui.widgets import (  # noqa: E402
    MacroStepDialog, TargetEditorDialog, TurboDialog,
)


class GuiSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        apply_theme(cls.app)

    @classmethod
    def tearDownClass(cls):
        cls.app.processEvents()
        cfg_path = Path(_TMP.name)
        _TMP.cleanup()

    def setUp(self):
        self.window = MainWindow(demo=True)
        self.window.show()
        QTest.qWait(300)  # let the startup timer run
        self.state = self.window.state

    def tearDown(self):
        if self.window.state.busy:
            self.fail("window still busy after test")
        self.window.close()
        self.window.deleteLater()
        QTest.qWait(20)

    # -- helpers ----------------------------------------------------------
    def all_pages(self):
        return list(self.window.pages.items())

    def assert_no_dirty(self):
        self.assertEqual(self.state.dirty_sections(), [])

    def set_question_yes(self):
        self._old_question = QMessageBox.question
        QMessageBox.question = staticmethod(
            lambda *a, **k: QMessageBox.StandardButton.Yes)

    def restore_question(self):
        QMessageBox.question = self._old_question

    # -- navigation -------------------------------------------------------
    def test_every_page_refreshes(self):
        for key, page in self.all_pages():
            with self.subTest(page=key):
                page.refresh()
                self.window.navigate(key)
                QTest.qWait(5)
                self.assertIs(self.window.stack.currentWidget(), page)
                self.assertEqual(self.window.page_title.text(), page.TITLE)

    def test_all_pages_have_titles(self):
        for key, page in self.all_pages():
            self.assertTrue(page.TITLE, key)
            self.assertTrue(page.SUBTITLE, key)

    # -- staged edits -----------------------------------------------------
    def test_mouse_page_allows_dpi_above_100(self):
        page = self.window.pages["mouse"]
        self.window.navigate("mouse")
        page.side_combo.setCurrentIndex(0)  # right stick
        page.mode.setCurrentIndex(page.mode.findData("mouse"))
        page.dpi_x.slider.setValue(150)
        self.assertEqual(page.dpi_x.value(), 150)
        self.assertEqual(page.dpi_y.value(), 150)
        self.assertTrue(page.dpi_note.isVisible())
        right = self.state.staged["stick_right"]
        self.assertEqual(right["mode"], "mouse")
        self.assertEqual(right["mouse_dpi"], 150)
        self.assertEqual(right["mouse_dpi_y"], 150)
        self.assertEqual(self.state.dirty_sections(), ["sticks"])
        self.assertFalse(self.window.apply_button.isEnabled())

        page.dpi_x.slider.setValue(255)
        self.assertEqual(right["mouse_dpi"], 255)
        self.assertEqual(right["mouse_dpi_y"], 255)

    def test_dashboard_quick_dpi(self):
        page = self.window.pages["overview"]
        self.window.navigate("overview")
        page.side_combo.setCurrentIndex(0)
        page.dpi.slider.setValue(180)
        self.assertTrue(page.dpi_note.isVisible())
        self.assertEqual(self.state.staged["stick_right"]["mouse_dpi"], 50)

    def test_sticks_wheel_mode_and_zones(self):
        page = self.window.pages["sticks"]
        self.window.navigate("sticks")
        tab = page.right
        tab.mode.setCurrentIndex(tab.mode.findData("wheel"))
        self.assertFalse(tab.wheel.isHidden())
        tab.dpi_x.slider.setValue(200)
        self.assertEqual(self.state.staged["stick_right"]["mouse_dpi"], 200)
        tab._refresh_wheel()
        tab.mode.setCurrentIndex(tab.mode.findData("native"))
        self.assertTrue(tab.wheel.isHidden())
        self.assertEqual(self.state.dirty_sections(), ["sticks"])

    def test_triggers_edit(self):
        page = self.window.pages["triggers"]
        self.window.navigate("triggers")
        tab = page.right
        tab.hair.setCurrentIndex(tab.hair.findData("fixed"))
        tab.begin.slider.setValue(15)
        self.assertEqual(self.state.staged["trigger_right"]["hair_mode"], "fixed")
        self.assertEqual(self.state.staged["trigger_right"]["hair_trigger_begin"], 15)
        self.assertEqual(self.state.dirty_sections(), ["triggers"])

    def test_buttons_table_and_macro_navigation(self):
        page = self.window.pages["buttons"]
        self.window.navigate("buttons")
        self.assertGreater(page.table.rowCount(), 20)
        row = page._rows["l4"]
        page.table.selectRow(row)
        page._selection_changed()
        self.assertTrue(page.macro_button.isEnabled())
        page.table.selectRow(page._rows["a"])
        page._selection_changed()
        self.assertFalse(page.macro_button.isEnabled())
        page.table.selectRow(page._rows["l4"])
        page._selection_changed()
        page._macro()  # navigates to macros and selects l4
        QTest.qWait(5)
        self.assertEqual(self.window.stack.currentWidget(), self.window.pages["macros"])
        macros_page = self.window.pages["macros"]
        self.assertEqual(macros_page._selected(), "l4")

    def test_macro_add_and_clear(self):
        page = self.window.pages["macros"]
        self.window.navigate("macros")
        page.select_button("l4")
        page._steps = [
            {"target": "controller:a", "press_ms": 30, "release_ms": 30},
            {"target": "key:b", "press_ms": 10, "release_ms": 40},
        ]
        page._commit()
        macro = self.state.staged["macro_settings"]["l4"]
        self.assertEqual(len(macro["steps"]), 2)
        self.assertEqual(macro["steps"][0], ["controller:a", 30, 30])
        self.assertNotIn("l4", self.state.staged.get("key_mappings") or {})
        page._steps = []
        page._commit()
        self.assertNotIn("l4", self.state.staged["macro_settings"])

    def test_gyro_edit(self):
        page = self.window.pages["gyro"]
        self.window.navigate("gyro")
        page.output.setCurrentIndex(page.output.findData("keyboard"))
        self.assertTrue(page.directions.isVisible())
        page.output.setCurrentIndex(page.output.findData("mouse"))
        page.x_sensitivity.slider.setValue(77)
        self.assertEqual(self.state.staged["gyro"]["output_mode"], "mouse")
        self.assertEqual(self.state.staged["gyro"]["x_sensitivity"], 77)
        self.assertFalse(page.directions.isVisible())

    def test_lighting_edit_and_preset(self):
        page = self.window.pages["lighting"]
        self.window.navigate("lighting")
        page.mode.setCurrentIndex(page.mode.findData("breathing"))
        page.brightness.slider.setValue(66)
        self.assertEqual(self.state.staged["lighting"]["lighting_mode"], "breathing")
        self.assertEqual(self.state.staged["lighting"]["brightness"], 66)
        page.panel.set_hsv([12, 34, 56])
        page._color_changed("panel_hsv", [12, 34, 56])
        self.assertEqual(self.state.staged["lighting"]["panel_hsv"], [12, 34, 56])
        page._preset()
        self.assertEqual(self.state.staged["lighting"]["abxy_hsv"],
                         [[120, 100, 6], [0, 100, 6], [240, 100, 6], [59, 100, 6]])

    def test_vibration_edit(self):
        page = self.window.pages["vibration"]
        self.window.navigate("vibration")
        page.left.slider.setValue(44)
        page.lt_check.setChecked(True)
        page.lt_level.slider.setValue(55)
        rumble = self.state.staged["rumble"]
        self.assertEqual(rumble["left"], 44)
        self.assertEqual(rumble["lt_mode"], 1)
        self.assertEqual(rumble["lt_level"], 55)
        self.assertTrue(page.lt_level.isEnabled())

    def test_dpad_edit(self):
        page = self.window.pages["dpad"]
        self.window.navigate("dpad")
        page.swap.setCurrentIndex(page.swap.findData("dpad_to_ls"))
        page.auto.setChecked(False)
        dpad = self.state.staged["dpad"]
        self.assertEqual(dpad["swap"], "dpad_to_ls")
        self.assertFalse(dpad["auto_onoff"])
        self.assertEqual(self.state.dirty_sections(), ["dpad"])

    # -- discard / local persistence --------------------------------------
    def test_discard_restores_baseline(self):
        page = self.window.pages["mouse"]
        self.window.navigate("mouse")
        page.dpi_x.slider.setValue(200)
        self.assertTrue(self.state.dirty_sections())
        self.set_question_yes()
        try:
            self.window.discard_changes()
        finally:
            self.restore_question()
        self.assert_no_dirty()
        self.assertNotEqual(
            self.state.staged["stick_right"]["mouse_dpi"], 200)

    def test_local_config_saved(self):
        page = self.window.pages["mouse"]
        page.dpi_x.slider.setValue(123)
        self.state.save()
        loaded = cfg.load_config()
        self.assertEqual(loaded["stick_right"]["mouse_dpi"], 123)

    # -- profiles, backups, import/export ---------------------------------
    def test_profiles_save_load_delete(self):
        page = self.window.pages["profiles"]
        self.window.navigate("profiles")
        self.state.staged["stick_left"]["mouse_dpi"] = 111
        name = cfg.save_profile("Smoke Profile", self.state.staged)
        page.refresh_lists()
        self.assertEqual(page.profile_list.count(), 1)
        self.assertIn("Smoke Profile", page.profile_list.item(0).text())

        self.state.staged["stick_left"]["mouse_dpi"] = 20
        page.profile_list.setCurrentRow(0)
        page._load_profile()
        self.assertEqual(self.state.staged["stick_left"]["mouse_dpi"], 111)
        self.assertEqual(cfg.get_active_profile(), name)

        page.profile_list.setCurrentRow(0)
        self.set_question_yes()
        try:
            page._delete_profile()
        finally:
            self.restore_question()
        self.assertEqual(page.profile_list.count(), 0)

    def test_backups_create_load_delete(self):
        page = self.window.pages["profiles"]
        self.window.navigate("profiles")
        path = cfg.backup_config(self.state.staged, "gui-test")
        page.refresh_lists()
        self.assertGreaterEqual(page.backup_list.count(), 1)
        self.state.staged["trigger_left"]["hair_mode"] = "fixed"
        page.backup_list.setCurrentRow(0)
        page._restore_backup()
        self.assertEqual(self.state.staged["trigger_left"]["hair_mode"], "off")
        page.backup_list.setCurrentRow(0)
        self.set_question_yes()
        try:
            page._delete_backup()
        finally:
            self.restore_question()
        self.assertNotIn(str(path), [b["path"] for b in cfg.list_backups()])

    def test_json_export_import(self):
        page = self.window.pages["profiles"]
        self.window.navigate("profiles")
        self.state.staged["rumble"]["left"] = 33
        target = Path(_TMP.name) / "export-test.json"
        old_save = QFileDialog.getSaveFileName
        old_open = QFileDialog.getOpenFileName
        QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(target), ""))
        QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(target), ""))
        try:
            page._export()
            self.assertTrue(target.exists())
            self.state.staged["rumble"]["left"] = 99
            page._import()
        finally:
            QFileDialog.getSaveFileName = old_save
            QFileDialog.getOpenFileName = old_open
        self.assertEqual(self.state.staged["rumble"]["left"], 33)

    # -- diagnostics ------------------------------------------------------
    def test_diagnostics_refresh(self):
        page = self.window.pages["diagnostics"]
        self.window.navigate("diagnostics")
        page.refresh()
        self.assertIn("udev", page.rule_pill.text())
        self.assertIn("журнал", page.SUBTITLE.lower())
        page.append_log("test message")
        self.assertIn("test message", page.log_edit.toPlainText())

    # -- live input without hardware --------------------------------------
    def test_live_poll_without_joystick(self):
        page = self.window.pages["overview"]
        self.window.navigate("overview")
        page.live_check.setChecked(True)
        QTest.qWait(120)
        self.assertIn("Джойстик не найден", page.live_status.text())
        page.live_check.setChecked(False)

    def test_mouse_scan_without_hardware(self):
        page = self.window.pages["mouse"]
        self.window.navigate("mouse")
        page._scan_nodes()
        self.assertIn("не найден", page.nodes_label.text().lower())
        self.assertFalse(page.measure_button.isEnabled())

    # -- dialogs ----------------------------------------------------------
    def test_target_editor_roundtrip(self):
        cases = [
            ("controller:a+b", "controller"),
            ("key:left_ctrl+a", "key"),
            ("mouse:left_click+scroll_up", "mouse"),
            ("media:play", "media"),
            ("none", "unbind"),
            (None, "factory"),
        ]
        for target, kind in cases:
            with self.subTest(target=target):
                dialog = TargetEditorDialog(target)
                dialog.show()
                QTest.qWait(5)
                self.assertEqual(dialog.kind.currentData(), kind)
                result = dialog.target()
                if target is None:
                    self.assertIsNone(result)
                elif target == "none":
                    self.assertEqual(result, "none")
                else:
                    self.assertEqual(result, target)
                    keys.encode_target(result)
                dialog.reject()

    def test_macro_step_dialog(self):
        dialog = MacroStepDialog()
        dialog.show()
        QTest.qWait(5)
        step = dialog.step()
        self.assertIn("target", step)
        self.assertEqual(step["press_ms"], 50)
        keys.encode_target(step["target"])
        dialog.reject()

    def test_turbo_dialog(self):
        dialog = TurboDialog({"rate": 20, "continuous": True})
        dialog.show()
        QTest.qWait(5)
        self.assertEqual(dialog.rate.value(), 20)
        self.assertTrue(dialog.continuous.isChecked())
        result = dialog.result_settings()
        self.assertEqual(result, {"rate": 20, "continuous": True})
        dialog.enabled.setChecked(False)
        self.assertIsNone(dialog.result_settings())
        dialog.reject()


if __name__ == "__main__":
    unittest.main(verbosity=2)
