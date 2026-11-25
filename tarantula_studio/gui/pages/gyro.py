"""Gyroscope configuration page."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QVBoxLayout,
)

from ...core import keys
from ..labels import (
    GYRO_AXIS_LABELS, GYRO_METHOD_LABELS, GYRO_MOTION_LABELS, GYRO_OUTPUT_LABELS,
    SOURCE_ORDER, source_label, target_label,
)
from ..widgets import (
    Card, CurveGroup, Page, SliderRow, TargetEditorDialog, make_button, muted,
    note,
)


class GyroPage(Page):
    TITLE = "Гироскоп"
    SUBTITLE = "Выход, активация, чувствительность и кривая"

    def __init__(self, app):
        super().__init__(app)
        self._loading = False
        self._build()
        self.state.configReplaced.connect(self.refresh)

    def _build(self):
        self.add(note(
            "Гироскоп настраивается независимо от стиков. В режиме «Клавиши» "
            "направления наклона назначаются на четыре зоны; в режиме мыши используются "
            "чувствительность и инверсия ниже."
        ))

        card = Card("Выход гироскопа")
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        self.output = QComboBox()
        for value, label in GYRO_OUTPUT_LABELS.items():
            self.output.addItem(label, value)
        self.motion = QComboBox()
        for value, label in GYRO_MOTION_LABELS.items():
            self.motion.addItem(label, value)
        self.axis_mode = QComboBox()
        for value, label in GYRO_AXIS_LABELS.items():
            self.axis_mode.addItem(label, value)
        self.activate_button = QComboBox()
        for name in SOURCE_ORDER:
            self.activate_button.addItem(source_label(name), name)
        self.activate_method = QComboBox()
        for value, label in GYRO_METHOD_LABELS.items():
            self.activate_method.addItem(label, value)
        fields = [
            ("Выход", self.output), ("Тип движения", self.motion),
            ("Ось", self.axis_mode), ("Кнопка активации", self.activate_button),
            ("Способ активации", self.activate_method),
        ]
        for row, (label, widget) in enumerate(fields):
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(widget, row, 1)
            widget.currentIndexChanged.connect(self._save)
        grid.setColumnStretch(1, 1)
        card.add_layout(grid)

        self.x_sensitivity = SliderRow("Чувствительность X", 0, 100, 50, "%")
        self.y_sensitivity = SliderRow("Чувствительность Y", 0, 100, 50, "%")
        self.overlap = SliderRow("Угол перекрытия", 0, 100, 40, "%")
        self.trigger_range = SliderRow("Диапазон срабатывания курка", 0, 100, 40, "%")
        for widget in (self.x_sensitivity, self.y_sensitivity,
                       self.overlap, self.trigger_range):
            widget.valueChanged.connect(self._save)
            card.add(widget)
        check_row = QHBoxLayout()
        self.invert_x = QCheckBox("Инвертировать X")
        self.invert_y = QCheckBox("Инвертировать Y")
        self.invert_x.toggled.connect(self._save)
        self.invert_y.toggled.connect(self._save)
        check_row.addWidget(self.invert_x)
        check_row.addWidget(self.invert_y)
        check_row.addStretch(1)
        card.add_layout(check_row)
        self.add(card)

        self.directions = QGroupBox("Клавиши направлений (выход «Клавиши»)")
        dgrid = QGridLayout(self.directions)
        dgrid.setContentsMargins(14, 16, 14, 14)
        self._direction_buttons = {}
        for row, (name, label) in enumerate((("up", "Наклон вверх"),
                                             ("down", "Наклон вниз"),
                                             ("left", "Наклон влево"),
                                             ("right", "Наклон вправо"))):
            dgrid.addWidget(QLabel(label), row, 0)
            button = make_button("—")
            button.clicked.connect(lambda _=False, key=name: self._edit_direction(key))
            dgrid.addWidget(button, row, 1)
            self._direction_buttons[name] = button
        dgrid.setColumnStretch(1, 1)
        dgrid.addWidget(muted("Каждой зоне можно назначить клавишу, кнопку, мышь "
                              "или медиа-команду."), 4, 0, 1, 2)
        self.add(self.directions)

        self.curve = CurveGroup("Кривая гироскопа", circle=False, axis_ratio=True)
        self.curve.changed.connect(self._curve_changed)
        self.add(self.curve)

        row = QHBoxLayout()
        reset = make_button("Сбросить гироскоп к считанному", danger=True)
        reset.clicked.connect(self._reset)
        row.addWidget(reset)
        row.addStretch(1)
        self.add_layout(row)
        self.add_stretch()

    def _gyro(self) -> dict:
        return self.state.staged.setdefault("gyro", {})

    def refresh(self):
        gyro = self._gyro()
        self._loading = True
        for combo, key in ((self.output, "output_mode"), (self.motion, "motion_mode"),
                           (self.axis_mode, "axis_mode"),
                           (self.activate_method, "activate_method")):
            index = combo.findData(gyro.get(key))
            combo.setCurrentIndex(max(0, index))
        name = gyro.get("activate_button", "b")
        index = self.activate_button.findData(name)
        if index < 0:
            self.activate_button.addItem(source_label(name), name)
            index = self.activate_button.count() - 1
        self.activate_button.setCurrentIndex(index)
        self.x_sensitivity.set_value(gyro.get("x_sensitivity", 50))
        self.y_sensitivity.set_value(gyro.get("y_sensitivity", 50))
        self.overlap.set_value(gyro.get("overlap_percent", 40))
        self.trigger_range.set_value(gyro.get("output_trigger_range", 40))
        self.invert_x.setChecked(bool(gyro.get("invert_x")))
        self.invert_y.setChecked(bool(gyro.get("invert_y")))
        self.curve.set_config(gyro)
        for name, button in self._direction_buttons.items():
            target = gyro.get(f"kb_{name}")
            button.setText(target_label(target) if target else "Не задано")
            button.setToolTip(str(target or "none"))
        self.directions.setVisible(self.output.currentData() == "keyboard")
        self._loading = False

    def _save(self, *_args):
        if self._loading:
            return
        gyro = self._gyro()
        gyro["output_mode"] = self.output.currentData() or "off"
        gyro["motion_mode"] = self.motion.currentData() or "aim"
        gyro["axis_mode"] = self.axis_mode.currentData() or "yaw"
        gyro["activate_button"] = self.activate_button.currentData() or "b"
        gyro["activate_method"] = self.activate_method.currentData() or "off"
        gyro["x_sensitivity"] = self.x_sensitivity.value()
        gyro["y_sensitivity"] = self.y_sensitivity.value()
        gyro["overlap_percent"] = self.overlap.value()
        gyro["output_trigger_range"] = self.trigger_range.value()
        gyro["invert_x"] = self.invert_x.isChecked()
        gyro["invert_y"] = self.invert_y.isChecked()
        self.directions.setVisible(self.output.currentData() == "keyboard")
        self.state.touch()

    def _curve_changed(self):
        if self._loading:
            return
        gyro = self._gyro()
        self.curve.update_config(gyro)
        self.state.touch()

    def _edit_direction(self, name: str):
        gyro = self._gyro()
        dialog = TargetEditorDialog(gyro.get(f"kb_{name}"), self,
                                    "Назначение направления гироскопа")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        target = dialog.target() or "none"
        gyro[f"kb_{name}"] = target
        button = self._direction_buttons[name]
        button.setText(target_label(target))
        button.setToolTip(target)
        self.state.touch()

    def _reset(self):
        self.state.restore_key("gyro")
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
