"""Macro editor for the extra buttons."""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QGridLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QTableWidget, QTableWidgetItem,
)

from ...core import keys
from ..labels import SOURCE_LABELS, macro_description, source_label, target_label
from ..widgets import (
    Card, MacroStepDialog, Page, make_button, muted, note,
)


class MacrosPage(Page):
    TITLE = "Макросы"
    SUBTITLE = "До 12 шагов на L4, R4, T1–T3 и C1–C4"

    def __init__(self, app):
        super().__init__(app)
        self._loading = False
        self._steps: list[dict] = []
        self._build()
        self.state.configReplaced.connect(self.refresh)

    def _build(self):
        self.add(note(
            "Макрос заменяет обычное назначение кнопки. Шаги записываются в контроллер "
            "при применении; одновременно можно хранить до 12 шагов на каждую из девяти "
            "кнопок. Единицы времени в прошивке — миллисекунды."
        ))
        layout = QHBoxLayout()
        layout.setSpacing(16)

        left = Card("Кнопки с макросами")
        left.setMinimumWidth(230)
        self.list = QListWidget()
        self.list.setMinimumHeight(440)
        self.list.currentItemChanged.connect(self._selection_changed)
        left.add(self.list)
        left.add(muted("Выберите кнопку, затем добавьте шаги справа."))
        layout.addWidget(left, 1)

        right = Card("Редактор макроса")
        self.title = QLabel("Выберите кнопку")
        self.title.setObjectName("Big")
        right.add(self.title)
        flags = QHBoxLayout()
        self.hold = QCheckBox("Удержание (hold)")
        self.hold.setToolTip("Пока кнопка удерживается, макрос выполняется как удержание")
        self.loop = QCheckBox("Цикл (loop)")
        self.loop.setToolTip("Повторять макрос, пока кнопка удерживается")
        self.hold.toggled.connect(self._flags_changed)
        self.loop.toggled.connect(self._flags_changed)
        flags.addWidget(self.hold)
        flags.addWidget(self.loop)
        flags.addStretch(1)
        right.add_layout(flags)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "Действие", "Нажатие", "Отпускание"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(lambda _index: self._edit_step())
        self.table.itemSelectionChanged.connect(self._selection_changed_buttons)
        self.table.setMinimumHeight(300)
        right.add(self.table)

        row = right.row()
        self.add_button = make_button("Добавить шаг", primary=True)
        self.add_button.clicked.connect(self._add_step)
        row.addWidget(self.add_button)
        self.edit_button = make_button("Изменить")
        self.edit_button.clicked.connect(self._edit_step)
        row.addWidget(self.edit_button)
        self.remove_button = make_button("Удалить")
        self.remove_button.clicked.connect(self._remove_step)
        row.addWidget(self.remove_button)
        self.up_button = make_button("↑")
        self.up_button.setFixedWidth(38)
        self.up_button.clicked.connect(lambda: self._move_step(-1))
        row.addWidget(self.up_button)
        self.down_button = make_button("↓")
        self.down_button.setFixedWidth(38)
        self.down_button.clicked.connect(lambda: self._move_step(1))
        row.addWidget(self.down_button)
        row.addStretch(1)

        row = right.row()
        self.clear_button = make_button("Очистить макрос", danger=True)
        self.clear_button.clicked.connect(self._clear)
        row.addWidget(self.clear_button)
        self.status = muted("")
        row.addWidget(self.status, 1)

        layout.addWidget(right, 3)
        self.add_layout(layout)
        self.add_stretch()
        self._selection_changed_buttons()

    # -- list -------------------------------------------------------------
    def refresh(self):
        selected = self._selected()
        self.list.blockSignals(True)
        self.list.clear()
        macros = self.state.staged.get("macro_settings") or {}
        for name in keys.MACRO_SOURCES:
            item = QListWidgetItem(source_label(name))
            item.setData(Qt.ItemDataRole.UserRole, name)
            if name in macros:
                item.setText(f"{source_label(name)}  ·  {macro_description(macros[name])}")
            self.list.addItem(item)
        self.list.blockSignals(False)
        if selected:
            self.select_button(selected)
        elif self.list.count():
            self.list.setCurrentRow(0)
        else:
            self._load_macro(None)

    def select_button(self, name: str):
        for index in range(self.list.count()):
            item = self.list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == name:
                self.list.setCurrentRow(index)
                return

    def _selected(self) -> str | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selection_changed(self, current, previous):
        self._load_macro(self._selected())

    def _load_macro(self, name: str | None):
        self._loading = True
        self._steps = []
        if name:
            self.title.setText(f"Макрос: {source_label(name)}")
            macro = (self.state.staged.get("macro_settings") or {}).get(name) or {}
            for step in macro.get("steps") or []:
                if len(step) >= 3:
                    self._steps.append({"target": step[0], "press_ms": int(step[1]),
                                        "release_ms": int(step[2])})
            self.hold.setChecked(bool(macro.get("hold")))
            self.loop.setChecked(bool(macro.get("loop")))
        else:
            self.title.setText("Выберите кнопку")
            self.hold.setChecked(False)
            self.loop.setChecked(False)
        self._loading = False
        self._redraw_steps()
        self._update_buttons()

    # -- editor -----------------------------------------------------------
    def _redraw_steps(self):
        self.table.setRowCount(0)
        for index, step in enumerate(self._steps):
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(index + 1)))
            target = QTableWidgetItem(target_label(step.get("target")))
            target.setToolTip(str(step.get("target")))
            self.table.setItem(row, 1, target)
            self.table.setItem(row, 2, QTableWidgetItem(f"{step.get('press_ms', 0)} мс"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{step.get('release_ms', 0)} мс"))
        self.status.setText(f"Шагов: {len(self._steps)} / 12")
        self._selection_changed_buttons()

    def _update_buttons(self):
        has = self._selected() is not None
        self.add_button.setEnabled(has and len(self._steps) < 12)
        self.clear_button.setEnabled(has and bool(self._steps))
        self.hold.setEnabled(has)
        self.loop.setEnabled(has)
        self.table.setEnabled(has)

    def _selection_changed_buttons(self):
        row = self.table.currentRow()
        valid = row is not None and 0 <= row < len(self._steps)
        self.edit_button.setEnabled(valid)
        self.remove_button.setEnabled(valid)
        self.up_button.setEnabled(valid and row > 0)
        self.down_button.setEnabled(valid and row < len(self._steps) - 1)

    def _commit(self):
        if self._loading:
            return
        name = self._selected()
        if not name:
            return
        macros = self.state.staged.setdefault("macro_settings", {})
        mappings = self.state.staged.setdefault("key_mappings", {})
        turbo = self.state.staged.setdefault("turbo_settings", {})
        if self._steps:
            macros[name] = {
                "steps": [[step["target"], step["press_ms"], step["release_ms"]]
                          for step in self._steps],
                "hold": self.hold.isChecked(),
                "loop": self.loop.isChecked(),
            }
            mappings.pop(name, None)
            turbo.pop(name, None)
        else:
            macros.pop(name, None)
        self.state.touch()
        self._update_list_item(name)
        self._update_buttons()

    def _update_list_item(self, name: str):
        macros = self.state.staged.get("macro_settings") or {}
        for index in range(self.list.count()):
            item = self.list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == name:
                if name in macros:
                    item.setText(f"{source_label(name)}  ·  {macro_description(macros[name])}")
                else:
                    item.setText(source_label(name))
                break

    def _flags_changed(self, *_args):
        if self._steps:
            self._commit()

    def _add_step(self):
        if len(self._steps) >= 12:
            QMessageBox.information(self, "Лимит макроса", "Максимум 12 шагов на кнопку.")
            return
        dialog = MacroStepDialog(None, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._steps.append(dialog.step())
            self._redraw_steps()
            self.table.selectRow(len(self._steps) - 1)
            self._commit()

    def _edit_step(self):
        row = self.table.currentRow()
        if not (0 <= row < len(self._steps)):
            return
        dialog = MacroStepDialog(self._steps[row], self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._steps[row] = dialog.step()
            self._redraw_steps()
            self.table.selectRow(row)
            self._commit()

    def _remove_step(self):
        row = self.table.currentRow()
        if not (0 <= row < len(self._steps)):
            return
        del self._steps[row]
        self._redraw_steps()
        if self._steps:
            self.table.selectRow(min(row, len(self._steps) - 1))
        self._commit()

    def _move_step(self, direction: int):
        row = self.table.currentRow()
        target = row + direction
        if not (0 <= row < len(self._steps) and 0 <= target < len(self._steps)):
            return
        self._steps[row], self._steps[target] = self._steps[target], self._steps[row]
        self._redraw_steps()
        self.table.selectRow(target)
        self._commit()

    def _clear(self):
        if not self._selected():
            return
        if QMessageBox.question(self, "Очистить макрос",
                                "Удалить все шаги макроса у выбранной кнопки?") \
                != QMessageBox.StandardButton.Yes:
            return
        self._steps = []
        self._loading = True
        self.hold.setChecked(False)
        self.loop.setChecked(False)
        self._loading = False
        self._redraw_steps()
        self._commit()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
