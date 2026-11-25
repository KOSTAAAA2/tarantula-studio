"""Sticks page: mode, curve geometry and wheel-mode key zones."""
from __future__ import annotations

import copy

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from ...core import keys
from ..labels import STICK_MODE_LABELS, target_label
from ..widgets import (
    Card, CurveGroup, Page, SliderRow, TargetEditorDialog, make_button, muted,
    note,
)


class StickTab(QWidget):
    def __init__(self, app, side: int, parent=None):
        super().__init__(parent)
        self.app = app
        self.state = app.state
        self.side = side
        self.key = "stick_right" if side else "stick_left"
        self._loading = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(14)

        card = Card("Основные параметры")
        row = card.row()
        row.addWidget(QLabel("Режим стика"))
        self.mode = QComboBox()
        for value, label in STICK_MODE_LABELS.items():
            self.mode.addItem(label, value)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        row.addWidget(self.mode, 1)

        self.overlap = SliderRow("Угол перекрытия", 0, 100, 40, "%", 170)
        self.overlap.valueChanged.connect(self._save)
        card.add(self.overlap)
        self.invert_x = QCheckBox("Инвертировать ось X")
        self.invert_y = QCheckBox("Инвертировать ось Y")
        self.invert_x.toggled.connect(self._save)
        self.invert_y.toggled.connect(self._save)
        check_row = QHBoxLayout()
        check_row.addWidget(self.invert_x)
        check_row.addWidget(self.invert_y)
        check_row.addStretch(1)
        card.add_layout(check_row)

        self.dpi_x = SliderRow("DPI мыши по X", 0, 255, 50, label_width=150)
        self.dpi_y = SliderRow("DPI мыши по Y", 0, 255, 50, label_width=150)
        self.dpi_x.valueChanged.connect(self._save)
        self.dpi_y.valueChanged.connect(self._save)
        card.add(self.dpi_x)
        card.add(self.dpi_y)
        self.dpi_note = note(
            "DPI используется только в режиме «Мышь (HID)». Значения выше 100 — "
            "экспериментальные; проверьте обратное чтение на странице «Мышь и DPI»."
        )
        card.add(self.dpi_note)
        layout.addWidget(card)

        self.curve = CurveGroup("Геометрия и кривая", circle=True, axis_ratio=True)
        self.curve.changed.connect(self._curve_changed)
        layout.addWidget(self.curve)

        self.wheel = self._build_wheel_group()
        layout.addWidget(self.wheel)

        row = QHBoxLayout()
        reset = make_button("Сбросить стик к считанному", danger=True)
        reset.clicked.connect(self._reset)
        row.addWidget(reset)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
        self._refresh_wheel()

    def _build_wheel_group(self) -> QGroupBox:
        group = QGroupBox("Клавиши режима «Wheel»")
        grid = QGridLayout(group)
        grid.setContentsMargins(14, 16, 14, 14)
        grid.setSpacing(6)
        self._zone_buttons: dict[str, QPushButton] = {}
        self._zone_reset: dict[str, QPushButton] = {}
        labels = {"left": "Внутренняя ←", "right": "Внутренняя →",
                  "up": "Внутренняя ↑", "down": "Внутренняя ↓"}
        for row, name in enumerate(("left", "right", "up", "down")):
            grid.addWidget(QLabel(labels[name]), row, 0)
            button = make_button("—")
            button.clicked.connect(lambda _=False, key=name: self._edit_zone(key))
            grid.addWidget(button, row, 1)
            self._zone_buttons[name] = button
        row = 4
        grid.addWidget(QLabel("Внешнее кольцо"), row, 0)
        outline = make_button("—")
        outline.clicked.connect(lambda: self._edit_zone("outline"))
        grid.addWidget(outline, row, 1)
        self._zone_buttons["outline"] = outline

        row += 1
        override_title = QLabel("Отдельные зоны внешнего кольца (необязательно)")
        override_title.setObjectName("SectionLabel")
        grid.addWidget(override_title, row, 0, 1, 3)
        for index, name in enumerate(("left", "right", "up", "down")):
            row += 1
            grid.addWidget(QLabel(f"Кольцо {labels[name].split(' ', 1)[1]}"), row, 0)
            button = make_button("—")
            button.clicked.connect(lambda _=False, key=name: self._edit_zone(f"{key}_outer"))
            grid.addWidget(button, row, 1)
            self._zone_buttons[f"{name}_outer"] = button
            reset = make_button("↺")
            reset.setToolTip("Использовать общее значение внешнего кольца")
            reset.setFixedWidth(36)
            reset.clicked.connect(lambda _=False, key=name: self._clear_outer(key))
            grid.addWidget(reset, row, 2)
            self._zone_reset[name] = reset
        grid.setColumnStretch(1, 1)
        grid.addWidget(muted(
            "Эти назначения записываются, когда стик переключён в режим «Клавиши по "
            "зонам». Для внутренних зон и кольца можно выбрать клавишу, кнопку "
            "контроллера, мышь или медиа-команду."
        ), row + 1, 0, 1, 3)
        return group

    # -- data -------------------------------------------------------------
    def refresh(self):
        stick = self.state.staged.get(self.key) or {}
        self._loading = True
        index = self.mode.findData(stick.get("mode", "native"))
        self.mode.setCurrentIndex(max(0, index))
        self.overlap.set_value(stick.get("overlap_percent", 40))
        self.invert_x.setChecked(bool(stick.get("invert_x", False)))
        self.invert_y.setChecked(bool(stick.get("invert_y", False)))
        self.dpi_x.set_value(stick.get("mouse_dpi", 50))
        self.dpi_y.set_value(stick.get("mouse_dpi_y", stick.get("mouse_dpi", 50)))
        self.curve.set_config(stick)
        self._loading = False
        self.dpi_note.setVisible(self.mode.currentData() != "mouse"
                                 or self.dpi_x.value() > 100 or self.dpi_y.value() > 100)
        self._refresh_wheel()
        self.wheel.setVisible(self.mode.currentData() == "wheel")

    def _mode_changed(self, *_args):
        if self._loading:
            return
        self._save()
        self.wheel.setVisible(self.mode.currentData() == "wheel")
        self.dpi_note.setVisible(self.mode.currentData() != "mouse"
                                 or self.dpi_x.value() > 100 or self.dpi_y.value() > 100)

    def _save(self, *_args):
        if self._loading:
            return
        stick = self.state.staged.setdefault(self.key, {})
        stick["mode"] = self.mode.currentData() or "native"
        stick["overlap_percent"] = self.overlap.value()
        stick["invert_x"] = self.invert_x.isChecked()
        stick["invert_y"] = self.invert_y.isChecked()
        stick["mouse_dpi"] = self.dpi_x.value()
        stick["mouse_dpi_y"] = self.dpi_y.value()
        self.state.touch()

    def _curve_changed(self):
        if self._loading:
            return
        stick = self.state.staged.setdefault(self.key, {})
        self.curve.update_config(stick)
        self.state.touch()

    def _refresh_wheel(self):
        stick = self.state.staged.get(self.key) or {}
        keyboard = stick.get("keyboard") or {}
        for name in ("left", "right", "up", "down"):
            target = keyboard.get(name)
            self._zone_buttons[name].setText(target_label(target) if target else "Не задано")
            self._zone_buttons[name].setToolTip(str(target or "none"))
        outline = keyboard.get("outline")
        self._zone_buttons["outline"].setText(target_label(outline) if outline else "Не задано")
        self._zone_buttons["outline"].setToolTip(str(outline or "none"))
        for name in ("left", "right", "up", "down"):
            override = keyboard.get(f"{name}_outer")
            button = self._zone_buttons[f"{name}_outer"]
            button.setText(target_label(override) if override else "Как у кольца")
            button.setToolTip(str(override or outline or "none"))
            self._zone_reset[name].setEnabled(bool(override))

    def _edit_zone(self, key: str):
        stick = self.state.staged.setdefault(self.key, {})
        keyboard = stick.setdefault("keyboard", {})
        current = keyboard.get(key)
        if key.endswith("_outer") and not current:
            current = keyboard.get("outline")
        dialog = TargetEditorDialog(current, self, "Назначение зоны стика")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        target = dialog.target() or "none"
        keyboard[key] = target
        self._refresh_wheel()
        self.state.touch()

    def _clear_outer(self, name: str):
        stick = self.state.staged.setdefault(self.key, {})
        keyboard = stick.setdefault("keyboard", {})
        keyboard[f"{name}_outer"] = ""
        self._refresh_wheel()
        self.state.touch()

    def _reset(self):
        self.state.restore_key(self.key)
        self.refresh()


class SticksPage(Page):
    TITLE = "Стики"
    SUBTITLE = "Режимы, мёртвые зоны, кривые и клавиши wheel-режима"

    def __init__(self, app):
        super().__init__(app)
        self.add(note(
            "Кривые и мёртвые зоны применяются к физическому стику. Режим мыши "
            "включается на этой странице или на странице «Мышь и DPI»."
        ))
        self.tabs = QTabWidget()
        self.left = StickTab(app, 0)
        self.right = StickTab(app, 1)
        self.tabs.addTab(self.left, "Левый стик (LS)")
        self.tabs.addTab(self.right, "Правый стик (RS)")
        self.add(self.tabs)
        self.add_stretch()
        self.state.configReplaced.connect(self.refresh)
        self.tabs.currentChanged.connect(lambda _: self.refresh())

    def refresh(self):
        self.left.refresh()
        self.right.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
