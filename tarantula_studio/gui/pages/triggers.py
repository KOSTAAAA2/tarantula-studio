"""Triggers page: hair trigger and response curves."""
from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget

from ..labels import HAIR_LABELS
from ..widgets import Card, CurveGroup, Page, SliderRow, make_button, note


class TriggerTab(QWidget):
    def __init__(self, app, side: int, parent=None):
        super().__init__(parent)
        self.app = app
        self.state = app.state
        self.key = "trigger_right" if side else "trigger_left"
        self._loading = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(14)

        card = Card("Быстрый курок (hair trigger)")
        row = card.row()
        row.addWidget(QLabel("Режим"))
        self.hair = QComboBox()
        for value, label in HAIR_LABELS.items():
            self.hair.addItem(label, value)
        self.hair.currentIndexChanged.connect(self._save)
        row.addWidget(self.hair, 1)
        self.begin = SliderRow("Порог срабатывания", 0, 100, 10, "%", 180)
        self.end = SliderRow("Порог отпускания", 0, 100, 20, "%", 180)
        self.begin.valueChanged.connect(self._save)
        self.end.valueChanged.connect(self._save)
        card.add(self.begin)
        card.add(self.end)
        card.add(note("Адаптивный режим подстраивает порог под скорость нажатия, "
                      "фиксированный использует значения выше. Линейный режим "
                      "отключает быстрый курок."))
        layout.addWidget(card)

        self.curve = CurveGroup("Кривая курка", circle=False, axis_ratio=False)
        self.curve.changed.connect(self._curve_changed)
        layout.addWidget(self.curve)

        row = QHBoxLayout()
        reset = make_button("Сбросить курок к считанному", danger=True)
        reset.clicked.connect(self._reset)
        row.addWidget(reset)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)

    def refresh(self):
        trigger = self.state.staged.get(self.key) or {}
        self._loading = True
        index = self.hair.findData(trigger.get("hair_mode", "off"))
        self.hair.setCurrentIndex(max(0, index))
        self.begin.set_value(trigger.get("hair_trigger_begin", 10))
        self.end.set_value(trigger.get("hair_trigger_end", 20))
        self.curve.set_config(trigger)
        self._loading = False

    def _save(self, *_args):
        if self._loading:
            return
        trigger = self.state.staged.setdefault(self.key, {})
        trigger["hair_mode"] = self.hair.currentData() or "off"
        trigger["hair_trigger_begin"] = self.begin.value()
        trigger["hair_trigger_end"] = self.end.value()
        self.state.touch()

    def _curve_changed(self):
        if self._loading:
            return
        trigger = self.state.staged.setdefault(self.key, {})
        self.curve.update_config(trigger)
        self.state.touch()

    def _reset(self):
        self.state.restore_key(self.key)
        self.refresh()


class TriggersPage(Page):
    TITLE = "Курки"
    SUBTITLE = "Быстрый курок, мёртвые зоны и кривые LT/RT"

    def __init__(self, app):
        super().__init__(app)
        self.tabs = QTabWidget()
        self.left = TriggerTab(app, 0)
        self.right = TriggerTab(app, 1)
        self.tabs.addTab(self.left, "LT — левый курок")
        self.tabs.addTab(self.right, "RT — правый курок")
        self.add(self.tabs)
        self.add_stretch()
        self.state.configReplaced.connect(self.refresh)

    def refresh(self):
        self.left.refresh()
        self.right.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
