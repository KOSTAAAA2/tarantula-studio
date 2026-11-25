"""Buttons page: remapping, turbo and macro entry points."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHeaderView, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QTableWidget, QTableWidgetItem,
)
from PySide6.QtCore import Qt

from ...core import keys
from ..labels import (
    SOURCE_ORDER, macro_description, source_label, target_label,
)
from ..widgets import (
    Card, Page, TargetEditorDialog, TurboDialog, make_button, muted, note,
)


class ButtonsPage(Page):
    TITLE = "Кнопки"
    SUBTITLE = "Переназначение, турбо и макросы на дополнительные кнопки"

    def __init__(self, app):
        super().__init__(app)
        self._rows: dict[str, int] = {}
        self._build()
        self.state.configReplaced.connect(self.refresh)

    def _build(self):
        self.add(note(
            "Макросы поддерживаются только на L4, R4, T1–T3 и C1–C4 (до 12 шагов). "
            "У обычных кнопок можно менять назначение, турбо и режим переключателя."
        ))
        card = Card("Назначения")
        top = card.row()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по кнопке или назначению…")
        self.search.textChanged.connect(self._apply_filter)
        top.addWidget(self.search, 1)
        self.filter = QComboBox()
        self.filter.addItem("Все кнопки", "all")
        self.filter.addItem("Только изменённые", "changed")
        self.filter.addItem("С макросами", "macro")
        self.filter.addItem("С турбо", "turbo")
        self.filter.currentIndexChanged.connect(self._apply_filter)
        top.addWidget(self.filter)
        self.stats = muted("")
        top.addWidget(self.stats)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Кнопка", "Назначение", "Турбо", "Макрос"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(lambda _index: self._edit())
        self.table.itemSelectionChanged.connect(self._selection_changed)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumHeight(440)
        card.add(self.table)

        row = card.row()
        self.edit_button = make_button("Изменить назначение", primary=True)
        self.edit_button.clicked.connect(self._edit)
        row.addWidget(self.edit_button)
        self.reset_button = make_button("Сбросить кнопку")
        self.reset_button.clicked.connect(self._reset)
        row.addWidget(self.reset_button)
        self.turbo_button = make_button("Турбо…")
        self.turbo_button.clicked.connect(self._turbo)
        row.addWidget(self.turbo_button)
        self.macro_button = make_button("Макрос…")
        self.macro_button.clicked.connect(self._macro)
        row.addWidget(self.macro_button)
        row.addStretch(1)
        card.add(muted(
            "Сброс возвращает заводское назначение и удаляет турбо и макрос. "
            "Значения попадут в контроллер только после «Применить» внизу окна."
        ))
        self.add(card)
        self.add_stretch()

    # -- table ------------------------------------------------------------
    def refresh(self):
        selected = self._selected_name()
        mappings = self.state.staged.get("key_mappings") or {}
        turbo = self.state.staged.get("turbo_settings") or {}
        macros = self.state.staged.get("macro_settings") or {}
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self._rows.clear()
        for name in SOURCE_ORDER:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._rows[name] = row
            source_item = QTableWidgetItem(source_label(name))
            source_item.setData(Qt.ItemDataRole.UserRole, name)
            source_item.setFlags(source_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, source_item)
            target = mappings.get(name)
            if name in macros:
                target_text = "Макрос"
            elif target:
                target_text = target_label(target)
            else:
                target_text = "Заводское"
            target_item = QTableWidgetItem(target_text)
            target_item.setToolTip(str(target or "заводское назначение"))
            self.table.setItem(row, 1, target_item)
            turbo_value = turbo.get(name)
            turbo_item = QTableWidgetItem(
                f"{turbo_value.get('rate', 10)} Гц" + (" · toggle" if turbo_value.get("continuous") else "")
                if turbo_value else "—"
            )
            self.table.setItem(row, 2, turbo_item)
            macro_item = QTableWidgetItem(macro_description(macros.get(name)) if name in macros else "—")
            self.table.setItem(row, 3, macro_item)
            if target or name in macros:
                for column in range(4):
                    item = self.table.item(row, column)
                    item.setForeground(Qt.GlobalColor.white)
        self.table.blockSignals(False)
        if selected in self._rows:
            self.table.selectRow(self._rows[selected])
        self._update_stats()
        self._apply_filter()
        self._selection_changed()

    def _selected_name(self) -> str | None:
        items = self.table.selectedItems()
        if not items:
            return None
        return self.table.item(items[0].row(), 0).data(Qt.ItemDataRole.UserRole)

    def _selection_changed(self):
        name = self._selected_name()
        enabled = name is not None
        self.edit_button.setEnabled(enabled)
        self.reset_button.setEnabled(enabled)
        self.turbo_button.setEnabled(enabled)
        self.macro_button.setEnabled(enabled and name in keys.MACRO_SOURCES)
        if name and name not in keys.MACRO_SOURCES:
            self.macro_button.setToolTip("Макросы доступны только на L4, R4, T1–T3, C1–C4")
        else:
            self.macro_button.setToolTip("")

    def _update_stats(self):
        mappings = self.state.staged.get("key_mappings") or {}
        macros = self.state.staged.get("macro_settings") or {}
        turbo = self.state.staged.get("turbo_settings") or {}
        self.stats.setText(f"Изменено {len(mappings)} · макросов {len(macros)} · турбо {len(turbo)}")

    def _apply_filter(self):
        text = self.search.text().strip().lower()
        mode = self.filter.currentData() or "all"
        mappings = self.state.staged.get("key_mappings") or {}
        macros = self.state.staged.get("macro_settings") or {}
        turbo = self.state.staged.get("turbo_settings") or {}
        for name, row in self._rows.items():
            mapping = mappings.get(name)
            visible = True
            if mode == "changed" and not (mapping or name in macros or name in turbo):
                visible = False
            elif mode == "macro" and name not in macros:
                visible = False
            elif mode == "turbo" and name not in turbo:
                visible = False
            if text:
                haystack = " ".join((
                    name, source_label(name), str(mapping or ""),
                    target_label(mapping) if mapping else "",
                )).lower()
                if text not in haystack:
                    visible = False
            self.table.setRowHidden(row, not visible)

    # -- actions ----------------------------------------------------------
    def _edit(self):
        name = self._selected_name()
        if not name:
            return
        mappings = self.state.staged.setdefault("key_mappings", {})
        macros = self.state.staged.setdefault("macro_settings", {})
        turbo = self.state.staged.setdefault("turbo_settings", {})
        if name in macros:
            answer = QMessageBox.question(
                self, "Заменить макрос?",
                f"У кнопки {source_label(name)} настроен макрос. "
                "Назначение заменит макрос. Продолжить?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        dialog = TargetEditorDialog(mappings.get(name), self,
                                    f"Назначение: {source_label(name)}")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        target = dialog.target()
        macros.pop(name, None)
        if target is None:
            mappings.pop(name, None)
            turbo.pop(name, None)
        elif target == "none":
            mappings[name] = "none"
            turbo.pop(name, None)
        else:
            mappings[name] = target
        self.state.touch()
        self.refresh()

    def _reset(self):
        name = self._selected_name()
        if not name:
            return
        for key in ("key_mappings", "turbo_settings", "macro_settings"):
            (self.state.staged.get(key) or {}).pop(name, None)
        self.state.touch()
        self.refresh()

    def _turbo(self):
        name = self._selected_name()
        if not name:
            return
        mappings = self.state.staged.setdefault("key_mappings", {})
        macros = self.state.staged.get("macro_settings") or {}
        if name in macros:
            QMessageBox.information(self, "Макрос", "Для кнопки с макросом турбо недоступно.")
            return
        target = mappings.get(name)
        if not target or target == "none":
            QMessageBox.information(self, "Сначала назначение",
                                    "Сначала назначьте кнопке действие.")
            return
        turbo = self.state.staged.setdefault("turbo_settings", {})
        dialog = TurboDialog(turbo.get(name), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        settings = dialog.result_settings()
        if settings:
            turbo[name] = settings
        else:
            turbo.pop(name, None)
        self.state.touch()
        self.refresh()

    def _macro(self):
        name = self._selected_name()
        if name and name in keys.MACRO_SOURCES:
            self.app.navigate("macros")
            page = self.app.pages.get("macros")
            if page:
                page.select_button(name)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
