"""Diagnostics: hidraw permissions, udev rule and logs."""
from __future__ import annotations

import os
import shlex
import shutil
import tempfile
from datetime import datetime

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QMessageBox, QPlainTextEdit, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ...core import mouse
from ...core.transport import (
    diagnose, list_hidraw, udev_rule_text,
)
from ..widgets import Card, Page, make_button, muted, note, set_pill


class DiagnosticsPage(Page):
    TITLE = "Диагностика"
    SUBTITLE = "Права hidraw, udev-правило, узлы мыши и журнал"

    def __init__(self, app):
        super().__init__(app)
        self._process = None
        self._build()
        self.state.deviceChanged.connect(self.refresh)
        self.state.statusMessage.connect(self.append_log)

    def _build(self):
        card = Card("Состояние")
        row = card.row()
        self.root_pill = QLabel()
        self.rule_pill = QLabel()
        self.device_pill = QLabel()
        row.addWidget(self.root_pill)
        row.addWidget(self.rule_pill)
        row.addWidget(self.device_pill)
        row.addStretch(1)
        refresh = make_button("Обновить")
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh)
        self.summary = muted("")
        card.add(self.summary)
        self.add(card)

        card = Card("hidraw-устройства")
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Узел", "VID:PID", "Продукт", "Config reports", "Доступ"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(190)
        header = self.table.horizontalHeader()
        from PySide6.QtWidgets import QHeaderView
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        card.add(self.table)
        card.add(muted("Нужен узел с VID 3537, поддерживаемым PID и отчётами 06/07. "
                       "В режиме донгла это обычно единственный интерфейс конфигурации."))
        self.add(card)

        card = Card("udev-правило")
        card.add(muted("Правило даёт активному пользователю доступ к hidraw и input "
                       "без запуска приложения от root. После установки подключите "
                       "контроллер заново."))
        self.rule_edit = QPlainTextEdit()
        self.rule_edit.setReadOnly(True)
        self.rule_edit.setPlainText(udev_rule_text())
        self.rule_edit.setMaximumHeight(90)
        card.add(self.rule_edit)
        row = card.row()
        copy = make_button("Копировать")
        copy.clicked.connect(self._copy_rule)
        row.addWidget(copy)
        save = make_button("Сохранить в файл…")
        save.clicked.connect(self._save_rule)
        row.addWidget(save)
        self.install_button = make_button("Установить правило", primary=True)
        self.install_button.clicked.connect(self._install_rule)
        row.addWidget(self.install_button)
        row.addStretch(1)
        self.rule_path = muted("")
        card.add(self.rule_path)
        self.add(card)

        card = Card("Узлы мыши для проверки DPI")
        self.mouse_list = QListWidget()
        self.mouse_list.setMinimumHeight(100)
        card.add(self.mouse_list)
        row = card.row()
        open_mouse = make_button("Открыть «Мышь и DPI»")
        open_mouse.clicked.connect(lambda: self.app.navigate("mouse"))
        row.addWidget(open_mouse)
        row.addStretch(1)
        self.add(card)

        card = Card("Журнал")
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.document().setMaximumBlockCount(600)
        self.log_edit.setMinimumHeight(160)
        card.add(self.log_edit)
        row = card.row()
        clear = make_button("Очистить журнал")
        clear.clicked.connect(self.log_edit.clear)
        row.addWidget(clear)
        row.addStretch(1)
        self.add(card)
        self.add_stretch()

    # -- data -------------------------------------------------------------
    def refresh(self):
        diag = diagnose()
        set_pill(self.root_pill, "root" if diag["is_root"] else "не root",
                 "ok" if diag["is_root"] else "muted")
        set_pill(self.rule_pill, "udev: установлено" if diag["rule_installed"]
                 else "udev: не установлено",
                 "ok" if diag["rule_installed"] else "warn")
        selected = diag["selected"]
        if selected:
            set_pill(self.device_pill, "контроллер найден", "ok")
        else:
            set_pill(self.device_pill, "контроллер не найден", "muted")

        if diag["udev_files"]:
            self.rule_path.setText("Файлы правил: " + ", ".join(diag["udev_files"]))
        else:
            self.rule_path.setText("Файлы правил не найдены в /etc/udev/rules.d.")
        self.install_button.setEnabled(shutil.which("pkexec") is not None)

        if selected:
            access = "rw" if selected.readable and selected.writable else "нет доступа"
            self.summary.setText(
                f"Выбран: {selected.path} · {selected.product} · config reports: "
                f"{'да' if selected.has_config_reports else 'нет'} · доступ: {access}"
            )
        else:
            self.summary.setText(
                "Поддерживаемый интерфейс конфигурации не найден. Подключите "
                "контроллер по USB в режиме PC/XInput и нажмите «Обновить»."
            )

        nodes = list_hidraw()
        self.table.setRowCount(0)
        for node in nodes:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                node.path,
                f"{node.vid:04x}:{node.pid:04x}",
                node.product,
                "да" if node.has_config_reports else "нет",
                "rw" if node.readable and node.writable else
                "r" if node.readable else "—",
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        if not nodes:
            self.table.insertRow(0)
            self.table.setItem(0, 0, QTableWidgetItem("hidraw-устройств нет"))

        self.mouse_list.clear()
        mouse_nodes = mouse.find_mouse_nodes()
        for node in mouse_nodes:
            self.mouse_list.addItem(node.describe())
        if not mouse_nodes:
            self.mouse_list.addItem("Интерфейс мыши GameSir не найден.")

    # -- rule actions -----------------------------------------------------
    def _copy_rule(self):
        QApplication.clipboard().setText(udev_rule_text())
        self.app.log("udev-правило скопировано в буфер обмена.")

    def _save_rule(self):
        path, _filter = QFileDialog.getSaveFileName(
            self, "Сохранить udev-правило", "70-gamesir-tarantula.rules",
            "udev rules (*.rules);;Все файлы (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(udev_rule_text())
        except OSError as exc:
            QMessageBox.warning(self, "udev", str(exc))
            return
        self.app.log(f"udev-правило сохранено: {path}")

    def _install_rule(self):
        if shutil.which("pkexec") is None:
            QMessageBox.information(
                self, "pkexec не найден",
                "Установите polkit/pkexec или скопируйте правило в "
                "/etc/udev/rules.d/ вручную от root.")
            return
        if QMessageBox.question(
                self, "Установить udev-правило",
                "Будет создан файл /etc/udev/rules.d/70-gamesir-tarantula.rules "
                "и перезагружены правила udev. Продолжить?") \
                != QMessageBox.StandardButton.Yes:
            return
        try:
            handle, temp_path = tempfile.mkstemp(prefix="tarantula-", suffix=".rules")
            with os.fdopen(handle, "w", encoding="utf-8") as fh:
                fh.write(udev_rule_text())
        except OSError as exc:
            QMessageBox.warning(self, "udev", str(exc))
            return
        command = (
            f"install -m 644 {shlex.quote(temp_path)} "
            "/etc/udev/rules.d/70-gamesir-tarantula.rules && "
            "udevadm control --reload-rules && "
            "udevadm trigger --subsystem-match=hidraw --action=change && "
            f"rm -f {shlex.quote(temp_path)}"
        )
        self.install_button.setEnabled(False)
        self._process = QProcess(self)
        self._process.finished.connect(
            lambda code, status: self._install_finished(code, status, temp_path))
        self._process.errorOccurred.connect(self._install_error)
        self._process.start("pkexec", ["sh", "-c", command])

    def _install_error(self, _error):
        self.install_button.setEnabled(True)
        QMessageBox.warning(self, "udev", "Не удалось запустить pkexec.")

    def _install_finished(self, code, _status, temp_path):
        self.install_button.setEnabled(True)
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        self._process = None
        if code == 0:
            self.app.log("udev-правило установлено. Подключите контроллер заново.")
            QMessageBox.information(
                self, "Готово",
                "Правило установлено. Отключите и снова подключите контроллер, "
                "затем нажмите «Обновить» или «Считать с контроллера».")
        else:
            self.app.log(f"Установка udev-правила завершилась с кодом {code}.", "error")
            QMessageBox.warning(
                self, "udev",
                "Установка не удалась или была отменена. Проверьте права root/polkit.")
        self.refresh()

    # -- log --------------------------------------------------------------
    def append_log(self, text: str, level: str = "info"):
        stamp = datetime.now().strftime("%H:%M:%S")
        prefix = {"error": "ERROR", "warning": "WARN", "warn": "WARN"}.get(level, "INFO")
        self.log_edit.appendPlainText(f"[{stamp}] {prefix}  {text}")

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
