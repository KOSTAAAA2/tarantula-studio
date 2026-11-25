"""D-pad and layout page."""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel

from ..labels import (
    DPAD_SWAP_LABELS, DPAD_TYPE_LABELS, LAYOUT_LABELS, SOURCE_ORDER, source_label,
)
from ..widgets import Card, Page, make_button, muted, note


class DpadPage(Page):
    TITLE = "D-Pad и раскладка"
    SUBTITLE = "Режим крестовины, swap, ABXY/BAYX и авто-калибровка"

    def __init__(self, app):
        super().__init__(app)
        self._loading = False
        self._build()
        self.state.configReplaced.connect(self.refresh)

    def _build(self):
        card = Card("Крестовина и раскладка")
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        self.dpad_type = QComboBox()
        for value, label in DPAD_TYPE_LABELS.items():
            self.dpad_type.addItem(label, value)
        self.swap = QComboBox()
        for value, label in DPAD_SWAP_LABELS.items():
            self.swap.addItem(label, value)
        self.layout = QComboBox()
        for value, label in LAYOUT_LABELS.items():
            self.layout.addItem(label, value)
        self.macro_switch = QComboBox()
        self.macro_switch.addItem("Нет", "none")
        for name in SOURCE_ORDER:
            self.macro_switch.addItem(source_label(name), name)
        fields = [("Тип D-Pad", self.dpad_type), ("Swap", self.swap),
                  ("Раскладка", self.layout), ("Кнопка переключения макросов", self.macro_switch)]
        for row, (label, widget) in enumerate(fields):
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(widget, row, 1)
            widget.currentIndexChanged.connect(self._save)
        grid.setColumnStretch(1, 1)
        card.add_layout(grid)

        self.auto = QCheckBox("Auto On/Off (автоматическое включение контроллера)")
        self.fast = QCheckBox("Fast Trigger (авто-калибровка курков)")
        self.auto.toggled.connect(self._save)
        self.fast.toggled.connect(self._save)
        card.add(self.auto)
        card.add(self.fast)
        card.add(note("Auto On/Off и Fast Trigger в протоколе инвертированы: "
                      "включённый флажок записывается как 0. Приложение скрывает эту "
                      "деталь и показывает привычные переключатели."))
        self.add(card)

        self.add(muted("Изменение раскладки ABXY/BAYX влияет на подписи кнопок в играх, "
                       "но не переназначает физические кнопки. Для смены мест A/B и X/Y "
                       "используйте переназначение на странице «Кнопки»."))

        row = QHBoxLayout()
        reset = make_button("Сбросить D-Pad к считанному", danger=True)
        reset.clicked.connect(self._reset)
        row.addWidget(reset)
        row.addStretch(1)
        self.add_layout(row)
        self.add_stretch()

    def _dpad(self) -> dict:
        return self.state.staged.setdefault("dpad", {})

    def refresh(self):
        dpad = self._dpad()
        self._loading = True
        for combo, key, fallback in (
                (self.dpad_type, "dpad_type", "8way"),
                (self.swap, "swap", "off"),
                (self.layout, "layout", "xbox")):
            index = combo.findData(dpad.get(key, fallback))
            combo.setCurrentIndex(max(0, index))
        switch = dpad.get("macro_switch", "none")
        index = self.macro_switch.findData(switch)
        if index < 0:
            self.macro_switch.addItem(source_label(switch), switch)
            index = self.macro_switch.count() - 1
        self.macro_switch.setCurrentIndex(index)
        self.auto.setChecked(bool(dpad.get("auto_onoff", True)))
        self.fast.setChecked(bool(dpad.get("fast_trigger", True)))
        self._loading = False

    def _save(self, *_args):
        if self._loading:
            return
        dpad = self._dpad()
        dpad["dpad_type"] = self.dpad_type.currentData() or "8way"
        dpad["swap"] = self.swap.currentData() or "off"
        dpad["layout"] = self.layout.currentData() or "xbox"
        dpad["macro_switch"] = self.macro_switch.currentData() or "none"
        dpad["auto_onoff"] = self.auto.isChecked()
        dpad["fast_trigger"] = self.fast.isChecked()
        self.state.touch()

    def _reset(self):
        self.state.restore_key("dpad")
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
