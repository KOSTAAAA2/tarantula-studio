"""Lighting page: mode, brightness, speed and per-zone colors."""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout,
)

from ..labels import LIGHT_MODE_LABELS
from ..widgets import (
    Card, ColorButton, Page, SliderRow, make_button, muted, note,
)


class LightingPage(Page):
    TITLE = "Подсветка"
    SUBTITLE = "Режим, яркость, скорость и цвета зон"

    def __init__(self, app):
        super().__init__(app)
        self._loading = False
        self._build()
        self.state.configReplaced.connect(self.refresh)

    def _build(self):
        card = Card("Параметры подсветки")
        row = card.row()
        row.addWidget(QLabel("Режим"))
        self.mode = QComboBox()
        for value, label in LIGHT_MODE_LABELS.items():
            self.mode.addItem(label, value)
        self.mode.currentIndexChanged.connect(self._save)
        row.addWidget(self.mode, 1)
        self.brightness = SliderRow("Яркость", 0, 100, 50, "%")
        self.speed = SliderRow("Скорость анимации", 0, 100, 50, "%")
        self.brightness.valueChanged.connect(self._save)
        self.speed.valueChanged.connect(self._save)
        card.add(self.brightness)
        card.add(self.speed)
        card.add(note("Для панели (Panel) официальная прошивка использует значение "
                      "яркости как яркость цвета, поэтому отдельный цвет панели может "
                      "перезаписываться при применении."))
        self.add(card)

        colors = Card("Цвета зон")
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)
        self.panel = ColorButton([240, 100, 50])
        self.home = ColorButton([0, 0, 100])
        grid.addWidget(QLabel("Панель (Panel)"), 0, 0)
        grid.addWidget(self.panel, 0, 1)
        grid.addWidget(QLabel("Home"), 1, 0)
        grid.addWidget(self.home, 1, 1)
        self.panel.changed.connect(lambda hsv: self._color_changed("panel_hsv", hsv))
        self.home.changed.connect(lambda hsv: self._color_changed("home_hsv", hsv))

        self.abxy: list[ColorButton] = []
        self.bayx: list[ColorButton] = []
        for row_index, (title, labels, store, key) in enumerate((
                ("ABXY (Xbox)", ["A", "B", "X", "Y"], self.abxy, "abxy_hsv"),
                ("BAYX (Switch)", ["B", "A", "Y", "X"], self.bayx, "bayx_hsv"))):
            base = 2 + row_index * 2
            label = QLabel(title)
            label.setObjectName("SectionLabel")
            grid.addWidget(label, base, 0, 1, 5)
            for index, name in enumerate(labels):
                column = 1 + index
                header = QLabel(name)
                header.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                grid.addWidget(header, base + 1, column)
                button = ColorButton([0, 0, 6])
                button.changed.connect(
                    lambda hsv, k=key, idx=index: self._color_list_changed(k, idx, hsv)
                )
                grid.addWidget(button, base + 2, column)
                store.append(button)
        grid.setColumnStretch(5, 1)
        colors.add_layout(grid)
        row = colors.row()
        preset = make_button("Стандартные цвета")
        preset.clicked.connect(self._preset)
        row.addWidget(preset)
        row.addStretch(1)
        colors.add(muted("Цвета задаются в HSV. Кнопка «Стандартные цвета» возвращает "
                         "заводские оттенки A/B/X/Y."))
        self.add(colors)

        row = QHBoxLayout()
        reset = make_button("Сбросить подсветку к считанному", danger=True)
        reset.clicked.connect(self._reset)
        row.addWidget(reset)
        row.addStretch(1)
        self.add_layout(row)
        self.add_stretch()

    def _lighting(self) -> dict:
        return self.state.staged.setdefault("lighting", {})

    def _valid_hsv(self, value, fallback):
        try:
            if not isinstance(value, (list, tuple)) or len(value) < 3:
                return list(fallback)
            return [int(value[0]) % 360 if int(value[0]) >= 360 else max(0, int(value[0])),
                    max(0, min(100, int(value[1]))),
                    max(0, min(100, int(value[2])))]
        except (TypeError, ValueError):
            return list(fallback)

    def refresh(self):
        lighting = self._lighting()
        self._loading = True
        index = self.mode.findData(lighting.get("lighting_mode", "colorful"))
        self.mode.setCurrentIndex(max(0, index))
        self.brightness.set_value(lighting.get("brightness", 50))
        self.speed.set_value(lighting.get("lighting_speed", 50))
        self.panel.set_hsv(self._valid_hsv(lighting.get("panel_hsv"), [240, 100, 50]))
        self.home.set_hsv(self._valid_hsv(lighting.get("home_hsv"), [0, 0, 100]))
        for store, key in ((self.abxy, "abxy_hsv"), (self.bayx, "bayx_hsv")):
            colors = lighting.get(key) or []
            for index, button in enumerate(store):
                fallback = [0, 0, 6]
                button.set_hsv(self._valid_hsv(colors[index] if index < len(colors) else fallback,
                                               fallback))
        self._loading = False

    def _save(self, *_args):
        if self._loading:
            return
        lighting = self._lighting()
        lighting["lighting_mode"] = self.mode.currentData() or "colorful"
        lighting["brightness"] = self.brightness.value()
        lighting["lighting_speed"] = self.speed.value()
        self.state.touch()

    def _color_changed(self, key: str, hsv):
        if self._loading:
            return
        self._lighting()[key] = list(hsv)
        self.state.touch()

    def _color_list_changed(self, key: str, index: int, hsv):
        if self._loading:
            return
        lighting = self._lighting()
        colors = list(lighting.get(key) or [[0, 0, 6] for _ in range(4)])
        while len(colors) < 4:
            colors.append([0, 0, 6])
        colors[index] = list(hsv)
        lighting[key] = colors
        self.state.touch()

    def _preset(self):
        from ...core.defaults import lighting_defaults
        defaults = lighting_defaults()
        self._loading = True
        for store, key in ((self.abxy, "abxy_hsv"), (self.bayx, "bayx_hsv")):
            colors = defaults[key]
            for index, button in enumerate(store):
                button.set_hsv(colors[index])
        self._loading = False
        self._lighting()["abxy_hsv"] = copy.deepcopy(defaults["abxy_hsv"])
        self._lighting()["bayx_hsv"] = copy.deepcopy(defaults["bayx_hsv"])
        self.state.touch()

    def _reset(self):
        self.state.restore_key("lighting")
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
