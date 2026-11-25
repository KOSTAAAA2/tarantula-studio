"""Vibration page."""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel

from ...core import device as devmod
from ...core.transport import HidrawDevice
from ..widgets import Card, Page, SliderRow, make_button, muted, note


class VibrationPage(Page):
    TITLE = "Вибрация"
    SUBTITLE = "Сила моторов и виброотклик курков"

    def __init__(self, app):
        super().__init__(app)
        self._loading = False
        self._build()
        self.state.configReplaced.connect(self.refresh)
        self.state.busyChanged.connect(self._busy_changed)

    def _build(self):
        card = Card("Моторы")
        self.left = SliderRow("Левый мотор", 0, 100, 75, "%")
        self.right = SliderRow("Правый мотор", 0, 100, 75, "%")
        self.left.valueChanged.connect(self._save)
        self.right.valueChanged.connect(self._save)
        card.add(self.left)
        card.add(self.right)
        self.add(card)

        card = Card("Виброотклик курков")
        self.lt_check = QCheckBox("Включить виброотклик LT")
        self.rt_check = QCheckBox("Включить виброотклик RT")
        self.lt_check.toggled.connect(self._save)
        self.rt_check.toggled.connect(self._save)
        row = QHBoxLayout()
        row.addWidget(self.lt_check)
        row.addWidget(self.rt_check)
        row.addStretch(1)
        card.add_layout(row)
        self.lt_level = SliderRow("Сила LT", 0, 100, 0, "%")
        self.rt_level = SliderRow("Сила RT", 0, 100, 0, "%")
        self.lt_level.valueChanged.connect(self._save)
        self.rt_level.valueChanged.connect(self._save)
        card.add(self.lt_level)
        card.add(self.rt_level)
        card.add(note("Виброотклик курка срабатывает при нажатии на аналоговый курок. "
                      "Уровень задаётся отдельно от моторов рукояток."))
        self.add(card)

        card = Card("Проверка")
        card.add(muted("Тест отправляет команду вибрации напрямую и не сохраняет "
                       "настройки. Он работает только при подключённом контроллере."))
        row = card.row()
        self.test_button = make_button("Тест обоих моторов", primary=True)
        self.test_button.clicked.connect(lambda: self._test("both"))
        row.addWidget(self.test_button)
        self.test_left = make_button("Только левый")
        self.test_left.clicked.connect(lambda: self._test("left"))
        row.addWidget(self.test_left)
        self.test_right = make_button("Только правый")
        self.test_right.clicked.connect(lambda: self._test("right"))
        row.addWidget(self.test_right)
        row.addStretch(1)
        self.add(card)

        row = QHBoxLayout()
        reset = make_button("Сбросить вибрацию к считанному", danger=True)
        reset.clicked.connect(self._reset)
        row.addWidget(reset)
        row.addStretch(1)
        self.add_layout(row)
        self.add_stretch()

    def _rumble(self) -> dict:
        return self.state.staged.setdefault("rumble", {})

    def refresh(self):
        rumble = self._rumble()
        self._loading = True
        self.left.set_value(rumble.get("left", 75))
        self.right.set_value(rumble.get("right", 75))
        self.lt_check.setChecked(bool(rumble.get("lt_mode", 0)))
        self.rt_check.setChecked(bool(rumble.get("rt_mode", 0)))
        self.lt_level.set_value(rumble.get("lt_level", 0))
        self.rt_level.set_value(rumble.get("rt_level", 0))
        self.lt_level.setEnabled(self.lt_check.isChecked())
        self.rt_level.setEnabled(self.rt_check.isChecked())
        self._loading = False
        self._busy_changed(self.state.busy)

    def _save(self, *_args):
        if self._loading:
            return
        rumble = self._rumble()
        rumble["left"] = self.left.value()
        rumble["right"] = self.right.value()
        rumble["lt_mode"] = 1 if self.lt_check.isChecked() else 0
        rumble["rt_mode"] = 1 if self.rt_check.isChecked() else 0
        rumble["lt_level"] = self.lt_level.value()
        rumble["rt_level"] = self.rt_level.value()
        self.lt_level.setEnabled(self.lt_check.isChecked())
        self.rt_level.setEnabled(self.rt_check.isChecked())
        self.state.touch()

    def _busy_changed(self, busy):
        can = not busy and self.state.device_present and not self.state.access_error
        for button in (self.test_button, self.test_left, self.test_right):
            button.setEnabled(can)

    def _test(self, side: str):
        if not self.state.device_present:
            return
        rumble = self._rumble()
        left = rumble.get("left", 75) if side in ("both", "left") else 0
        right = rumble.get("right", 75) if side in ("both", "right") else 0
        lt = rumble.get("lt_level", 0) if rumble.get("lt_mode") else 0
        rt = rumble.get("rt_level", 0) if rumble.get("rt_mode") else 0

        def job(progress):
            progress("Вибрация…")
            with HidrawDevice() as dev:
                devmod.fire_rumble(dev, left, right, 800, lt, rt)

        self.app.run_task("Тест вибрации", job)
        self.app.log(f"Тест вибрации: L={left} R={right} LT={lt} RT={rt}")

    def _reset(self):
        self.state.restore_key("rumble")
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
